#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step1 (Debug) v3: Beamer.txt -> Step1 HTML (robust PDF page mapping)
Problem this solves:
- Your final PDF is rendered with a template that INSERTS extra pages (title/agenda/section separators),
  so "frame_index + offset" is NOT reliable.
- You want HTML to contain ONLY the real Beamer frames (no extra template pages).
- But you still want snapshots (fig/table) taken from the rendered PDF.

Solution:
- We keep slides = parsed frames from beamer.txt (so HTML has no extra pages).
- For snapshots, we build a per-frame mapping: frame_i -> pdf_page_j by matching slide titles/body keywords
  against PDF page extracted text, using a monotonic alignment (DP).
- Extra template pages are automatically skipped (they don't match any frame well).

Dependencies:
- PyMuPDF (pymupdf) for PDF text + rendering
- Your project's CamelAIClient in ppt_requirements_collector.py

Run:
- Edit CONFIG section only, then: python step1_beamertext_debug_v3.py
"""

from __future__ import annotations

import re
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # pip install pymupdf

# ---------- CONFIG (edit these, no CLI needed) ----------
BASE_DIR = Path(__file__).resolve().parent

BEAMER_TXT_PATH = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/content.txt"   # e.g. "/abs/path/to/beamer.txt"
PDF_PATH        = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/base.pdf"   # e.g. "/abs/path/to/beamer.pdf"
OUT_HTML_PATH   = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/step1.html"   # e.g. "/abs/path/to/out_step1.html"

TEMPLATE_PATH   = str(BASE_DIR / "step1_template_step1_beamertext_v2.html")
PROMPT_PATH     = str(BASE_DIR / "step1_prompt_beamertext_v2.txt")

# Page mapping mode:
# - If True: build frame->pdf_page mapping with DP alignment (recommended when PDF has inserted pages)
# - If False: use pdf_page = frame_index + PAGE_OFFSET (old behavior)
USE_PAGE_MAP = True
PAGE_OFFSET = 0  # used only if USE_PAGE_MAP=False

# Mapping knobs
MAP_MAX_PAGES_SCAN = 500         # safety cap
MAP_MIN_SCORE = 0.08             # below this score treated as "weak match" (still mapped, but logged)
MAP_WINDOW_PAD = 6               # allow mapping early/late by up to this many pages beyond DP monotonic
MAP_BODY_TOKEN_LIMIT = 60        # how many tokens from body to use for matching

# Limit for faster iteration: None or list of 0-based frame indices, e.g. [0,1,2]
ONLY_FRAMES: Optional[List[int]] = None

# Snapshot quality
SNAPSHOT_DPI = 220

# LLM controls
SYSTEM_PROMPT = "You are a careful Beamer-to-HTML extractor. Output only a single HTML <section>."
DRY_RUN = False
FORCE_SKELETON = True
PRINT_LLM_PREVIEW = True
# -----------------------------------------------------

from ppt_requirements_collector import CamelAIClient  # keep consistent with your repo


# ------------------ Beamer parsing ------------------
FRAME_RE = re.compile(r"\\begin\{frame\}(\[[^\]]*\])?(\{[^}]*\})?\s*(.*?)\\end\{frame\}", re.S)

def extract_frames(beamer_tex: str) -> List[str]:
    return [m.group(0) for m in FRAME_RE.finditer(beamer_tex)]

def extract_title(frame_tex: str) -> str:
    m = re.search(r"\\frametitle\{([^}]*)\}", frame_tex)
    if m: return m.group(1).strip()
    m = re.search(r"\\begin\{frame\}(?:\[[^\]]*\])?\{([^}]*)\}", frame_tex)
    if m: return m.group(1).strip()
    return ""

def strip_frame_wrapper(frame_tex: str) -> str:
    inner = re.sub(r"^\\begin\{frame\}(\[[^\]]*\])?(\{[^}]*\})?\s*", "", frame_tex.strip(), flags=re.S)
    inner = re.sub(r"\\end\{frame\}\s*$", "", inner.strip(), flags=re.S)
    inner = re.sub(r"\\frametitle\{[^}]*\}\s*", "", inner)
    return inner.strip()

def latex_to_plain_approx(s: str) -> str:
    """Very lightweight LaTeX->plain for matching only."""
    s = s or ""
    # remove commands like \textbf{..} -> keep inner
    s = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\$[^$]*\$", " ", s)  # drop inline math for matching
    s = re.sub(r"\s+", " ", s)
    return s.strip()

@dataclass
class Snapshot:
    sid: str
    kind: str  # "image" | "table"

def tokenize_snapshots(frame_inner: str) -> Tuple[str, List[Snapshot]]:
    snapshots: List[Snapshot] = []
    idx = 0

    def new_sid(kind: str) -> str:
        nonlocal idx
        idx += 1
        sid = f"SNAPSHOT_{idx}"
        snapshots.append(Snapshot(sid=sid, kind=kind))
        return sid

    def repl_graphics(_m: re.Match) -> str:
        sid = new_sid("image")
        return f"[[{sid}]]"
    frame_inner = re.sub(r"\\includegraphics(\[[^\]]*\])?\{[^}]+\}", repl_graphics, frame_inner)

    def repl_table_env(_m: re.Match) -> str:
        sid = new_sid("table")
        return f"[[{sid}]]"
    frame_inner = re.sub(r"\\begin\{table\}.*?\\end\{table\}", repl_table_env, frame_inner, flags=re.S)
    frame_inner = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", repl_table_env, frame_inner, flags=re.S)
    frame_inner = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", repl_table_env, frame_inner, flags=re.S)

    return frame_inner, snapshots


# ------------------ Prompt fill ------------------
def safe_replace(prompt: str, mapping: Dict[str, str]) -> str:
    out = prompt
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out


# ------------------ PDF snapshot helpers ------------------
def render_page_png(doc: fitz.Document, page_index: int, dpi: int = 220, clip: Optional[fitz.Rect] = None) -> bytes:
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
    return pix.tobytes("png")

def b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")

def page_area(page: fitz.Page) -> float:
    r = page.rect
    return float(r.width * r.height)

def get_image_rects_best(page: fitz.Page) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    for img in page.get_images(full=True):
        xref = img[0]
        for r in page.get_image_rects(xref):
            rects.append(r)
    rects = [r for r in rects if (r.width * r.height) > 3000]
    rects.sort(key=lambda r: (-(r.width * r.height), r.y0, r.x0))
    return rects

def union_rect(rects: List[fitz.Rect]) -> Optional[fitz.Rect]:
    if not rects:
        return None
    u = rects[0]
    for r in rects[1:]:
        u = u | r
    return u

def clamp_rect(r: fitz.Rect, page_r: fitz.Rect) -> fitz.Rect:
    x0 = max(page_r.x0, r.x0)
    y0 = max(page_r.y0, r.y0)
    x1 = min(page_r.x1, r.x1)
    y1 = min(page_r.y1, r.y1)
    return fitz.Rect(x0, y0, x1, y1)

def expand_rect(r: fitz.Rect, margin: float, page_r: fitz.Rect) -> fitz.Rect:
    rr = fitz.Rect(r.x0 - margin, r.y0 - margin, r.x1 + margin, r.y1 + margin)
    return clamp_rect(rr, page_r)

def guess_table_bbox(page: fitz.Page) -> Optional[fitz.Rect]:
    pr = page.rect
    top_cut = pr.y0 + pr.height * 0.16
    bottom_cut = pr.y0 + pr.height * 0.96

    blocks = page.get_text("blocks")
    cand: List[fitz.Rect] = []
    for b in blocks:
        x0, y0, x1, y1, txt, *_ = b
        txt = (txt or "").strip()
        if not txt:
            continue
        if y1 <= top_cut or y0 >= bottom_cut:
            continue
        if len(txt) < 8:
            continue
        cand.append(fitz.Rect(x0, y0, x1, y1))

    u = union_rect(cand)
    if u is None:
        return None
    if (u.width * u.height) < 0.10 * page_area(page):
        return None
    return expand_rect(u, margin=8, page_r=pr)


# ------------------ Frame -> PDF page mapping ------------------
STOP = {"the","and","for","with","from","into","based","core","concepts","overview","introduction"}

def normalize_tokens(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    toks = [t for t in toks if t not in STOP]
    return toks

def overlap_score(frame_sig: str, page_text: str) -> float:
    ft = set(normalize_tokens(frame_sig))
    if not ft:
        return 0.0
    pt = set(normalize_tokens(page_text))
    inter = len(ft & pt)
    return inter / max(1, len(ft))

def build_frame_signature(title: str, inner_tex: str) -> str:
    plain = latex_to_plain_approx(inner_tex)
    toks = normalize_tokens(plain)
    toks = toks[:MAP_BODY_TOKEN_LIMIT]
    return (title + " " + " ".join(toks)).strip()

def build_page_texts(doc: fitz.Document, max_pages: int) -> List[str]:
    n = min(doc.page_count, max_pages)
    out = []
    for i in range(n):
        t = doc.load_page(i).get_text("text") or ""
        out.append(t)
    return out

def dp_align(frames_sig: List[str], pages_text: List[str]) -> Tuple[List[int], List[float]]:
    """
    Monotonic alignment by DP:
    choose page indices j0<j1<... maximizing sum score(i,j).
    O(F*P) with prefix max trick.
    """
    F = len(frames_sig)
    P = len(pages_text)
    if F == 0 or P == 0:
        return ([-1]*F, [0.0]*F)

    # scores on the fly to save memory
    # DP rows: best value ending at page j for frame i
    dp_prev = [-1e9]*P
    back = [[-1]*P for _ in range(F)]

    # i=0
    for j in range(P):
        dp_prev[j] = overlap_score(frames_sig[0], pages_text[j])
        back[0][j] = -1

    for i in range(1, F):
        dp_cur = [-1e9]*P
        # prefix max of dp_prev
        pref_best = [-1e9]*P
        pref_arg = [-1]*P
        bestv = -1e9
        bestk = -1
        for j in range(P):
            if dp_prev[j] > bestv:
                bestv = dp_prev[j]
                bestk = j
            pref_best[j] = bestv
            pref_arg[j] = bestk

        for j in range(P):
            if j == 0:
                continue
            prev_best = pref_best[j-1]
            if prev_best <= -1e8:
                continue
            sc = overlap_score(frames_sig[i], pages_text[j])
            dp_cur[j] = prev_best + sc
            back[i][j] = pref_arg[j-1]

        dp_prev = dp_cur

    # pick best end
    end_j = max(range(P), key=lambda j: dp_prev[j])
    # backtrack
    mapping = [-1]*F
    scores = [0.0]*F
    j = end_j
    for i in range(F-1, -1, -1):
        mapping[i] = j
        scores[i] = overlap_score(frames_sig[i], pages_text[j]) if j >= 0 else 0.0
        j = back[i][j] if j >= 0 else -1
        if i > 0 and j < 0:
            # no valid monotonic path; fall back to 0 for early
            j = 0
    return mapping, scores


# ------------------ HTML skeleton + helpers ------------------
SKELETON = """<section class="slide layout--detail-list" data-slide-id="{slide_id}">
  <header>
    <div class="title-wrap">
      <h1 class="raw-title">{title}</h1>
      <div class="subtitle">{subtitle}</div>
    </div>
    <div class="tags">{tags}</div>
  </header>

  <main>
    <div class="pane text-pane">
      <div class="raw-body">
{body}
      </div>
    </div>

    <div class="pane fig-pane">
      <div class="fig-grid">
{fig}
      </div>
    </div>
  </main>

  <aside class="raw-notes"><pre>{notes}</pre></aside>
</section>"""

def indent(s: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else "" for line in (s or "").splitlines())

def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")

def escape_html(s: str) -> str:
    s = s or ""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))

def html_unescape(s: str) -> str:
    s = s or ""
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&#39;", "'").replace("&amp;", "&"))

def ensure_single_section(html_text: str) -> str:
    html_text = (html_text or "").strip()
    html_text = re.sub(r"^```.*?\n", "", html_text)
    html_text = re.sub(r"\n```$", "", html_text)
    m = re.search(r"<section\b.*?</section>", html_text, flags=re.S | re.I)
    return m.group(0).strip() if m else ""

def build_fig_boxes_from_sids(sids: List[str], pdf_page_index: int) -> str:
    boxes = []
    for sid in sids:
        boxes.append(f"""<div class="figure-box" data-snapshot-id="{sid}">
  <div class="figure-head">
    <div class="figure-title">Snapshot</div>
    <div class="figure-badge">PDF p{pdf_page_index}</div>
  </div>
  <div class="figure-body"><div class="snapshot-hint">[SNAPSHOT:{sid}]</div></div>
  <div class="figure-caption"></div>
</div>""")
    return "\n".join(boxes)

def enforce_skeleton(slide_id: str, title_fallback: str, pdf_page_index: int, raw: str) -> str:
    sec = ensure_single_section(raw)
    if not sec:
        body = (raw or "").strip() or "<p></p>"
        return SKELETON.format(slide_id=slide_id, title=escape_html(title_fallback), subtitle="", tags="",
                               body=indent(body, 8), fig="", notes="")

    title = ""
    m = re.search(r'<h1[^>]*class="raw-title"[^>]*>(.*?)</h1>', sec, flags=re.S | re.I)
    if m:
        title = strip_tags(m.group(1)).strip()
    if not title:
        title = title_fallback

    body_html = ""
    m = re.search(r'<div[^>]*class="raw-body"[^>]*>(.*?)</div>', sec, flags=re.S | re.I)
    if m:
        body_html = m.group(1).strip()
    if not body_html:
        body_html = "<p></p>"

    fig_html = ""
    m = re.search(r'<div[^>]*class="fig-grid"[^>]*>(.*?)</div>', sec, flags=re.S | re.I)
    if m:
        fig_html = m.group(1).strip()

    notes = ""
    m = re.search(r'<aside[^>]*class="raw-notes"[^>]*>.*?<pre[^>]*>(.*?)</pre>.*?</aside>', sec, flags=re.S | re.I)
    if m:
        notes = html_unescape(m.group(1)).strip()

    sids = re.findall(r"\[\[(SNAPSHOT_\d+)\]\]", body_html)
    if sids:
        for sid in sids:
            body_html = body_html.replace(f"[[{sid}]]", "")
        if not fig_html:
            fig_html = build_fig_boxes_from_sids(sids, pdf_page_index)

    return SKELETON.format(
        slide_id=slide_id,
        title=escape_html(title),
        subtitle="",
        tags="",
        body=indent(body_html.strip(), 8),
        fig=indent(fig_html.strip(), 8) if fig_html.strip() else "",
        notes=escape_html(notes)
    )

def add_has_snapshot_class(slide_html: str) -> str:
    if 'data-snapshot-id="' not in slide_html:
        return slide_html
    m = re.search(r'<section[^>]*class="([^"]*)"', slide_html, flags=re.I)
    if not m:
        return slide_html
    classes = m.group(1)
    if "has-snapshot" in classes:
        return slide_html
    new = classes + " has-snapshot"
    return slide_html[:m.start(1)] + new + slide_html[m.end(1):]

def inject_slides_into_template(template_html: str, slides_html: str) -> str:
    marker = '<!-- Step1: The model generates <section class="slide" ...> here. -->'
    if marker in template_html:
        return template_html.replace(marker, marker + "\n" + slides_html + "\n")
    m = re.search(r'(<div class="deck"\s+id="deck"\s*>\s*)', template_html, flags=re.I)
    if not m:
        raise RuntimeError("Cannot find deck injection point in template.")
    pos = m.end(1)
    return template_html[:pos] + "\n" + slides_html + "\n" + template_html[pos:]


def inject_snapshot_imgs(slide_html: str, imgs_b64: Dict[str, str], pdf_page_index: int) -> str:
    for sid, b64 in imgs_b64.items():
        pat = re.compile(
            rf'(<div class="figure-box"[^>]*data-snapshot-id="{re.escape(sid)}"[^>]*>.*?<div class="figure-body">)(.*?)(</div>)',
            re.S
        )
        def _repl(m: re.Match) -> str:
            return m.group(1) + f'<img class="snapshot-img" src="data:image/png;base64,{b64}" alt="{sid}"/>' + m.group(3)
        if pat.search(slide_html):
            slide_html = pat.sub(_repl, slide_html, count=1)

    missing = [sid for sid in imgs_b64.keys() if f'data-snapshot-id="{sid}"' not in slide_html]
    if missing:
        boxes = []
        for sid in missing:
            b64 = imgs_b64[sid]
            boxes.append(f"""
<div class="figure-box" data-snapshot-id="{sid}">
  <div class="figure-head">
    <div class="figure-title">Snapshot</div>
    <div class="figure-badge">PDF p{pdf_page_index}</div>
  </div>
  <div class="figure-body"><img class="snapshot-img" src="data:image/png;base64,{b64}" alt="{sid}"/></div>
  <div class="figure-caption"></div>
</div>
""".strip())
        insert = "\n".join(boxes)
        m = re.search(r'(<div class="fig-grid"[^>]*>)', slide_html, flags=re.S | re.I)
        if m:
            pos = m.end(1)
            slide_html = slide_html[:pos] + "\n" + insert + "\n" + slide_html[pos:]
        else:
            slide_html = slide_html.replace("</section>", "\n" + insert + "\n</section>")
    return slide_html


# ------------------ main ------------------
def main() -> None:
    beamer_path = Path(BEAMER_TXT_PATH).expanduser().resolve()
    pdf_path = Path(PDF_PATH).expanduser().resolve()
    out_path = Path(OUT_HTML_PATH).expanduser().resolve()
    template_path = Path(TEMPLATE_PATH).expanduser().resolve()
    prompt_path = Path(PROMPT_PATH).expanduser().resolve()

    for p in [beamer_path, pdf_path, template_path, prompt_path]:
        if not p.exists():
            raise SystemExit(f"[ERR] file not found: {p}")

    beamer_text = beamer_path.read_text(encoding="utf-8", errors="ignore")
    frames = extract_frames(beamer_text)
    if not frames:
        raise SystemExit("[ERR] No \\begin{frame}...\\end{frame} found in beamer input.")

    doc = fitz.open(str(pdf_path))
    pages_text = build_page_texts(doc, MAP_MAX_PAGES_SCAN)

    # Build page map if enabled
    page_map: List[int] = []
    page_scores: List[float] = []
    if USE_PAGE_MAP:
        sigs = []
        for f in frames:
            title = extract_title(f) or ""
            inner = strip_frame_wrapper(f)
            sigs.append(build_frame_signature(title, inner))
        page_map, page_scores = dp_align(sigs, pages_text)
        print(f"[MAP] built frame->page mapping (frames={len(frames)} pdf_pages={len(pages_text)})")
        weak = sum(1 for s in page_scores if s < MAP_MIN_SCORE)
        if weak:
            print(f"[MAP] warning: {weak} frames have weak match score < {MAP_MIN_SCORE:.2f} (still mapped).")
    else:
        page_map = [i + int(PAGE_OFFSET) for i in range(len(frames))]
        page_scores = [1.0] * len(frames)
        print(f"[MAP] using constant PAGE_OFFSET={PAGE_OFFSET}")

    camel = CamelAIClient()
    prompt_tpl = prompt_path.read_text(encoding="utf-8", errors="ignore")
    template_html = template_path.read_text(encoding="utf-8", errors="ignore")

    wanted = set(ONLY_FRAMES) if ONLY_FRAMES is not None else None

    slides: List[str] = []
    for i, frame_tex in enumerate(frames):
        if wanted is not None and i not in wanted:
            continue

        slide_id = f"s{i+1}"
        pdf_page = page_map[i] if i < len(page_map) else -1
        match_score = page_scores[i] if i < len(page_scores) else 0.0

        title = extract_title(frame_tex) or f"Slide {i+1}"
        inner = strip_frame_wrapper(frame_tex)
        cleaned_inner, snaps = tokenize_snapshots(inner)

        filled_prompt = safe_replace(prompt_tpl, {
            "SLIDE_ID": slide_id,
            "PDF_PAGE_INDEX": str(pdf_page),
            "FRAME_LATEX": cleaned_inner
        })

        if DRY_RUN:
            slide_html = SKELETON.format(
                slide_id=slide_id, title=escape_html(title), subtitle="", tags='<span class="tag tag--accent">DRY_RUN</span>',
                body=indent("<p>DRY_RUN: LLM will fill content here.</p>", 8),
                fig="",
                notes=""
            )
        else:
            print(f"[LLM] calling CamelAIClient.get_response frame={i} slide_id={slide_id} mapped_pdf_page={pdf_page} score={match_score:.3f} ...")
            resp = camel.get_response(filled_prompt, system_prompt=SYSTEM_PROMPT)
            if PRINT_LLM_PREVIEW:
                preview = (resp or "").strip().replace("\n", " ")
                print("[LLM] preview:", preview[:180] + ("..." if len(preview) > 180 else ""))

            slide_html = enforce_skeleton(slide_id, title, pdf_page, resp) if FORCE_SKELETON else ensure_single_section(resp)

        # Snapshot injection: only if we have a valid mapped page
        if snaps:
            if pdf_page < 0 or pdf_page >= doc.page_count:
                print(f"[WARN] mapped pdf_page out of range: {pdf_page} (pages={doc.page_count}). Skip snapshots for {slide_id}.")
            else:
                imgs_b64: Dict[str, str] = {}
                page = doc.load_page(pdf_page)
                img_rects = get_image_rects_best(page)
                used = [False] * len(img_rects)

                def pick_next_large_rect(min_area_ratio: float = 0.06) -> Optional[fitz.Rect]:
                    pa = page_area(page)
                    for idx_r, r in enumerate(img_rects):
                        if used[idx_r]:
                            continue
                        if (r.width * r.height) >= min_area_ratio * pa:
                            used[idx_r] = True
                            return r
                    for idx_r, r in enumerate(img_rects):
                        if not used[idx_r]:
                            used[idx_r] = True
                            return r
                    return None

                for s in snaps:
                    clip = None
                    if s.kind == "image":
                        clip = pick_next_large_rect()
                    else:
                        clip = guess_table_bbox(page)

                    png = render_page_png(doc, pdf_page, dpi=SNAPSHOT_DPI, clip=clip)
                    imgs_b64[s.sid] = b64_png(png)

                slide_html = inject_snapshot_imgs(slide_html, imgs_b64, pdf_page)

        slide_html = add_has_snapshot_class(slide_html)
        slides.append(slide_html)

        print(f"[OK] frame {i} -> {slide_id} (mapped pdf p{pdf_page}, score={match_score:.3f}) snaps={len(snaps)}")

    deck_html = "\n\n".join(slides)
    final_html = inject_slides_into_template(template_html, deck_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")
    print("[DONE] wrote:", out_path)


if __name__ == "__main__":
    main()
