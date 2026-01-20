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
STEP1_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step1_prompt_beamertext_v8_keynote_mathlayout.txt")
STEP1_TEMPLATE_PATH = str(BASE_DIR / "html_diedai" / "step1_template_step1_beamertext_v7.html")

STEP1_5_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step1_5_planner_prompt_v15_images_keynote_layout.json.txt")

# --- Step2 prompts: dynamic shell + per-slide (avoid truncation)
STEP2_SHELL_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step2_shell_prompt_v5_css_only_keynote_layout.txt")
STEP2_SLIDE_PROMPT_PATH = str(BASE_DIR / "html_diedai" / "step2_slide_prompt_v3_dynamic_per_slide_keynote_layout.txt")

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

def strip_code_fences(s: str) -> str:
    """Remove surrounding Markdown code fences like ```html ... ``` and return plain content."""
    if not s:
        return ""
    s = s.strip()
    blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", s)
    if blocks:
        s = "\n\n".join([b.strip() for b in blocks if b.strip()])
        return s.strip()
    s = re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

# ---------- Post-process helpers (robustify output; avoid raw LaTeX / ugly bullets) ----------
_SUBS = str.maketrans({"0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉"})

def _script_letter(ch: str) -> str:
    # Unicode script letters for common mathcal; fallback to original.
    return {"D":"𝒟", "G":"𝒢"}.get(ch, ch)

def _clean_math_content(s: str) -> str:
    s = s.strip()
    # common macros
    s = re.sub(r"\\mathcal\{([A-Za-z])\}", lambda m: _script_letter(m.group(1)), s)
    s = re.sub(r"\\times", "×", s)
    s = re.sub(r"\\leq|\\le", "≤", s)
    s = re.sub(r"\\geq|\\ge", "≥", s)
    s = re.sub(r"\\approx", "≈", s)
    # remove remaining backslashes/braces (we do not render LaTeX)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\", "")
    
    # subscripts like G_1 or 𝒢_1
    s = re.sub(r"([A-Za-z𝒟𝒢])_([0-9])", lambda m: m.group(1) + m.group(2).translate(_SUBS), s)
    # normalize spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s

def sanitize_math_in_html(html: str) -> str:
    # Convert \(...\), \[...\], $...$ into <span class="math">...</span>
    def repl_math(inner: str) -> str:
        return f'<span class="math">{_clean_math_content(inner)}</span>'

    html = re.sub(r"\\\((.*?)\\\)", lambda m: repl_math(m.group(1)), html, flags=re.S)
    html = re.sub(r"\\\[(.*?)\\\]", lambda m: repl_math(m.group(1)), html, flags=re.S)
    html = re.sub(r"\$\$(.*?)\$\$", lambda m: repl_math(m.group(1)), html, flags=re.S)
    html = re.sub(r"\$(.+?)\$", lambda m: repl_math(m.group(1)), html, flags=re.S)

    # Standalone \mathcal{X} occurrences not wrapped
    html = re.sub(r"\\mathcal\{([A-Za-z])\}", lambda m: repl_math(m.group(1)), html)

    return html

def strip_li_leading_markers(html: str) -> str:
    # Remove leading bullet/arrow symbols in <li> content.
    return re.sub(r"(<li\b[^>]*>)\s*(?:[•\-*→➜➤]+\s*)+", r"\1", html)

def collapse_consecutive_dividers(html: str) -> str:
    # Remove consecutive dividers at HTML level (CSS also guards this).
    return re.sub(r"(?:<div\s+class=\"divider\"\s*>\s*</div>\s*){2,}", '<div class="divider"></div>', html, flags=re.I)

def postprocess_html(html: str) -> str:
    html = sanitize_math_in_html(html)
    html = strip_li_leading_markers(html)
    html = collapse_consecutive_dividers(html)
    return html


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


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def build_shell_html(deck_title: str, css_text: str, design_spec: str) -> str:
    """Build a complete, safe shell HTML around LLM-provided CSS.

    Visual language stays dynamic (css_text comes from the model),
    but HTML/JS is deterministic so the deck renders even when model output is truncated.
    """
    marker = "<!-- SLIDES_INJECT_HERE -->"

    js = r"""
(function(){
  function clamp(n, a, b){ return Math.max(a, Math.min(b, n)); }
  function slides(){ return Array.from(document.querySelectorAll('section.slide')); }

  function fitOne(el){
    const min = parseFloat(el.getAttribute('data-fit-min') || '14');
    let size = parseFloat(el.getAttribute('data-fit-max') || getComputedStyle(el).fontSize || '24');
    el.style.fontSize = size + 'px';
    const tooBig = () => (el.scrollWidth > el.clientWidth + 1) || (el.scrollHeight > el.clientHeight + 1);
    let guard = 250;
    while(tooBig() && size > min && guard-- > 0){
      size -= 1;
      el.style.fontSize = size + 'px';
    }
  }
  function fitAll(){
    const els = Array.from(document.querySelectorAll('[data-fit]'));
    for(const el of els) fitOne(el);
  }

  let idx = 0;
  function show(i){
    const ss = slides();
    if(!ss.length) return;
    idx = clamp(i, 0, ss.length - 1);
    ss.forEach((s,k)=> s.classList.toggle('is-active', k===idx));
    const cur = document.getElementById('curSlide');
    const tot = document.getElementById('totalSlides');
    const bar = document.getElementById('progressBar');
    if(cur) cur.textContent = String(idx+1);
    if(tot) tot.textContent = String(ss.length);
    if(bar) bar.style.width = ((idx+1)/ss.length*100).toFixed(1)+'%';
    requestAnimationFrame(()=>fitAll());
  }
  function next(){ show(idx+1); }
  function prev(){ show(idx-1); }

  document.addEventListener('keydown', (e)=>{
    if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' '){ e.preventDefault(); next(); }
    if(e.key==='ArrowLeft'||e.key==='PageUp'){ e.preventDefault(); prev(); }
  });
  const btnPrev = document.getElementById('btnPrev');
  const btnNext = document.getElementById('btnNext');
  if(btnPrev) btnPrev.addEventListener('click', prev);
  if(btnNext) btnNext.addEventListener('click', next);

  window.addEventListener('load', ()=>{ show(0); fitAll(); });
  window.addEventListener('resize', ()=>{ fitAll(); });
})();
"""

    design_comment = f"<!-- DESIGN_SPEC_BEGIN\n{(design_spec or '').strip()}\nDESIGN_SPEC_END -->" if design_spec else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>{html_escape(deck_title)}</title>
  <style>
{css_text}
  
  </style>
  {design_comment}
</head>
<body>
  <div class="deck-root">
    <div class="stage">
{marker}
    </div>
    <div class="controls">
      <button id="btnPrev" class="btn">←</button>
      <div class="counter"><span id="curSlide">1</span>/<span id="totalSlides">1</span></div>
      <button id="btnNext" class="btn">→</button>
    </div>
    <div class="progress"><div id="progressBar" class="progress-bar"></div></div>
  </div>
  <script>
{js}
  </script>
</body>
</html>"""

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

    # Step2-A: shell theme (split generation to avoid truncation)
    shell_prompt = read_text(str(shell_prompt_path))

    # Keep Step2-A input small: only outline + a compact meta snippet from plan (optional)
    # (Passing the whole plan can push the model into long outputs and truncation.)
    meta_hint = ""
    mt = re.search(r'"deck_title"\s*:\s*"([^"]+)"', plan_text)
    if mt:
        meta_hint += f'DECK_TITLE="{mt.group(1)}"\n'
    meta_hint += f"NUM_SLIDES={len(slides)}\n"

    user_input_shell = (
        meta_hint
        + "OUTLINE:\n"
        + outline_text
        + "\n\n"
        + "Output format requirement: CSS-only or <style> block + DESIGN_SPEC (no full HTML).\n"
    )

    def _need_more_css(s: str) -> bool:
        # If model starts a <style> but doesn't close it, it's truncated.
        has_open = bool(re.search(r"<style[^>]*>", s, re.I))
        has_close = bool(re.search(r"</style>", s, re.I))
        return has_open and (not has_close)

    def _append_continuation(prev: str) -> str:
        tail = prev[-800:]
        cont_user = (
            "Your previous output was truncated.\n"
            "Continue EXACTLY from where it ended. Do NOT repeat earlier text.\n"
            "Output ONLY the remaining text, until you have closed </style> and the DESIGN_SPEC_END marker.\n"
            f"PREVIOUS_TAIL:\n{tail}\n"
        )
        return camel.get_response(cont_user, system_prompt=shell_prompt)

    print("[STEP2][LLM] generating shell theme (CSS-only) ...")
    shell_resp = camel.get_response(user_input_shell, system_prompt=shell_prompt)
    shell_resp = strip_code_fences(shell_resp).strip()

    # Continuation stitching (up to 2 times) if style block is truncated
    for _ in range(2):
        if _need_more_css(shell_resp):
            print("[STEP2][WARN] shell CSS truncated; requesting continuation ...")
            shell_resp += "\n" + strip_code_fences(_append_continuation(shell_resp)).strip()
        else:
            break

    # Extract css + design_spec; if no <style>, treat whole as css.
    title_m = re.search(r"<title>(.*?)</title>", shell_resp, re.I | re.S)
    deck_title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else (mt.group(1) if mt else "Keynote Deck")
    style_m = re.search(r"<style[^>]*>([\s\S]*?)</style>", shell_resp, re.I)
    css_text = style_m.group(1).strip() if style_m else shell_resp.strip()

    design_spec = extract_design_spec(shell_resp)
    if not design_spec:
        # Minimal fallback spec for per-slide renderer (keeps pipeline running)
        design_spec = """design_language: keynote_launch_event
component_classes: slide, stage, hero, subtitle, chip, chips, callout-row, callout-pill, callout-line, card, card-title, bullets, media-card, media-img, media-meta, stat, kpi, math, divider, grid-2col, grid-3col, runway, step, watermark
notes:
- bullets marker is ONLY ONE: arrow
- callout pills must be FIT-CONTENT
- divider must be SINGLE line
- math uses inline span.math
- kpi highlights only for span.kpi
"""

    # Build deterministic shell HTML so we always have a complete file
    shell_html = build_shell_html(deck_title=deck_title, css_text=css_text, design_spec=design_spec)
    (out_dir / "step2_shell.html").write_text(shell_html, encoding="utf-8")
    print("[STEP2] wrote shell: " + str(out_dir / "step2_shell.html"))

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
        resp = camel.get_response(user_input_slide, system_prompt=slide_prompt)
        resp2 = strip_code_fences(resp)
        sm = re.search(r"<section\b[\s\S]*?</section>", resp2, re.I)
        if not sm:
            dbg = out_dir / f"step2_slide_{sid}.raw.txt"
            dbg.write_text(resp2, encoding="utf-8")
            raise RuntimeError(f"Slide render failed for {sid}. See {dbg}")
        slide_section = postprocess_html(sm.group(0).strip())
        rendered.append(slide_section)
        print(f"[STEP2] slide {i+1}/{len(slides)} ok: {sid}")

    final_html = inject_slides_into_shell(shell_html, "\n\n".join(rendered))
    final_html = postprocess_html(final_html)
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

    # Step2 prompts
    step2_shell_prompt = Path(STEP2_SHELL_PROMPT_PATH).expanduser().resolve()
    step2_slide_prompt = Path(STEP2_SLIDE_PROMPT_PATH).expanduser().resolve()
    for p in [step2_shell_prompt, step2_slide_prompt]:
        if not p.exists():
            raise FileNotFoundError(f"Missing Step2 prompt: {p}")

    # Step2
    run_step2(step1_html_with_imgs, plan_json_path, out_dir, step2_shell_prompt, step2_slide_prompt)

if __name__ == "__main__":
    main()
