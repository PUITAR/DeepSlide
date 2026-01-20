#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step1 (Debug): Beamer.txt -> Step1 HTML
- Text: convert from beamer frames via your existing CamelAIClient (project API wrapper)
- Figures/Tables: snapshot from rendered PDF and inject into the slide's fig-pane

You said you already have external API & wrappers — so this script IMPORTS your project's CamelAIClient
instead of re-implementing any HTTP client.

Files:
- Template: step1_template_step1_beamertext_v1.html
- Prompt  : step1_prompt_beamertext_v1.txt

How to use:
1) Edit CONFIG section (paths + offsets) then run: python step1_beamertext_debug_v1.py
2) Open OUT_HTML_PATH in browser.

Note:
- Snapshot cropping:
  * includegraphics -> best-effort crop via PDF embedded image rects (reading-order)
  * tables/tabular  -> fallback full-page snapshot (robust baseline)
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

TEMPLATE_PATH   = str(BASE_DIR / "step1_template_step1_beamertext_v1.html")
PROMPT_PATH     = str(BASE_DIR / "step1_prompt_beamertext_v1.txt")

# PDF page alignment: pdf_page = frame_index + PAGE_OFFSET
PAGE_OFFSET = 0

# Limit for faster iteration: None or list of 0-based frame indices, e.g. [0,1,2]
ONLY_FRAMES: Optional[List[int]] = None

# Snapshot quality
SNAPSHOT_DPI = 200

# LLM controls
SYSTEM_PROMPT = "You are a careful Beamer-to-HTML extractor."

# If True, do not call LLM, output minimal placeholder sections.
DRY_RUN = False
# -----------------------------------------------------


# ---- import your API wrapper (keep consistent with your project) ----
# Your project defines CamelAIClient in ppt_requirements_collector.py
from ppt_requirements_collector import CamelAIClient  # noqa: E402


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

@dataclass
class Snapshot:
    sid: str   # SNAPSHOT_1
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

    # includegraphics -> image
    def repl_graphics(_m: re.Match) -> str:
        sid = new_sid("image")
        return f"[[{sid}]]"

    frame_inner = re.sub(r"\\includegraphics(\[[^\]]*\])?\{[^}]+\}", repl_graphics, frame_inner)

    # tables/tabular/figure -> table snapshot
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
def render_page_png(doc: fitz.Document, page_index: int, dpi: int = 200, clip: Optional[fitz.Rect] = None) -> bytes:
    if page_index < 0 or page_index >= doc.page_count:
        raise ValueError(f"page_index out of range: {page_index} (pages={doc.page_count})")
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
    return pix.tobytes("png")

def b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")

def get_image_rects_in_reading_order(page: fitz.Page) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    for img in page.get_images(full=True):
        xref = img[0]
        for r in page.get_image_rects(xref):
            rects.append(r)
    rects.sort(key=lambda r: (round(r.y0, 2), round(r.x0, 2)))
    rects = [r for r in rects if (r.width * r.height) > 4000]
    return rects


# ------------------ HTML injection ------------------
def ensure_single_section(html_text: str) -> str:
    html_text = html_text.strip()
    html_text = re.sub(r"^```.*?\n", "", html_text)
    html_text = re.sub(r"\n```$", "", html_text)
    m = re.search(r"<section\b.*?</section>", html_text, flags=re.S | re.I)
    if not m:
        raise RuntimeError("Model output does not contain a <section>...</section> block.")
    return m.group(0).strip()

def add_slide_id_if_missing(slide_html: str, slide_id: str) -> str:
    if "data-slide-id" in slide_html:
        return slide_html
    return re.sub(r"<section\b", f'<section data-slide-id="{slide_id}"', slide_html, count=1)

def ensure_raw_notes(slide_html: str) -> str:
    if "raw-notes" in slide_html:
        if "<pre" not in slide_html:
            slide_html = slide_html.replace('class="raw-notes">', 'class="raw-notes"><pre>')
            slide_html = slide_html.replace("</aside>", "</pre></aside>")
        return slide_html
    return slide_html.replace("</section>", '<aside class="raw-notes"><pre></pre></aside>\n</section>')

def inject_slides_into_template(template_html: str, slides_html: str) -> str:
    marker = "<!-- Step1: The model generates <section class=\"slide\" ...> here. -->"
    if marker in template_html:
        return template_html.replace(marker, marker + "\n" + slides_html + "\n")
    m = re.search(r'(<div class="deck"\s+id="deck"\s*>\s*)', template_html)
    if not m:
        raise RuntimeError("Cannot find deck injection point in template.")
    pos = m.end(1)
    return template_html[:pos] + "\n" + slides_html + "\n" + template_html[pos:]

def inject_snapshot_imgs(slide_html: str, imgs_b64: Dict[str, str], pdf_page_index: int) -> str:
    # Replace inside existing figure-box by sid
    for sid, b64 in imgs_b64.items():
        pat = re.compile(
            rf'(<div class="figure-box"[^>]*data-snapshot-id="{re.escape(sid)}"[^>]*>.*?<div class="figure-body">)(.*?)(</div>)',
            re.S
        )
        def _repl(m: re.Match) -> str:
            return m.group(1) + f'<img class="snapshot-img" src="data:image/png;base64,{b64}" alt="{sid}"/>' + m.group(3)
        if pat.search(slide_html):
            slide_html = pat.sub(_repl, slide_html, count=1)

    # If the LLM forgot placeholders, append them into fig-grid
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
        m = re.search(r'(<div class="fig-grid"[^>]*>)', slide_html)
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

    # init your wrapper
    camel = CamelAIClient()

    prompt_tpl = prompt_path.read_text(encoding="utf-8", errors="ignore")
    template_html = template_path.read_text(encoding="utf-8", errors="ignore")

    doc = fitz.open(str(pdf_path))

    slides: List[str] = []
    for i, frame_tex in enumerate(frames):
        if ONLY_FRAMES is not None and i not in set(ONLY_FRAMES):
            continue

        slide_id = f"s{i+1}"
        pdf_page = i + int(PAGE_OFFSET)

        title = extract_title(frame_tex)
        inner = strip_frame_wrapper(frame_tex)

        cleaned_inner, snaps = tokenize_snapshots(inner)

        filled_prompt = safe_replace(prompt_tpl, {
            "SLIDE_ID": slide_id,
            "PDF_PAGE_INDEX": str(pdf_page),
            "FRAME_LATEX": cleaned_inner
        })

        if DRY_RUN:
            slide_html = f"""
<section class="slide layout--detail-list" data-slide-id="{slide_id}">
  <header>
    <div class="title-wrap">
      <h1 class="raw-title">{title or ("Slide " + str(i+1))}</h1>
      <div class="subtitle"></div>
    </div>
    <div class="tags"><span class="tag tag--accent">DRY_RUN</span></div>
  </header>
  <main>
    <div class="pane text-pane">
      <div class="raw-body"><p>DRY_RUN: LLM will fill content here.</p></div>
    </div>
    <div class="pane fig-pane"><div class="fig-grid"></div></div>
  </main>
  <aside class="raw-notes"><pre></pre></aside>
</section>
""".strip()
        else:
            resp = camel.get_response(filled_prompt, system_prompt=SYSTEM_PROMPT)
            slide_html = ensure_single_section(resp)
            slide_html = add_slide_id_if_missing(slide_html, slide_id)
            slide_html = ensure_raw_notes(slide_html)

        # Snapshot injection
        if snaps:
            imgs_b64: Dict[str, str] = {}
            page = doc.load_page(pdf_page)
            img_rects = get_image_rects_in_reading_order(page)
            rect_cursor = 0

            for s in snaps:
                if s.kind == "image" and rect_cursor < len(img_rects):
                    clip = img_rects[rect_cursor]
                    rect_cursor += 1
                    png = render_page_png(doc, pdf_page, dpi=SNAPSHOT_DPI, clip=clip)
                else:
                    png = render_page_png(doc, pdf_page, dpi=SNAPSHOT_DPI, clip=None)
                imgs_b64[s.sid] = b64_png(png)

            slide_html = inject_snapshot_imgs(slide_html, imgs_b64, pdf_page)

        slides.append(slide_html)
        print(f"[OK] frame {i} -> {slide_id} (pdf p{pdf_page}) snaps={len(snaps)}")

    deck_html = "\n\n".join(slides)
    final_html = inject_slides_into_template(template_html, deck_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")
    print("[DONE] wrote:", out_path)


if __name__ == "__main__":
    main()
