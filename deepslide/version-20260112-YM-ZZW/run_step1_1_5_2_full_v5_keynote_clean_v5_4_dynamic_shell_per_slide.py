#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end pipeline: Step1 (beamer -> raw HTML with figure placeholders + auto snapshots)
                     Step1.5 (plan JSON)
                     Step2 (render keynote-style HTML)

Key goals vs previous versions:
- Step1 uses a single, clean raw extractor template (no "two snapshot boxes").
- Figures/tables are represented only once (raw-figure -> injected <img>).
- Step1.5 / Step2 are image-aware via `visuals` elements in plan JSON.

This script assumes your repo provides:
- ppt_requirements_collector.CamelAIClient with get_response(user_input, system_prompt=...)
"""

from __future__ import annotations
from pathlib import Path
import re
import json
import html
from typing import List, Dict, Tuple, Optional

# ---------- CONFIG (edit here only) ----------
BASE_DIR = Path(__file__).resolve().parent

# Step1 inputs
BEAMER_TXT_PATH = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/content.txt"     # "/abs/path/to/beamer.txt"
PDF_PATH        = r"/home/ym/DeepSlide/deepslide/version-20260112-YM-ZZW/base.pdf"     # "/abs/path/to/rendered.pdf"

# Prompts / templates (assume this .py and html_diedai/ are in the same directory)
STEP1_PROMPT_PATH   = str(BASE_DIR / "html_diedai" / "step1_prompt_beamertext_v7_keynote_clean.txt")
STEP1_TEMPLATE_PATH = str(BASE_DIR / "html_diedai" / "step1_template_step1_beamertext_v7.html")

STEP1_5_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step1_5_planner_prompt_v13_images_keynote.txt")

# --- Step2 prompts: dynamic shell + per-slide (avoid truncation)
STEP2_SHELL_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step2_shell_prompt_v1_dynamic.txt")
STEP2_SLIDE_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step2_slide_prompt_v1_dynamic_per_slide.txt")

# Outputs
OUT_DIR = str(BASE_DIR / "html_outputs")
STEP1_OUT_HTML   = "step1_generated.html"
STEP1_5_OUT_JSON = "step1_5_plan.json"
STEP2_OUT_HTML   = "step2_visual_deck.html"
SNAP_DIR_NAME    = "snapshots"  # under OUT_DIR

# Page mapping (only affects screenshot page selection; NOT the LLM output)
USE_PAGE_MAP = True
MAP_MAX_PAGES_SCAN = 800
MAP_MIN_SCORE = 0.08
MAP_BODY_TOKEN_LIMIT = 120  # raise if PDF has many extra pages or titles are weak

# Snapshot extraction
SNAP_MAX_PER_SLIDE = 3  # if a slide has multiple figures, take up to K image-blocks; fallback to full page
SNAP_DPI = 180

# ---------- helpers ----------
def read_text(p: str) -> str:
    return Path(p).read_text(encoding="utf-8", errors="ignore")

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", s)

def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)

def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def tokenize(s: str) -> List[str]:
    s = norm_ws(s).lower()
    # keep letters/numbers as tokens
    return re.findall(r"[a-z0-9]+", s)

def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

# ---------- Step0: split beamer text into frames ----------


def split_frames(beamer_txt: str) -> List[Dict]:
    """
    Expected beamer.txt style:
    - frames separated by lines like:  === Frame ===  or '--- frame ---'
    The older debug scripts handled multiple formats; this is a robust heuristic:
    - split by '\n\\begin{frame}' if present; else by 'FRAME:' markers; else by '---' blocks.
    """
    txt = beamer_txt

    # Prefer LaTeX-like frames
    if "\\begin{frame" in txt:
        parts = re.split(r"\\begin\{frame\}", txt)
        frames = []
        for part in parts[1:]:
            body = part.split("\\end{frame}", 1)[0]
            title_m = re.search(r"\\frametitle\{([^}]*)\}", body)
            title = title_m.group(1).strip() if title_m else ""
            frames.append({"title": title, "body": body.strip()})
        return frames

    # Generic marker-based fallback
    seps = re.split(r"\n-{3,}\n|\n={3,}\n|\n\\s*FRAME\\s*\\d+\\s*\\n", txt)
    frames = []
    for part in seps:
        part = part.strip()
        if not part:
            continue
        # attempt to grab first line as title if short
        lines = [l.strip() for l in part.splitlines() if l.strip()]
        title = ""
        body = part
        if lines and len(lines[0]) <= 80 and not lines[0].startswith("\\"):
            title = lines[0]
            body = "\n".join(lines[1:]).strip()
        frames.append({"title": title, "body": body})
    return frames

# ---------- Page mapping: frame -> pdf page ----------
def pdf_page_texts(pdf_path: str, max_pages: int) -> List[str]:
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    n = min(doc.page_count, max_pages)
    out = []
    for i in range(n):
        page = doc.load_page(i)
        t = page.get_text("text") or ""
        out.append(t)
    doc.close()
    return out

def map_frames_to_pages(frames: List[Dict], pdf_pages_text: List[str]) -> Tuple[List[int], List[float], int]:
    """
    Map each frame to best-matching page index (0-based).
    Returns: page_idx_list, score_list, weak_matches_count
    """
    page_tokens = [tokenize(t) for t in pdf_pages_text]
    mapped = []
    scores = []
    weak = 0
    for fr in frames:
        title = fr.get("title", "")
        body = fr.get("body", "")
        q = " ".join([title, body])
        q_tokens = tokenize(q)
        if MAP_BODY_TOKEN_LIMIT > 0:
            q_tokens = q_tokens[:MAP_BODY_TOKEN_LIMIT]
        best_i, best_s = 0, 0.0
        for i, pt in enumerate(page_tokens):
            s = jaccard(q_tokens, pt)
            if s > best_s:
                best_s = s
                best_i = i
        mapped.append(best_i)
        scores.append(best_s)
        if best_s < MAP_MIN_SCORE:
            weak += 1
    return mapped, scores, weak

# ---------- Snapshot extraction ----------
def extract_image_bboxes(page) -> List[Tuple[float,float,float,float]]:
    """
    Return bounding boxes of image blocks (type==1) from page.get_text("dict").
    """
    try:
        d = page.get_text("dict")
        bbs = []
        for b in d.get("blocks", []):
            if b.get("type") == 1 and "bbox" in b:
                x0,y0,x1,y1 = b["bbox"]
                area = max(0.0, (x1-x0)) * max(0.0, (y1-y0))
                # filter tiny icons/logos
                if area > 8_000:
                    bbs.append((x0,y0,x1,y1))
        # sort by area desc
        bbs.sort(key=lambda r: (r[2]-r[0])*(r[3]-r[1]), reverse=True)
        return bbs
    except Exception:
        return []

def save_clip(page, rect, out_path: Path, dpi: int):
    import fitz
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat, clip=fitz.Rect(rect))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_path))

def save_full(page, out_path: Path, dpi: int):
    import fitz
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_path))

def inject_snapshots_into_step1(step1_html: str, snap_relpaths_by_slide: Dict[str, List[str]]) -> str:
    """
    Replace each <figure class="raw-figure"...>...</figure> with an <img> inside it (if snapshot exists),
    without adding any extra figure boxes elsewhere.
    """
    # parse per slide id
    def repl_slide(m):
        slide_id = m.group("sid")
        inner = m.group("inner")
        snaps = snap_relpaths_by_slide.get(slide_id, [])
        idx = 0

        def repl_fig(fm):
            nonlocal idx
            fig = fm.group(0)
            snap = snaps[idx] if idx < len(snaps) else ""
            idx += 1
            # insert <img> before figcaption
            if snap:
                if "<figcaption" in fig:
                    fig = re.sub(r"(<figcaption[^>]*>)", f'<img class="raw-img" src="{html.escape(snap)}" alt="snapshot"/>\n\\1', fig, count=1, flags=re.S)
                else:
                    fig = fig.replace("</figure>", f'\n<img class="raw-img" src="{html.escape(snap)}" alt="snapshot"/>\n</figure>')
            return fig

        inner2 = re.sub(r"<figure\s+class=['\"]raw-figure['\"][^>]*>.*?</figure>", repl_fig, inner, flags=re.S)
        return f'<section class="slide" data-slide-id="{slide_id}">{inner2}</section>'

    # First, normalize: ensure we have <section ...> ... </section> style with slide-id.
    # Our template uses <section class="slide" ...> directly; use robust pattern.
    slide_pat = re.compile(r"<section\s+class=['\"]slide[^'\"]*['\"]\s+data-slide-id=['\"](?P<sid>s\d+)['\"]\s*>(?P<inner>.*?)</section>", re.S)
    return slide_pat.sub(repl_slide, step1_html)

# ---------- JSON extraction / repair ----------
def extract_json_obj(s: str) -> Optional[dict]:
    """
    Extract first top-level JSON object from a string. Returns dict or None.
    """
    if not s:
        return None
    # common: model outputs ```json ... ```
    s2 = re.sub(r"```(?:json)?", "", s, flags=re.I).replace("```", "")
    # find first '{' and last '}'
    i = s2.find("{")
    j = s2.rfind("}")
    if i < 0 or j < 0 or j <= i:
        return None
    cand = s2[i:j+1].strip()
    try:
        return json.loads(cand)
    except Exception:
        return None

def repair_json_with_llm(camel, broken_text: str) -> str:
    repair_prompt = (
        "You are a JSON repair tool. Convert the input into VALID STRICT JSON only. "
        "No markdown, no commentary. Keep the same structure and keys; fix missing commas/quotes/brackets."
    )
    return camel.get_response(broken_text, system_prompt=repair_prompt)

# ---------- main steps ----------
def run_step1(frames: List[Dict], pdf_path: str, out_dir: Path, step1_prompt: str, step1_template: str) -> Path:
    from ppt_requirements_collector import CamelAIClient  # keep consistent with your repo
    camel = CamelAIClient()

    # mapping
    mapped_pages = [0] * len(frames)
    scores = [0.0] * len(frames)
    weak = 0
    if USE_PAGE_MAP and pdf_path and Path(pdf_path).exists():
        pages_text = pdf_page_texts(pdf_path, MAP_MAX_PAGES_SCAN)
        mapped_pages, scores, weak = map_frames_to_pages(frames, pages_text)
        print(f"[MAP] frames={len(frames)} pdf_pages={len(pages_text)} weak_matches={weak}")

    # per-frame LLM: output <section ...>
    sections = []
    for i, fr in enumerate(frames):
        slide_id = f"s{i+1}"
        title = fr.get("title","").strip()
        body = fr.get("body","").strip()
        mapped_pdf = mapped_pages[i] if i < len(mapped_pages) else 0
        score = scores[i] if i < len(scores) else 0.0

        user_input = (
            f"slide_id: {slide_id}\n"
            f"frame_title: {title}\n"
            f"mapped_pdf_page_index_0based: {mapped_pdf}\n"
            f"frame_body:\n{body}\n"
        )
        print(f"[STEP1][LLM] frame={i} slide_id={slide_id} mapped_pdf={mapped_pdf+1} score={score:.3f}")
        resp = camel.get_response(user_input, system_prompt=step1_prompt).strip()
        # minimal guard: ensure section wrapper exists
        if "<section" not in resp:
            resp = f'<section class="slide" data-slide-id="{slide_id}"><h1 class="raw-title">{html.escape(title or slide_id)}</h1><div class="raw-body"><p>{html.escape(resp)}</p></div><aside class="raw-notes"></aside></section>'
        sections.append(resp)

    # inject into template
    if "<!-- SLIDES_INJECT_HERE -->" not in step1_template:
        raise RuntimeError("Step1 template missing <!-- SLIDES_INJECT_HERE --> marker.")
    deck_html = step1_template.replace("<!-- SLIDES_INJECT_HERE -->", "\n\n".join(sections))

    step1_out = out_dir / STEP1_OUT_HTML
    write_text(step1_out, deck_html)
    print(f"[STEP1] wrote: {step1_out}")
    return step1_out

def run_snapshots(step1_html_path: Path, pdf_path: str, out_dir: Path, frames_to_pages: List[int]) -> Path:
    """
    Create snapshot PNGs from PDF and inject <img> into raw-figure tags in step1 HTML.
    """
    import fitz
    if not Path(pdf_path).exists():
        print("[SNAP] pdf not found, skip snapshot injection.")
        return step1_html_path

    html0 = read_text(str(step1_html_path))

    # collect slide ids and figure counts per slide
    slide_pat = re.compile(r"<section\s+class=['\"]slide[^'\"]*['\"]\s+data-slide-id=['\"](?P<sid>s\d+)['\"][^>]*>(?P<inner>.*?)</section>", re.S)
    fig_pat = re.compile(r"<figure\s+class=['\"]raw-figure['\"][^>]*>.*?</figure>", re.S)

    slides = []
    for m in slide_pat.finditer(html0):
        sid = m.group("sid")
        inner = m.group("inner")
        figs = fig_pat.findall(inner)
        slides.append((sid, len(figs)))

    doc = fitz.open(pdf_path)
    snap_dir = out_dir / SNAP_DIR_NAME
    snap_dir.mkdir(parents=True, exist_ok=True)

    snap_relpaths_by_slide: Dict[str, List[str]] = {}

    for idx, (sid, fig_cnt) in enumerate(slides):
        if fig_cnt <= 0:
            continue
        page_idx = frames_to_pages[idx] if idx < len(frames_to_pages) else min(idx, doc.page_count-1)
        if page_idx < 0 or page_idx >= doc.page_count:
            page_idx = min(max(0, page_idx), doc.page_count-1)

        page = doc.load_page(page_idx)
        bbs = extract_image_bboxes(page)
        use_n = min(fig_cnt, SNAP_MAX_PER_SLIDE, len(bbs))

        rels = []
        # save cropped image blocks first
        for k in range(use_n):
            rect = bbs[k]
            out_name = f"{sid}_fig{k+1}_p{page_idx+1}.png"
            out_path = snap_dir / out_name
            save_clip(page, rect, out_path, dpi=SNAP_DPI)
            rels.append(f"{SNAP_DIR_NAME}/{out_name}")

        # if not enough image blocks, fallback to full page for remaining
        for k in range(use_n, fig_cnt):
            out_name = f"{sid}_full_p{page_idx+1}_{k+1}.png"
            out_path = snap_dir / out_name
            save_full(page, out_path, dpi=SNAP_DPI)
            rels.append(f"{SNAP_DIR_NAME}/{out_name}")

        snap_relpaths_by_slide[sid] = rels

    doc.close()

    html1 = inject_snapshots_into_step1(html0, snap_relpaths_by_slide)
    step1_injected = out_dir / ("step1_generated_with_imgs.html")
    write_text(step1_injected, html1)
    print(f"[SNAP] injected images into: {step1_injected}")
    return step1_injected

def run_step1_5(step1_html_path: Path, out_dir: Path, step1_5_prompt: str) -> Path:
    """
    Step1.5: ask LLM to produce a planning JSON.

    IMPORTANT (passthrough-friendly):
    - We ALWAYS save the raw model output into step1_5_plan.json (even if it is not strict JSON).
    - We will TRY to parse it; if parsing succeeds, we also save step1_5_plan.strict.json.
    - We DO NOT raise / stop the pipeline due to JSON formatting issues.
    """
    from ppt_requirements_collector import CamelAIClient
    camel = CamelAIClient()

    step1_html = read_text(str(step1_html_path))
    user_input = (
        "You will receive step1_generated.html below. Plan every slide.\n"
        "The plan is preferred to be STRICT JSON, but if you fail, output a single JSON-like object only.\n\n"
        "=== step1_generated.html ===\n"
        f"{step1_html}\n"
    )
    print("[STEP1.5][LLM] planning deck ...")
    resp = camel.get_response(user_input, system_prompt=step1_5_prompt).strip()

    # Always write raw output (use .json suffix for downstream convenience)
    json_path = out_dir / STEP1_5_OUT_JSON
    write_text(json_path, resp)
    print(f"[STEP1.5] wrote (raw maybe-non-strict): {json_path}")

    # Also keep a debug raw copy
    raw_path = out_dir / "step1_5_plan.raw.txt"
    write_text(raw_path, resp)

    # Best-effort strict JSON dump (optional)
    try:
        obj = extract_json_obj(resp)
        if obj is not None:
            strict_path = out_dir / "step1_5_plan.strict.json"
            write_text(strict_path, json.dumps(obj, ensure_ascii=False, indent=2))
            print(f"[STEP1.5] wrote strict: {strict_path}")
            return strict_path
    except Exception as e:
        print("[STEP1.5][WARN] JSON parse failed (will passthrough raw to Step2):", repr(e))

    return json_path

def extract_step1_sections(step1_html: str) -> list[dict]:
    sections: list[dict] = []
    for m in re.finditer(r'(<section\b[^>]*\bdata-slide-id="([^"]+)"[^>]*>[\s\S]*?</section>)', step1_html, re.I):
        sec_html = m.group(1)
        sid = m.group(2)
        tm = re.search(r'<h1[^>]*class="raw-title"[^>]*>(.*?)</h1>', sec_html, re.I | re.S)
        title = re.sub(r"<[^>]+>", "", tm.group(1)).strip() if tm else ""
        sections.append({"slide_id": sid, "html": sec_html, "title": title})
    return sections

def inject_slides_into_shell(shell_html: str, slides_html: str) -> str:
    marker = "<!-- SLIDES_INJECT_HERE -->"
    if marker not in shell_html:
        raise RuntimeError(f"Shell HTML missing marker {marker}")
    return shell_html.replace(marker, slides_html)

def extract_design_spec(shell_html: str) -> str:
    m = re.search(r"<!--\s*DESIGN_SPEC_BEGIN([\s\S]*?)DESIGN_SPEC_END\s*-->", shell_html, re.I)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"<style>([\s\S]*?)</style>", shell_html, re.I)
    style = (m2.group(1).strip() if m2 else "")[:2000]
    return (
        "design_language: unknown\n"
        "component_classes: slide, hero, card, grid-2col, bullets, media-card, chip, stat, runway\n"
        "notes: follow shell typography and spacing\n"
        "style_excerpt:\n" + style
    )

def run_step2(step1_html_path: Path, plan_path: Path, out_dir: Path, shell_prompt_path: Path, slide_prompt_path: Path) -> Path:
    """
    Dynamic shell (LLM once) + per-slide sections (LLM per slide).
    Avoids truncation while keeping style flexible (no local static template).
    """
    from ppt_requirements_collector import CamelAIClient
    camel = CamelAIClient()

    step1_html = read_text(str(step1_html_path))
    plan_text = read_text(str(plan_path))

    slides = extract_step1_sections(step1_html)
    if not slides:
        raise RuntimeError("No <section ... data-slide-id> found in Step1 HTML.")

    outline_text = "\n".join([f"{i+1}. {(s['title'] or s['slide_id'])}" for i, s in enumerate(slides)])

    shell_prompt = read_text(str(shell_prompt_path))
    slide_prompt = read_text(str(slide_prompt_path))

    # Step2-A: shell
    user_input_shell = (
        "Generate deck shell HTML only.\n\n"
        "=== step1_5_plan (raw) ===\n" + plan_text + "\n\n"
        "=== step1_outline (titles) ===\n" + outline_text + "\n"
    )
    shell_resp = camel.get_response(user_input_shell, shell_prompt)
    shell_resp = strip_code_fences(shell_resp)
    docm = re.search(r"<!DOCTYPE html>[\s\S]*</html>", shell_resp, re.I)
    if not docm:
        dbg = out_dir / "step2_shell.raw.txt"
        dbg.write_text(shell_resp, encoding="utf-8")
        raise RuntimeError(f"Shell generation failed. See {dbg}")
    shell_html = docm.group(0).strip()
    (out_dir / "step2_shell.html").write_text(shell_html, encoding="utf-8")

    design_spec = extract_design_spec(shell_html)

    # Step2-B: per-slide
    rendered = []
    print(f"[STEP2] dynamic shell + per-slide render: {len(slides)} slides ...")
    for i, s in enumerate(slides):
        sid = s["slide_id"]
        user_input_slide = (
            f"SLIDE_ID={sid}\n\n"
            "=== DESIGN_SPEC ===\n" + design_spec + "\n\n"
            "=== step1_5_plan (raw) ===\n" + plan_text + "\n\n"
            "=== step1_slide_html ===\n" + s["html"] + "\n"
        )
        resp = camel.get_response(user_input_slide, slide_prompt)
        resp2 = strip_code_fences(resp)
        sm = re.search(r"<section\b[\s\S]*?</section>", resp2, re.I)
        if not sm:
            dbg = out_dir / f"step2_slide_{sid}.raw.txt"
            dbg.write_text(resp2, encoding="utf-8")
            raise RuntimeError(f"Slide render failed for {sid}. See {dbg}")
        rendered.append(sm.group(0).strip())
        print(f"[STEP2] slide {i+1}/{len(slides)} ok: {sid}")

    final_html = inject_slides_into_shell(shell_html, "\n\n".join(rendered))
    out_path = out_dir / STEP2_OUT_HTML
    out_path.write_text(final_html, encoding="utf-8")
    print(f"[STEP2] wrote: {out_path}")
    return out_path

def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    beamer_txt = read_text(BEAMER_TXT_PATH)
    frames = split_frames(beamer_txt)
    if not frames:
        raise RuntimeError("No frames found in BEAMER_TXT_PATH.")

    step1_prompt = read_text(STEP1_PROMPT_PATH)
    step1_template = read_text(STEP1_TEMPLATE_PATH)

    # Step1
    step1_html_path = run_step1(frames, PDF_PATH, out_dir, step1_prompt, step1_template)

    # mapping again for snapshots (we reuse the same mapping computed inside run_step1)
    # simplest: recompute here to avoid coupling
    frames_to_pages = [0]*len(frames)
    if USE_PAGE_MAP and PDF_PATH and Path(PDF_PATH).exists():
        pages_text = pdf_page_texts(PDF_PATH, MAP_MAX_PAGES_SCAN)
        frames_to_pages, _, _ = map_frames_to_pages(frames, pages_text)

    # Snapshot injection -> new Step1 HTML (with imgs)
    step1_html_with_imgs = run_snapshots(step1_html_path, PDF_PATH, out_dir, frames_to_pages)

    # Step1.5
    step1_5_prompt = read_text(STEP1_5_PROMPT_PATH)
    plan_json_path = run_step1_5(step1_html_with_imgs, out_dir, step1_5_prompt)

    # Step2
    step2_prompt = read_text(STEP2_PROMPT_PATH)
    run_step2(step1_html_with_imgs, plan_json_path, out_dir, step2_shell_prompt, step2_slide_prompt)

if __name__ == "__main__":
    main()
