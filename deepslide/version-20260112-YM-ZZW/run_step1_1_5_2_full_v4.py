#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full pipeline (v4): Step1 (beamer.txt -> HTML with snapshots) -> Step1.5 (per-slide plan JSON) -> Step2 (per-slide render -> final HTML)

Fixes:
1) Step1 images: auto-detect images/tables from mapped PDF pages; export PNGs under out_dir/snapshots/ and reference by relative path.
2) Step1.5 JSON truncation: per-slide planning (one LLM call per slide), merged into a strict JSON file.
3) Step2 truncation / missing slides: per-slide rendering (one LLM call per slide) returning ONLY <section>, then injected into a local keynote template.

Edit CONFIG section only; no CLI required.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

# ---------------- CONFIG (edit here only) ----------------
BASE_DIR = Path(__file__).resolve().parent
HD = BASE_DIR / "html_diedai"

# Step1 inputs
BEAMER_TXT_PATH = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/content.txt"     # "/abs/path/to/beamer.txt"
PDF_PATH        = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/base.pdf"     # "/abs/path/to/rendered.pdf"

# Prompts (in html_diedai/)
STEP1_BODY_PROMPT_PATH = str(HD / "step1_prompt_beamertext_v3_fixsnapshot.txt")
STEP1_5_PROMPT_PATH    = str(HD / "step1_5_planner_prompt_v12_per_slide_img.txt")
STEP2_PROMPT_PATH      = str(HD / "step2_executor_prompt_v12_per_slide_img.txt")

# Templates
STEP1_TEMPLATE_PATH      = str(HD / "step1_template_step1_beamertext_v2.html")
STEP2_BASE_TEMPLATE_PATH = str(HD / "step1_template_keynote_v4.html")  # injection only, NOT fed into LLM

# Outputs
OUT_DIR = str(BASE_DIR / "html_outputs")
STEP1_OUT_HTML   = "step1_generated.html"
STEP1_5_OUT_JSON = "step1_5_plan.json"
STEP2_OUT_HTML   = "step2_visual_deck.html"

# Page mapping
USE_PAGE_MAP = True
MAP_MAX_PAGES_SCAN = 500
MAP_MIN_SCORE = 0.08
MAP_BODY_TOKEN_LIMIT = 70

# Snapshot export
SNAPSHOT_DPI = 220
MAX_SNAPSHOTS_PER_SLIDE = 2  # take top-2 largest images; if none, try 1 table-like crop

# LLM
SYSTEM_PROMPT_STEP1 = "You are a careful Beamer-to-HTML converter. Output only an HTML fragment."
SYSTEM_PROMPT_STEP15 = "You are a careful slide planner. Output only strict JSON."
SYSTEM_PROMPT_STEP2 = "You are a careful keynote renderer. Output only one <section>."

PRINT_PREVIEW = True
DRY_RUN = False

# For faster iteration: set to e.g. [0,1,2] (0-based frame indices); None = all
ONLY_FRAMES: Optional[List[int]] = None
# --------------------------------------------------------


from ppt_requirements_collector import CamelAIClient  # keep consistent with your repo


# ------------------ Beamer parsing ------------------
FRAME_RE = re.compile(r"\\begin\{frame\}(\[[^\]]*\])?(\{[^}]*\})?\s*(.*?)\\end\{frame\}", re.S)

def extract_frames(beamer_tex: str) -> List[str]:
    return [m.group(0) for m in FRAME_RE.finditer(beamer_tex)]

def extract_title(frame_tex: str) -> str:
    m = re.search(r"\\frametitle\{([^}]*)\}", frame_tex)
    if m:
        return m.group(1).strip()
    m = re.search(r"\\begin\{frame\}(?:\[[^\]]*\])?\{([^}]*)\}", frame_tex)
    if m:
        return m.group(1).strip()
    return ""

def strip_frame_wrapper(frame_tex: str) -> str:
    inner = re.sub(r"^\\begin\{frame\}(\[[^\]]*\])?(\{[^}]*\})?\s*", "", frame_tex.strip(), flags=re.S)
    inner = re.sub(r"\\end\{frame\}\s*$", "", inner.strip(), flags=re.S)
    inner = re.sub(r"\\frametitle\{[^}]*\}\s*", "", inner)
    return inner.strip()


# ------------------ Mapping frames -> PDF pages ------------------
STOP = {"the","and","for","with","from","into","based","core","concepts","overview","introduction","method","results","system"}

def latex_to_plain_approx(s: str) -> str:
    s = s or ""
    s = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\$[^$]*\$", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_tokens(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if len(t) >= 3 and t not in STOP]
    return toks

def overlap_score(frame_sig: str, page_text: str) -> float:
    ft = set(normalize_tokens(frame_sig))
    if not ft:
        return 0.0
    pt = set(normalize_tokens(page_text))
    inter = len(ft & pt)
    return inter / max(1, len(ft))

def build_frame_signature(title: str, inner_tex: str, token_limit: int) -> str:
    plain = latex_to_plain_approx(inner_tex)
    toks = normalize_tokens(plain)[:token_limit]
    return (title + " " + " ".join(toks)).strip()

def build_page_texts(doc: fitz.Document, max_pages: int) -> List[str]:
    n = min(doc.page_count, max_pages)
    out = []
    for i in range(n):
        out.append(doc.load_page(i).get_text("text") or "")
    return out

def dp_align(frames_sig: List[str], pages_text: List[str]) -> Tuple[List[int], List[float]]:
    F, P = len(frames_sig), len(pages_text)
    if F == 0 or P == 0:
        return ([-1]*F, [0.0]*F)

    dp_prev = [-1e9]*P
    back = [[-1]*P for _ in range(F)]

    for j in range(P):
        dp_prev[j] = overlap_score(frames_sig[0], pages_text[j])
        back[0][j] = -1

    for i in range(1, F):
        dp_cur = [-1e9]*P
        pref_best = [-1e9]*P
        pref_arg = [-1]*P
        bestv, bestk = -1e9, -1
        for j in range(P):
            if dp_prev[j] > bestv:
                bestv, bestk = dp_prev[j], j
            pref_best[j], pref_arg[j] = bestv, bestk

        for j in range(1, P):
            prev_best = pref_best[j-1]
            if prev_best <= -1e8:
                continue
            sc = overlap_score(frames_sig[i], pages_text[j])
            dp_cur[j] = prev_best + sc
            back[i][j] = pref_arg[j-1]
        dp_prev = dp_cur

    end_j = max(range(P), key=lambda j: dp_prev[j])
    mapping = [-1]*F
    scores = [0.0]*F
    j = end_j
    for i in range(F-1, -1, -1):
        mapping[i] = j
        scores[i] = overlap_score(frames_sig[i], pages_text[j]) if j >= 0 else 0.0
        j = back[i][j] if j >= 0 else -1
        if i > 0 and j < 0:
            j = 0
    return mapping, scores


# ------------------ Snapshot extraction (PDF -> PNG files) ------------------
@dataclass
class SnapshotAsset:
    sid: str
    kind: str     # "image" | "table"
    rel_path: str # e.g. "snapshots/SNAPSHOT_1.png"

def render_page_png(doc: fitz.Document, page_index: int, dpi: int, clip: Optional[fitz.Rect] = None) -> bytes:
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
    return pix.tobytes("png")

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
    if (u.width * u.height) < 0.10 * float(pr.width * pr.height):
        return None
    margin = 8
    rr = fitz.Rect(u.x0 - margin, u.y0 - margin, u.x1 + margin, u.y1 + margin)
    rr = fitz.Rect(max(pr.x0, rr.x0), max(pr.y0, rr.y0), min(pr.x1, rr.x1), min(pr.y1, rr.y1))
    return rr

def extract_snapshots_for_page(doc: fitz.Document, page_index: int, sid_counter_start: int,
                               out_snap_dir: Path, max_snaps: int) -> Tuple[List[SnapshotAsset], int]:
    assets: List[SnapshotAsset] = []
    counter = sid_counter_start
    page = doc.load_page(page_index)

    rects = get_image_rects_best(page)
    if rects:
        for r in rects[:max_snaps]:
            counter += 1
            sid = f"SNAPSHOT_{counter}"
            png = render_page_png(doc, page_index, dpi=SNAPSHOT_DPI, clip=r)
            rel = f"snapshots/{sid}.png"
            (out_snap_dir / f"{sid}.png").write_bytes(png)
            assets.append(SnapshotAsset(sid=sid, kind="image", rel_path=rel))
        return assets, counter

    tb = guess_table_bbox(page)
    if tb is not None:
        counter += 1
        sid = f"SNAPSHOT_{counter}"
        png = render_page_png(doc, page_index, dpi=SNAPSHOT_DPI, clip=tb)
        rel = f"snapshots/{sid}.png"
        (out_snap_dir / f"{sid}.png").write_bytes(png)
        assets.append(SnapshotAsset(sid=sid, kind="table", rel_path=rel))
    return assets, counter


# ------------------ HTML builders ------------------
def escape_html(s: str) -> str:
    s = s or ""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))

def safe_replace(prompt: str, mapping: Dict[str, str]) -> str:
    out = prompt
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out

def inject_sections_into_template(template_html: str, sections_html: str) -> str:
    marker = '<!-- Step1: The model generates <section class="slide" ...> here. -->'
    if marker in template_html:
        return template_html.replace(marker, marker + "\n" + sections_html + "\n")
    m = re.search(r'(<div class="deck"\s+id="deck"\s*>\s*)', template_html, flags=re.I)
    if not m:
        raise RuntimeError("Cannot find deck injection point.")
    pos = m.end(1)
    return template_html[:pos] + "\n" + sections_html + "\n" + template_html[pos:]

def build_step1_section(slide_id: str, title: str, body_html: str, assets: List[SnapshotAsset]) -> str:
    fig_boxes = []
    for a in assets:
        fig_boxes.append(f"""<div class="figure-box" data-snapshot-id="{a.sid}" data-kind="{a.kind}">
  <div class="figure-head">
    <div class="figure-title">Snapshot</div>
    <div class="figure-badge">{escape_html(a.kind)}</div>
  </div>
  <div class="figure-body">
    <img class="snapshot-img" src="{escape_html(a.rel_path)}" alt="{escape_html(a.sid)}"/>
  </div>
  <div class="figure-caption"></div>
</div>""")
    fig_html = "\n".join(fig_boxes)

    return f"""<section class="slide layout--detail-list" data-slide-id="{slide_id}">
  <header>
    <div class="title-wrap">
      <h1 class="raw-title">{escape_html(title)}</h1>
      <div class="subtitle"></div>
    </div>
    <div class="tags"></div>
  </header>

  <main>
    <div class="pane text-pane">
      <div class="raw-body">
        <!--RAW_BODY_START-->
{body_html}
        <!--RAW_BODY_END-->
      </div>
    </div>

    <div class="pane fig-pane">
      <div class="fig-grid">
        <!--SNAPSHOT_GRID_START-->
{fig_html}
        <!--SNAPSHOT_GRID_END-->
      </div>
    </div>
  </main>

  <aside class="raw-notes"><pre></pre></aside>
</section>"""


def extract_step1_material(step1_html: str) -> List[Dict[str, str]]:
    sections = re.findall(r'(<section class="slide[\s\S]*?</section>)', step1_html, flags=re.I)
    out = []
    for sec in sections:
        m = re.search(r'data-slide-id="([^"]+)"', sec)
        if not m:
            continue
        sid = m.group(1).strip()
        t = ""
        mt = re.search(r'<h1[^>]*class="raw-title"[^>]*>(.*?)</h1>', sec, flags=re.S | re.I)
        if mt:
            t = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
        mb = re.search(r'<!--RAW_BODY_START-->([\s\S]*?)<!--RAW_BODY_END-->', sec)
        body_html = (mb.group(1).strip() if mb else "").strip()
        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = re.sub(r"\s+", " ", body_text).strip()

        mg = re.search(r'<!--SNAPSHOT_GRID_START-->([\s\S]*?)<!--SNAPSHOT_GRID_END-->', sec)
        snaps_html = (mg.group(1).strip() if mg else "").strip()
        snap_ids = re.findall(r'data-snapshot-id="([^"]+)"', snaps_html)
        snap_ids_json = json.dumps(snap_ids, ensure_ascii=False)
        out.append({
            "slide_id": sid,
            "title": t,
            "body_html": body_html,
            "body_text": body_text,
            "snapshots_html": snaps_html,
            "snapshot_ids_json": snap_ids_json
        })
    return out


# ------------------ JSON utilities ------------------
def strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

def extract_json_like(s: str) -> str:
    s = strip_code_fences(s)
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        return s[i:j+1]
    return s

def fix_trailing_commas(s: str) -> str:
    s = re.sub(r",\s*}", "}", s)
    s = re.sub(r",\s*]", "]", s)
    return s

def parse_strict_json(s: str) -> dict:
    cand = fix_trailing_commas(extract_json_like(s))
    return json.loads(cand)

def llm_repair_json(camel: CamelAIClient, bad: str) -> str:
    prompt = f"""Fix the following INVALID JSON into VALID STRICT JSON (double quotes, no trailing commas).
Return ONLY the JSON object, nothing else.

INVALID JSON:
{bad}
"""
    return camel.get_response(prompt, system_prompt="You are a JSON repair tool. Output only valid JSON.")


# ------------------ Steps ------------------
def run_step1(camel: CamelAIClient, out_dir: Path) -> Path:
    beamer_path = Path(BEAMER_TXT_PATH).expanduser().resolve()
    pdf_path = Path(PDF_PATH).expanduser().resolve()
    if not beamer_path.exists():
        raise SystemExit(f"[ERR] BEAMER_TXT_PATH not found: {beamer_path}")
    if not pdf_path.exists():
        raise SystemExit(f"[ERR] PDF_PATH not found: {pdf_path}")

    step1_prompt_path = Path(STEP1_BODY_PROMPT_PATH).expanduser().resolve()
    step1_tpl_path = Path(STEP1_TEMPLATE_PATH).expanduser().resolve()
    if not step1_prompt_path.exists():
        raise SystemExit(f"[ERR] Step1 prompt not found: {step1_prompt_path}")
    if not step1_tpl_path.exists():
        raise SystemExit(f"[ERR] Step1 template not found: {step1_tpl_path}")

    beamer_text = beamer_path.read_text(encoding="utf-8", errors="ignore")
    frames = extract_frames(beamer_text)
    if not frames:
        raise SystemExit("[ERR] No \\begin{frame}...\\end{frame} found in beamer input.")

    doc = fitz.open(str(pdf_path))
    pages_text = build_page_texts(doc, MAP_MAX_PAGES_SCAN)

    if USE_PAGE_MAP:
        sigs = []
        for f in frames:
            title = extract_title(f) or ""
            inner = strip_frame_wrapper(f)
            sigs.append(build_frame_signature(title, inner, MAP_BODY_TOKEN_LIMIT))
        page_map, page_scores = dp_align(sigs, pages_text)
        weak = sum(1 for s in page_scores if s < MAP_MIN_SCORE)
        print(f"[MAP] frames={len(frames)} pdf_pages={doc.page_count} weak_matches={weak}")
    else:
        page_map = list(range(len(frames)))
        page_scores = [1.0]*len(frames)
        print(f"[MAP] frames={len(frames)} pdf_pages={doc.page_count} (no alignment)")

    prompt_tpl = step1_prompt_path.read_text(encoding="utf-8", errors="ignore")
    tpl_html = step1_tpl_path.read_text(encoding="utf-8", errors="ignore")

    out_snap_dir = out_dir / "snapshots"
    out_snap_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(ONLY_FRAMES) if ONLY_FRAMES is not None else None

    sections: List[str] = []
    snap_counter = 0
    for i, frame_tex in enumerate(frames):
        if wanted is not None and i not in wanted:
            continue

        slide_id = f"s{i+1}"
        title = extract_title(frame_tex) or f"Slide {i+1}"
        inner = strip_frame_wrapper(frame_tex)

        pdf_page = page_map[i] if i < len(page_map) else -1
        score = page_scores[i] if i < len(page_scores) else 0.0

        # LLM convert body
        if DRY_RUN:
            body_html = "<p>(DRY_RUN)</p>"
        else:
            filled = safe_replace(prompt_tpl, {"SLIDE_ID": slide_id, "FRAME_LATEX": inner})
            print(f"[STEP1][LLM] frame={i} slide_id={slide_id} mapped_pdf={pdf_page} score={score:.3f}")
            resp = camel.get_response(filled, system_prompt=SYSTEM_PROMPT_STEP1)
            resp = strip_code_fences(resp)
            if PRINT_PREVIEW:
                pv = (resp or "").strip().replace("\n", " ")
                print("[STEP1][LLM] preview:", pv[:180] + ("..." if len(pv) > 180 else ""))
            body_html = (resp or "").strip()
            body_html = re.sub(r"(?is)<\/?(html|head|body|section)[^>]*>", "", body_html).strip()
            if not body_html:
                body_html = "<p></p>"

        # snapshots from PDF page
        assets: List[SnapshotAsset] = []
        if 0 <= pdf_page < doc.page_count:
            assets, snap_counter = extract_snapshots_for_page(
                doc, pdf_page, snap_counter, out_snap_dir, MAX_SNAPSHOTS_PER_SLIDE
            )
        else:
            if pdf_page != -1:
                print(f"[STEP1][WARN] pdf_page out of range: {pdf_page} / {doc.page_count}")

        sec = build_step1_section(slide_id, title, body_html, assets)
        sections.append(sec)

    step1_out = out_dir / STEP1_OUT_HTML
    final_html = inject_sections_into_template(tpl_html, "\n\n".join(sections))
    step1_out.write_text(final_html, encoding="utf-8")
    print(f"[STEP1] wrote: {step1_out}")
    return step1_out


def run_step1_5(camel: CamelAIClient, step1_html_path: Path, out_dir: Path) -> Path:
    prompt_path = Path(STEP1_5_PROMPT_PATH).expanduser().resolve()
    if not prompt_path.exists():
        raise SystemExit(f"[ERR] Step1.5 prompt not found: {prompt_path}")
    prompt_tpl = prompt_path.read_text(encoding="utf-8", errors="ignore")

    step1_html = step1_html_path.read_text(encoding="utf-8", errors="ignore")
    mats = extract_step1_material(step1_html)

    slides_plan: List[dict] = []
    raw_dir = out_dir / "debug_step1_5_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for m in mats:
        slide_id = m["slide_id"]
        filled = safe_replace(prompt_tpl, {
            "SLIDE_ID": slide_id,
            "TITLE": m["title"],
            "BODY_TEXT": m["body_text"],
            "BODY_HTML": m["body_html"],
            "SNAPSHOT_IDS": m["snapshot_ids_json"],
        })
        print(f"[STEP1.5][LLM] planning {slide_id} ...")
        resp = camel.get_response(filled, system_prompt=SYSTEM_PROMPT_STEP15)
        (raw_dir / f"{slide_id}.raw.txt").write_text(resp or "", encoding="utf-8")

        try:
            obj = parse_strict_json(resp or "")
        except Exception as e:
            print(f"[STEP1.5][WARN] parse failed for {slide_id}: {repr(e)} -> trying repair")
            repaired = llm_repair_json(camel, resp or "")
            (raw_dir / f"{slide_id}.repaired.txt").write_text(repaired or "", encoding="utf-8")
            obj = parse_strict_json(repaired or "")

        obj["slide_id"] = slide_id
        slides_plan.append(obj)

    plan = {
        "meta": {
            "deck_title": mats[0]["title"] if mats and mats[0]["title"] else "Deck",
            "design_language": "keynote_launch_event",
            "rules": {"no_empty_cards": True}
        },
        "slides": slides_plan
    }

    out_json = out_dir / STEP1_5_OUT_JSON
    out_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[STEP1.5] wrote: {out_json}")
    return out_json


def run_step2(camel: CamelAIClient, step1_html_path: Path, plan_json_path: Path, out_dir: Path) -> Path:
    prompt_path = Path(STEP2_PROMPT_PATH).expanduser().resolve()
    if not prompt_path.exists():
        raise SystemExit(f"[ERR] Step2 prompt not found: {prompt_path}")
    prompt_tpl = prompt_path.read_text(encoding="utf-8", errors="ignore")

    base_tpl_path = Path(STEP2_BASE_TEMPLATE_PATH).expanduser().resolve()
    if not base_tpl_path.exists():
        print(f"[STEP2][WARN] base template not found: {base_tpl_path} -> fallback to Step1 template")
        base_tpl_path = Path(STEP1_TEMPLATE_PATH).expanduser().resolve()
    base_tpl = base_tpl_path.read_text(encoding="utf-8", errors="ignore")

    step1_html = step1_html_path.read_text(encoding="utf-8", errors="ignore")
    mats_list = extract_step1_material(step1_html)
    mats = {m["slide_id"]: m for m in mats_list}

    plan = json.loads(plan_json_path.read_text(encoding="utf-8", errors="ignore"))
    slides = plan.get("slides", [])
    if not slides:
        raise SystemExit("[ERR] plan JSON has no slides.")

    raw_dir = out_dir / "debug_step2_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    sections: List[str] = []
    for sp in slides:
        slide_id = sp.get("slide_id", "")
        if slide_id not in mats:
            print(f"[STEP2][WARN] material missing for {slide_id}, skip")
            continue
        m = mats[slide_id]
        plan_json_one = json.dumps(sp, ensure_ascii=False, indent=2)

        filled = safe_replace(prompt_tpl, {
            "PLAN_JSON": plan_json_one,
            "SLIDE_ID": slide_id,
            "TITLE": m["title"],
            "BODY_HTML": m["body_html"],
            "SNAPSHOTS_HTML": m["snapshots_html"] if m["snapshots_html"] else "",
        })

        print(f"[STEP2][LLM] render {slide_id} template={sp.get('template_id','')} ...")
        resp = camel.get_response(filled, system_prompt=SYSTEM_PROMPT_STEP2)
        (raw_dir / f"{slide_id}.raw.txt").write_text(resp or "", encoding="utf-8")

        sec = strip_code_fences(resp or "")
        msec = re.search(r"(<section[\s\S]*?</section>)", sec, flags=re.I)
        if not msec:
            print(f"[STEP2][WARN] {slide_id}: no <section> found, fallback to Step1 section")
            m_fallback = re.search(rf'(<section class="slide[\s\S]*?data-slide-id="{re.escape(slide_id)}"[\s\S]*?</section>)',
                                   step1_html, flags=re.I)
            sec_out = m_fallback.group(1) if m_fallback else ""
        else:
            sec_out = msec.group(1).strip()

        sections.append(sec_out)

    step2_out = out_dir / STEP2_OUT_HTML
    final_html = inject_sections_into_template(base_tpl, "\n\n".join(sections))
    step2_out.write_text(final_html, encoding="utf-8")
    print(f"[STEP2] wrote: {step2_out}")
    return step2_out


def main() -> None:
    out_dir = Path(OUT_DIR).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    camel = CamelAIClient()

    step1_out = run_step1(camel, out_dir)
    plan_out = run_step1_5(camel, step1_out, out_dir)
    run_step2(camel, step1_out, plan_out, out_dir)


if __name__ == "__main__":
    main()
