import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import fitz

from app.services.core.logic_chain_budget import parse_total_minutes
from app.services.core.ppt_core import _extract_includegraphics_paths, _strip_latex_inline


_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]")
_STOP_EN = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "by",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "this",
    "that",
    "these",
    "those",
    "we",
    "you",
    "they",
    "i",
    "our",
    "your",
    "their",
}
_STOP_ZH = {"的", "了", "和", "与", "在", "对", "及", "或", "是", "我们", "你们", "他们", "它们", "一个", "一些", "以及"}


def _safe_read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read() or ""
    except Exception:
        return ""


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _tokenize(text: str) -> List[str]:
    raw = str(text or "").lower()
    toks = _TOKEN_RE.findall(raw)
    out: List[str] = []
    for t in toks:
        if len(t) <= 1 and not ("\u4e00" <= t <= "\u9fff"):
            continue
        if t in _STOP_EN or t in _STOP_ZH:
            continue
        out.append(t)
    return out


@dataclass(frozen=True)
class _Vectorizer:
    idf: Dict[str, float]

    def vec(self, text: str) -> Dict[str, float]:
        toks = _tokenize(text)
        if not toks:
            return {}
        tf = Counter(toks)
        v: Dict[str, float] = {}
        for k, c in tf.items():
            w = float(c) * float(self.idf.get(k, 0.0))
            if w:
                v[k] = w
        return v

    def cosine(self, a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        if len(a) > len(b):
            a, b = b, a
        dot = 0.0
        for k, av in a.items():
            bv = b.get(k)
            if bv is not None:
                dot += av * bv
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na <= 1e-12 or nb <= 1e-12:
            return 0.0
        return float(dot / (na * nb))


def _build_vectorizer(texts: List[str]) -> _Vectorizer:
    docs = [_tokenize(t) for t in (texts or [])]
    n = max(1, len(docs))
    df: Counter[str] = Counter()
    for toks in docs:
        df.update(set(toks))
    idf: Dict[str, float] = {}
    for t, c in df.items():
        idf[t] = math.log((n + 1.0) / (float(c) + 1.0)) + 1.0
    return _Vectorizer(idf=idf)


def _extract_title(frame: str) -> Tuple[str, str]:
    raw = str(frame or "")
    m1 = re.search(r"\\frametitle\{([\s\S]*?)\}", raw)
    m2 = re.search(r"\\framesubtitle\{([\s\S]*?)\}", raw)
    title = _strip_latex_inline(m1.group(1)) if m1 else ""
    subtitle = _strip_latex_inline(m2.group(1)) if m2 else ""
    return title, subtitle


def _frame_to_plain_text(frame: str) -> str:
    raw = str(frame or "")
    raw = re.sub(r"\\frametitle\{[\s\S]*?\}", "", raw)
    raw = re.sub(r"\\framesubtitle\{[\s\S]*?\}", "", raw)
    raw = re.sub(r"\\begin\{frame\}(\[[^\]]*\])?", "", raw)
    raw = raw.replace("\\end{frame}", "")
    return _strip_latex_inline(raw)


def _count_words(text: str) -> int:
    if not text:
        return 0
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]+", text))
    return int(zh + en)


def _estimate_speech_seconds(text: str) -> float:
    s = str(text or "").strip()
    if not s:
        return 0.0
    zh = len(re.findall(r"[\u4e00-\u9fff]", s))
    en = len(re.findall(r"[A-Za-z]+", s))
    sec_zh = zh / 3.0
    sec_en = (en / 140.0) * 60.0
    return float(sec_zh + sec_en)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    return lo if v < lo else hi if v > hi else v


def _score_legibility(min_font_pt: Optional[float], word_count: int, block_count: int) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    if not min_font_pt or min_font_pt <= 0:
        font_score = 0.4
        reasons.append("无法可靠读取字号，建议检查导出 PDF 是否正常")
    else:
        font_score = _clamp((float(min_font_pt) - 12.0) / 8.0)
        if min_font_pt < 16:
            reasons.append(f"最小字号偏小（{min_font_pt:.0f}pt），现场可能看不清")
        elif min_font_pt < 18:
            reasons.append(f"最小字号略小（{min_font_pt:.0f}pt），建议适当放大")

    word_score = 1.0 - _clamp((max(0, int(word_count) - 60)) / 120.0)
    if word_count > 140:
        reasons.append("文字信息密度过高，建议拆页或改图")
    elif word_count > 90:
        reasons.append("文字偏多，建议保留 3–5 个锚点词")

    block_score = 1.0 - _clamp((max(0, int(block_count) - 12)) / 18.0)
    if block_count > 28:
        reasons.append("元素块过多，视觉拥挤")

    score = 0.5 * font_score + 0.3 * word_score + 0.2 * block_score
    return _clamp(score), reasons[:3]


def _score_time_pace(est_sec: float, budget_sec: float) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    if budget_sec <= 1e-6:
        return 0.5, ["无法确定该页时间预算"]
    ratio = est_sec / budget_sec
    if ratio >= 1.25:
        reasons.append("预计口播超时，建议精简讲稿或拆页")
    elif ratio >= 1.1:
        reasons.append("口播略偏长，注意控制节奏")
    elif ratio <= 0.55 and est_sec > 0:
        reasons.append("口播偏短，可能缺少解释或例子")
    elif est_sec <= 0:
        reasons.append("该页缺少讲稿，彩排时可能卡壳")
    score = 1.0 - _clamp(abs(ratio - 1.0) / 0.6)
    return _clamp(score), reasons[:3]


def _score_transition(sim_prev: float, sim_next: float) -> Tuple[float, List[str]]:
    sims = [s for s in [sim_prev, sim_next] if s is not None]
    if not sims:
        return 0.5, ["无法计算转场相似度"]
    s = float(sum(sims) / len(sims))
    reasons: List[str] = []
    if s < 0.12:
        reasons.append("与相邻页语义跳跃大，建议加一句过渡或插入桥接页")
    elif s > 0.78:
        reasons.append("与相邻页内容过于相似，建议合并或突出差异点")
    score = 1.0 - _clamp(abs(s - 0.35) / 0.35)
    return _clamp(score), reasons[:2]


def _score_complementarity(sim: float, overlap: float) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    if sim >= 0.82 and overlap >= 0.7:
        reasons.append("讲稿与幻灯高度重复，有“照读”风险")
    if sim <= 0.12 and overlap <= 0.15:
        reasons.append("讲稿与幻灯联系较弱，听众可能抓不住锚点")
    score = 1.0 - _clamp(abs(sim - 0.5) / 0.5)
    return _clamp(score), reasons[:2]


def _score_focus_readiness(has_anchor: bool, has_actions: bool, pace_fit: float) -> Tuple[float, List[str]]:
    anchor_score = 1.0 if has_anchor else 0.1
    action_score = 1.0 if has_actions else (0.5 if has_anchor else 0.1)
    score = 0.5 * anchor_score + 0.3 * action_score + 0.2 * _clamp(pace_fit)
    reasons: List[str] = []
    if not has_anchor:
        reasons.append("缺少清晰视觉锚点，建议加一张对比图/表或高亮关键结果")
    elif not has_actions:
        reasons.append("尚未配置聚焦/强调动作，可考虑为关键区域添加视觉引导")
    return _clamp(score), reasons[:2]


def _infer_total_duration_seconds(project_record: Dict[str, Any]) -> int:
    req = project_record.get("requirements") if isinstance(project_record, dict) else None
    if not isinstance(req, dict):
        return 0
    raw = (
        req.get("total_minutes")
        or req.get("duration_minutes")
        or req.get("duration")
        or req.get("time")
        or req.get("total_time")
        or ""
    )
    mins = parse_total_minutes(str(raw), default=0)
    return int(mins) * 60 if mins > 0 else 0


def _build_time_budgets(page_types: List[str], total_duration_sec: int) -> List[float]:
    n = len(page_types)
    if n <= 0:
        return []
    if total_duration_sec <= 0:
        out: List[float] = []
        for t in page_types:
            if t == "title":
                out.append(20.0)
            elif t == "references":
                out.append(10.0)
            elif t == "section":
                out.append(12.0)
            else:
                out.append(45.0)
        return out

    weights = []
    for t in page_types:
        if t == "title":
            weights.append(0.7)
        elif t == "references":
            weights.append(0.35)
        elif t == "section":
            weights.append(0.5)
        else:
            weights.append(1.0)
    s = sum(weights) or 1.0
    return [float(total_duration_sec) * w / s for w in weights]


def _recipe_dir(project_path: str) -> str:
    r = os.path.join(project_path, "recipe")
    return r if os.path.exists(r) else project_path


def compute_preview_metrics(project_record: Dict[str, Any]) -> Dict[str, Any]:
    project_path = str((project_record or {}).get("path") or "")
    if not project_path or not os.path.isdir(project_path):
        return {"ok": False, "error": {"code": "missing_project_path", "message": "Project path not found"}}

    recipe_dir = _recipe_dir(project_path)
    pdf_path = os.path.join(recipe_dir, "base.pdf")
    if not os.path.exists(pdf_path):
        return {"ok": False, "error": {"code": "missing_base_pdf", "message": "base.pdf not found. Please compile first."}}

    content_tex_path = os.path.join(recipe_dir, "content.tex")
    speech_path = os.path.join(recipe_dir, "speech.txt")
    html_meta_path = os.path.join(recipe_dir, "html_meta.json")
    alignment_path = os.path.join(recipe_dir, "alignment_dsid.json")

    cache_path = os.path.join(recipe_dir, "preview_metrics.json")
    input_paths = [pdf_path, content_tex_path, speech_path, html_meta_path, alignment_path]
    input_mtimes: Dict[str, float] = {}
    for p in input_paths:
        try:
            input_mtimes[os.path.basename(p)] = float(os.path.getmtime(p)) if os.path.exists(p) else 0.0
        except Exception:
            input_mtimes[os.path.basename(p)] = 0.0

    cached = _safe_read_json(cache_path)
    if cached and isinstance(cached.get("_meta"), dict):
        meta = cached.get("_meta") or {}
        if (
            meta.get("version") == 1
            and isinstance(meta.get("input_mtimes"), dict)
            and dict(meta.get("input_mtimes")) == input_mtimes
            and isinstance(cached.get("data"), dict)
        ):
            return dict(cached["data"])

    content_tex = _safe_read_text(content_tex_path)
    speech_raw = _safe_read_text(speech_path)
    speech_segments = [s.strip() for s in str(speech_raw or "").split("<next>")]
    speech_segments = [s for s in speech_segments if s is not None]

    frames = [m.group(1) for m in re.finditer(r"(\\begin\{frame\}[\s\S]*?\\end\{frame\})", content_tex)]
    frame_plain: List[Dict[str, Any]] = []
    for fr in frames:
        title, subtitle = _extract_title(fr)
        body = _frame_to_plain_text(fr)
        images = _extract_includegraphics_paths(fr)
        has_table = "\\begin{tabular" in fr or "\\begin{table" in fr
        has_formula = bool(re.search(r"\$[^$]+\$|\\\[|\\\(", fr))
        text = " ".join([x for x in [title, subtitle, body] if x]).strip()
        frame_plain.append(
            {
                "title": title,
                "subtitle": subtitle,
                "text": text,
                "image_count": len(images),
                "has_table": bool(has_table),
                "has_formula": bool(has_formula),
            }
        )

    alignment = _safe_read_json(alignment_path) or {}
    dsid_by_page = alignment.get("dsid_by_page") if isinstance(alignment.get("dsid_by_page"), list) else None
    page_meta_by_page = alignment.get("page_meta_by_page") if isinstance(alignment.get("page_meta_by_page"), list) else None

    html_meta = _safe_read_json(html_meta_path) or {}
    focus_pages = set()
    try:
        focus_pages = set(int(x) for x in (html_meta.get("focus_pages") or []) if isinstance(x, (int, float, str)))
    except Exception:
        focus_pages = set()
    effects_by_page = html_meta.get("effects_by_page") if isinstance(html_meta.get("effects_by_page"), dict) else {}

    doc = fitz.open(pdf_path)
    pages = int(doc.page_count)
    pdf_stats: List[Dict[str, Any]] = []
    for i in range(pages):
        min_font = None
        block_count = 0
        try:
            page = doc.load_page(i)
            d = page.get_text("dict") or {}
            blocks = d.get("blocks") or []
            block_count = int(len(blocks))
            for b in blocks:
                lines = (b or {}).get("lines") or []
                for ln in lines:
                    for sp in (ln or {}).get("spans") or []:
                        try:
                            sz = float((sp or {}).get("size") or 0.0)
                        except Exception:
                            sz = 0.0
                        if sz > 0 and (min_font is None or sz < min_font):
                            min_font = sz
        except Exception:
            pass
        pdf_stats.append({"min_font_pt": min_font, "block_count": block_count})
    doc.close()

    page_types: List[str] = []
    for i in range(pages):
        t = "content"
        if page_meta_by_page and i < len(page_meta_by_page) and isinstance(page_meta_by_page[i], dict):
            t = str(page_meta_by_page[i].get("type") or "content")
        page_types.append(t)

    total_duration_sec = _infer_total_duration_seconds(project_record)
    budgets = _build_time_budgets(page_types, total_duration_sec)
    est_secs = [float(_estimate_speech_seconds(speech_segments[i]) if i < len(speech_segments) else 0.0) for i in range(pages)]

    slide_texts: List[str] = []
    for i in range(pages):
        fr_idx = None
        if dsid_by_page and i < len(dsid_by_page) and isinstance(dsid_by_page[i], int):
            fr_idx = int(dsid_by_page[i]) - 1
        elif i < len(frame_plain):
            fr_idx = i
        txt = frame_plain[fr_idx]["text"] if (fr_idx is not None and 0 <= fr_idx < len(frame_plain)) else ""
        slide_texts.append(txt)

    vectorizer = _build_vectorizer([t for t in slide_texts + speech_segments if t])
    slide_vecs = [vectorizer.vec(t) for t in slide_texts]
    speech_vecs = [vectorizer.vec(speech_segments[i] if i < len(speech_segments) else "") for i in range(pages)]

    emphasis_pages = set()
    for i in range(pages):
        has_effects = False
        try:
            v = effects_by_page.get(str(i)) if isinstance(effects_by_page, dict) else None
            if v is None:
                v = effects_by_page.get(i) if isinstance(effects_by_page, dict) else None
            has_effects = bool(v)
        except Exception:
            has_effects = False
        if has_effects or i in focus_pages:
            emphasis_pages.add(i)

    def pace_fit_for(i: int) -> float:
        if not emphasis_pages:
            return 0.3
        nearest = min(abs(i - j) for j in emphasis_pages)
        if nearest <= 1:
            return 1.0
        if nearest <= 2:
            return 0.75
        if nearest <= 4:
            return 0.55
        return 0.35

    per_slide: List[Dict[str, Any]] = []
    for i in range(pages):
        fr_idx = None
        if dsid_by_page and i < len(dsid_by_page) and isinstance(dsid_by_page[i], int):
            fr_idx = int(dsid_by_page[i]) - 1
        elif i < len(frame_plain):
            fr_idx = i

        ft = frame_plain[fr_idx] if (fr_idx is not None and 0 <= fr_idx < len(frame_plain)) else {}
        slide_text = slide_texts[i]
        speech_text = speech_segments[i] if i < len(speech_segments) else ""
        word_count = _count_words(slide_text)

        min_font_pt = pdf_stats[i]["min_font_pt"]
        block_count = int(pdf_stats[i]["block_count"] or 0) + int(ft.get("image_count") or 0) + (2 if ft.get("has_table") else 0)

        leg_score, leg_reasons = _score_legibility(min_font_pt, word_count, block_count)

        budget = float(budgets[i]) if i < len(budgets) else 0.0
        est = float(est_secs[i])
        tdq_score, tdq_reasons = _score_time_pace(est, budget)

        sim_prev = None
        sim_next = None
        if i - 1 >= 0:
            sim_prev = vectorizer.cosine(slide_vecs[i - 1], slide_vecs[i])
        if i + 1 < pages:
            sim_next = vectorizer.cosine(slide_vecs[i], slide_vecs[i + 1])
        ndc_score, ndc_reasons = _score_transition(sim_prev or 0.0, sim_next or 0.0)

        sim_ssc = vectorizer.cosine(slide_vecs[i], speech_vecs[i])
        toks_slide = set(_tokenize(slide_text))
        toks_speech = set(_tokenize(speech_text))
        overlap = float(len(toks_slide & toks_speech) / max(1, len(toks_slide | toks_speech))) if toks_slide or toks_speech else 0.0
        ssc_score, ssc_reasons = _score_complementarity(sim_ssc, overlap)

        has_anchor = bool(ft.get("image_count") or ft.get("has_table") or ft.get("has_formula"))
        has_actions = bool(i in emphasis_pages)
        fr_score, fr_reasons = _score_focus_readiness(has_anchor, has_actions, pace_fit_for(i))

        per_slide.append(
            {
                "page_index": i,
                "page_type": page_types[i] if i < len(page_types) else "content",
                "title": ft.get("title") or "",
                "metrics": {
                    "legibility": leg_score,
                    "time_pace": tdq_score,
                    "transition": ndc_score,
                    "script_complement": ssc_score,
                    "focus_readiness": fr_score,
                },
                "explain": {
                    "min_font_pt": min_font_pt,
                    "word_count": word_count,
                    "block_count": block_count,
                    "speech_seconds_est": est,
                    "time_budget_sec": budget,
                    "sim_prev": sim_prev,
                    "sim_next": sim_next,
                    "slide_script_sim": sim_ssc,
                    "slide_script_overlap": overlap,
                    "image_count": int(ft.get("image_count") or 0),
                },
                "signals": {
                    "legibility": leg_reasons,
                    "time_pace": tdq_reasons,
                    "transition": ndc_reasons,
                    "script_complement": ssc_reasons,
                    "focus_readiness": fr_reasons,
                },
            }
        )

    total_est = float(sum(est_secs))
    rsat = 0.5
    rsat_reasons: List[str] = []
    if total_duration_sec > 0:
        ratio = total_est / float(total_duration_sec)
        if ratio > 1.15:
            rsat_reasons.append("整体预计超时，建议精简内容或删页")
        elif ratio < 0.7 and total_est > 0:
            rsat_reasons.append("整体预计偏短，可能需要补充动机/总结")
        rsat = _clamp(1.0 - abs(ratio - 1.0) / 0.6)
    else:
        rsat_reasons.append("未配置目标时长，无法评估整体匹配")

    data = {
        "ok": True,
        "deck_summary": {
            "duration_target_sec": int(total_duration_sec),
            "duration_estimated_sec": float(total_est),
            "metrics": {"goal_fit": float(rsat)},
            "signals": {"goal_fit": rsat_reasons[:3]},
        },
        "per_slide": per_slide,
    }

    _atomic_write_json(cache_path, {"_meta": {"version": 1, "input_mtimes": input_mtimes}, "data": data})
    return data

