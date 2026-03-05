from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import os

from ..alignment import Embedder
from ..extractors.common import DeckContent, SourceDocContent


@dataclass(frozen=True)
class ArtifactMetrics:
    ACSR: float
    F_rouge: float
    F_bert: float
    F_text: float
    F_vis: float
    L: float
    A: float

    details: Dict


def compute_acsr(ok: bool) -> float:
    return 1.0 if ok else 0.0


def compute_f_text(
    source: SourceDocContent,
    deck: DeckContent,
    embedder: Embedder,
    topk: int = 5,
) -> tuple[float, Dict]:
    chunks = [c for c in source.chunks if c]
    if not chunks:
        return 0.0, {"reason": "no_source_chunks"}

    slide_texts = []
    for s in deck.slides:
        q = (s.text_final + "\n" + s.notes).strip()
        if not q:
            q = s.text_final.strip()
        slide_texts.append(q)

    try:
        if embedder.method == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer

            vec = TfidfVectorizer(max_features=50_000, ngram_range=(1, 2))
            chunk_emb = vec.fit_transform(chunks).toarray().astype(np.float32)
            slide_emb = vec.transform(slide_texts).toarray().astype(np.float32)
        else:
            chunk_emb = embedder.embed(chunks)
            slide_emb = embedder.embed(slide_texts)
    except Exception as e:
        return 0.0, {"reason": f"embed_failed: {e}"}

    chunk_emb = chunk_emb.astype(np.float32)
    slide_emb = slide_emb.astype(np.float32)
    if chunk_emb.size == 0 or slide_emb.size == 0:
        return 0.0, {"reason": "empty_embeddings"}

    from ..alignment import cosine_topk

    scores = []
    top_matches = []
    for i in range(slide_emb.shape[0]):
        res = cosine_topk(slide_emb[i], chunk_emb, k=topk)
        if not res.top_scores:
            scores.append(0.0)
            top_matches.append([])
            continue
        scores.append(float(np.mean(res.top_scores)))
        top_matches.append(list(zip(res.top_indices, res.top_scores)))

    return float(np.mean(scores)), {"per_slide": scores, "top_matches": top_matches}


def _tokenize(s: str) -> list[str]:
    return [t for t in (s or "").lower().replace("\n", " ").split(" ") if t]


def _rouge_1_f1(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    from collections import Counter

    ca = Counter(ta)
    cb = Counter(tb)
    overlap = sum((ca & cb).values())
    prec = overlap / max(1, len(ta))
    rec = overlap / max(1, len(tb))
    if prec + rec == 0:
        return 0.0
    return float(2 * prec * rec / (prec + rec))


def _rouge_l_f1(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    n = len(ta)
    m = len(tb)
    dp = [0] * (m + 1)
    for i in range(1, n + 1):
        prev = 0
        for j in range(1, m + 1):
            cur = dp[j]
            if ta[i - 1] == tb[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    lcs = dp[m]
    prec = lcs / max(1, n)
    rec = lcs / max(1, m)
    if prec + rec == 0:
        return 0.0
    return float(2 * prec * rec / (prec + rec))


def compute_f_rouge_and_bert(
    source: SourceDocContent,
    deck: DeckContent,
    embedder: Embedder,
    topk: int = 5,
) -> tuple[float, float, Dict]:
    f_text, d_text = compute_f_text(source, deck, embedder=embedder, topk=topk)
    top_matches = d_text.get("top_matches")
    if not isinstance(top_matches, list) or not source.chunks:
        return 0.0, 0.0, {"reason": "missing_alignment"}

    rouge_scores = []
    pairs = []
    for i, s in enumerate(deck.slides):
        q_slide = (s.text_final or "").strip()
        q_notes = (s.notes or "").strip()
        q = (q_slide + "\n" + q_notes).strip()
        m = top_matches[i] if i < len(top_matches) else []
        idxs = []
        for pair in (m[:topk] if isinstance(m, list) else []):
            if not isinstance(pair, (list, tuple)) or len(pair) < 1:
                continue
            idxs.append(int(pair[0]))
        chunks = [source.chunks[j] for j in idxs if 0 <= j < len(source.chunks)]
        t = "\n\n".join([c for c in chunks if c]).strip()
        if not q or not t:
            rouge_scores.append(0.0)
            continue

        r1 = 0.5 * (_rouge_1_f1(q_slide, t) + _rouge_1_f1(q_notes, t))
        rl = 0.5 * (_rouge_l_f1(q_slide, t) + _rouge_l_f1(q_notes, t))
        rouge_scores.append(float((r1 + rl) / 2.0))
        pairs.append((q, t))

    f_rouge = float(np.mean(rouge_scores)) if rouge_scores else 0.0

    f_bert = 0.0
    bert_details = {"is_proxy": True, "method": "embedding"}
    if pairs:
        use_bert_score = (os.getenv("EVAL_BERTSCORE_ENABLED") or "0").strip() in {"1", "true", "yes"}
        if use_bert_score:
            try:
                from bert_score import score as bert_score

                model_type = (os.getenv("EVAL_BERTSCORE_MODEL") or "roberta-base").strip()
                cands = [a for a, _ in pairs]
                refs = [b for _, b in pairs]
                P, R, F = bert_score(cands, refs, lang="en", verbose=False, model_type=model_type)
                f_bert = float(F.mean().item())
                bert_details = {"is_proxy": False, "method": "bert-score", "model": model_type}
            except Exception as e:
                bert_details = {"is_proxy": True, "method": "embedding", "error": str(e)}

        if bert_details.get("is_proxy"):
            try:
                sims = []
                for a, b in pairs:
                    emb = embedder.embed([a, b]).astype(np.float32)
                    if emb.shape[0] != 2:
                        continue
                    x = emb[0]
                    y = emb[1]
                    denom = (np.linalg.norm(x) * np.linalg.norm(y)) + 1e-12
                    sims.append(float(np.dot(x, y) / denom))
                f_bert = float(np.mean(sims)) if sims else 0.0
            except Exception as e:
                bert_details = {"is_proxy": True, "method": "embedding", "error": str(e)}
                f_bert = 0.0

    details = {"F_text": d_text, "F_rouge": {"per_slide": rouge_scores}, "F_bert": bert_details}
    return f_rouge, f_bert, details


def compute_f_vis(source: SourceDocContent, deck: DeckContent) -> tuple[float, Dict]:
    from pathlib import Path

    from .vision import VisionEmbedder, compute_f_vis_vit, extract_images_from_pdf, extract_images_from_pptx, filter_images

    thr = float((os.getenv("EVAL_FVIS_SIM_THRESHOLD") or "0.85").strip())
    min_edge = int((os.getenv("EVAL_FVIS_MIN_EDGE_PX") or "64").strip())
    min_area = int((os.getenv("EVAL_FVIS_MIN_AREA_PX") or str(64 * 64)).strip())

    global _VISION_EMBEDDER
    try:
        _VISION_EMBEDDER
    except NameError:
        _VISION_EMBEDDER = VisionEmbedder()

    src_items, src_diag = extract_images_from_pdf(Path(source.pdf_path))
    src_items, src_f = filter_images(src_items, min_edge_px=min_edge, min_area_px=min_area)

    deck_diag: Dict
    if deck.artifact_type == "pptx":
        deck_items, deck_diag = extract_images_from_pptx(Path(deck.artifact_path))
    else:
        deck_items, deck_diag = extract_images_from_pdf(Path(deck.artifact_path))
    deck_items, deck_f = filter_images(deck_items, min_edge_px=min_edge, min_area_px=min_area)

    score, details = compute_f_vis_vit(src_items, deck_items, embedder=_VISION_EMBEDDER, threshold=thr)
    if score is None:
        base = details if isinstance(details, dict) else {}
        base.update(
            {
                "na": True,
                "method": "vit_cls_cosine",
                "model": _VISION_EMBEDDER.model_id,
                "threshold": thr,
                "source_extract": src_diag,
                "source_filter": src_f,
                "deck_extract": deck_diag,
                "deck_filter": deck_f,
            }
        )
        return 0.0, base

    if not isinstance(details, dict):
        details = {}
    details.update(
        {
            "na": False,
            "source_extract": src_diag,
            "source_filter": src_f,
            "deck_extract": deck_diag,
            "deck_filter": deck_f,
        }
    )
    return float(score), details


def compute_legibility(deck: DeckContent) -> tuple[float, Dict]:
    if not deck.slides:
        return 0.0, {"reason": "no_slides"}

    penalties = []
    per_slide = []
    for s in deck.slides:
        o = 0.0
        if s.min_font_pt is not None and s.min_font_pt < 12:
            o += 1.0
        if s.word_count > 140:
            o += 1.0
        if s.num_shapes > 60:
            o += 1.0
        penalties.append(o)
        per_slide.append({"min_font_pt": s.min_font_pt, "word_count": s.word_count, "num_shapes": s.num_shapes, "pen": o})

    lam = 0.25
    score = 1.0 - float(np.mean([min(1.0, lam * p) for p in penalties]))
    score = max(0.0, min(1.0, score))
    return score, {"per_slide": per_slide}


def compute_aesthetic_proxy(deck: DeckContent, legibility: float) -> tuple[float, Dict]:
    if not deck.slides:
        return 0.0, {"reason": "no_slides"}
    img_ratio = float(sum(1 for s in deck.slides if s.num_images > 0) / max(1, len(deck.slides)))
    notes_ratio = float(sum(1 for s in deck.slides if (s.notes or "").strip()) / max(1, len(deck.slides)))
    a = float(max(0.0, min(1.0, 0.6 * legibility + 0.2 * (1.0 - abs(img_ratio - 0.6)) + 0.2 * notes_ratio)))
    return a, {"is_proxy": True, "img_ratio": img_ratio, "notes_ratio": notes_ratio}


def compute_artifact_metrics(
    source_ok: bool,
    deck_ok: bool,
    source: Optional[SourceDocContent],
    deck: Optional[DeckContent],
    embedder: Embedder,
) -> ArtifactMetrics:
    acsr = compute_acsr(deck_ok)
    details: Dict = {}

    if not (source_ok and deck_ok and source is not None and deck is not None):
        return ArtifactMetrics(ACSR=acsr, F_rouge=0.0, F_bert=0.0, F_text=0.0, F_vis=0.0, L=0.0, A=0.0, details={"reason": "missing_inputs"})

    f_rouge, f_bert, d_fid = compute_f_rouge_and_bert(source, deck, embedder=embedder)
    wR = 0.5
    wB = 0.5
    f_text = float(wR * f_rouge + wB * f_bert)
    f_vis, d_vis = compute_f_vis(source, deck)
    leg, d_leg = compute_legibility(deck)
    a, d_a = compute_aesthetic_proxy(deck, legibility=leg)
    details["F_rouge"] = d_fid.get("F_rouge")
    details["F_bert"] = d_fid.get("F_bert")
    details["F_text"] = d_fid.get("F_text")
    details["F_vis"] = d_vis
    details["L"] = d_leg
    details["A"] = d_a
    return ArtifactMetrics(ACSR=acsr, F_rouge=f_rouge, F_bert=f_bert, F_text=f_text, F_vis=f_vis, L=leg, A=a, details=details)


def compute_artifact_metrics_with_overrides(
    source_ok: bool,
    deck_ok: bool,
    source: Optional[SourceDocContent],
    deck: Optional[DeckContent],
    embedder: Embedder,
    overrides: Optional[Dict[str, float]] = None,
    override_details: Optional[Dict[str, Dict]] = None,
) -> ArtifactMetrics:
    base = compute_artifact_metrics(source_ok, deck_ok, source, deck, embedder=embedder)
    if not overrides:
        return base

    f_text = float(overrides.get("F_text", base.F_text))
    f_vis = float(overrides.get("F_vis", base.F_vis))
    l = float(overrides.get("L", base.L))
    a = float(overrides.get("A", base.A))
    details = dict(base.details)
    if override_details:
        details.update(override_details)
    return ArtifactMetrics(
        ACSR=base.ACSR,
        F_rouge=base.F_rouge,
        F_bert=base.F_bert,
        F_text=f_text,
        F_vis=f_vis,
        L=l,
        A=a,
        details=details,
    )
