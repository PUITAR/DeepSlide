from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from ..alignment import Embedder
from ..extractors.common import DeckContent


@dataclass(frozen=True)
class DeliveryMetrics:
    RSat: float
    SSC: float
    TDQ: float
    ACQ: float
    RR: float
    NDC: float

    details: Dict


def _cosine_sim(text_a: str, text_b: str, embedder: Embedder) -> float:
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b:
        return 0.0
    emb = embedder.embed([a, b]).astype(np.float32)
    if emb.shape[0] != 2:
        return 0.0
    x = emb[0]
    y = emb[1]
    denom = (np.linalg.norm(x) * np.linalg.norm(y)) + 1e-12
    return float(np.dot(x, y) / denom)


def compute_ssc(deck: DeckContent, embedder: Embedder, sweet_l: float = 0.25, sweet_u: float = 0.55) -> tuple[float, Dict]:
    sims = []
    covs = []
    for s in deck.slides:
        sim = _cosine_sim(s.text_final, s.notes, embedder)
        sims.append(sim)

        slide_terms = [w.lower() for w in s.text_final.replace("\n", " ").split(" ") if len(w) >= 5]
        slide_terms = slide_terms[:60]
        if not slide_terms:
            covs.append(0.0)
        else:
            notes_l = (s.notes or "").lower()
            hit = sum(1 for t in slide_terms if t in notes_l)
            covs.append(float(hit / max(1, len(slide_terms))))

    red_scores = []
    for sim in sims:
        if sweet_l <= sim <= sweet_u:
            red_scores.append(1.0)
        else:
            dist = min(abs(sim - sweet_l), abs(sim - sweet_u))
            denom = max(sweet_l, 1 - sweet_u) + 1e-6
            red_scores.append(max(0.0, 1.0 - dist / denom))

    red = float(np.mean(red_scores)) if red_scores else 0.0
    cov = float(np.mean(covs)) if covs else 0.0
    return float((red + cov) / 2.0), {"redundancy": red, "coverage": cov, "per_slide_sim": sims, "per_slide_cov": covs}


def compute_tdq(deck: DeckContent, duration_seconds: int, wpm: int = 150) -> tuple[float, Dict]:
    per_slide_seconds = []
    for s in deck.slides:
        words = len([w for w in (s.notes or "").replace("\n", " ").split(" ") if w])
        secs = (words / max(1, wpm)) * 60.0
        per_slide_seconds.append(secs)
    est_total = float(sum(per_slide_seconds))

    tau = 45.0
    tda = float(np.exp(-abs(est_total - float(duration_seconds)) / tau)) if duration_seconds > 0 else 0.0

    if len(per_slide_seconds) >= 2:
        std = float(np.std(per_slide_seconds))
        std_max = max(10.0, float(duration_seconds) / 6.0)
        psp = 1.0 - std / (std_max + 1e-6)
        psp = max(0.0, min(1.0, float(psp)))
    else:
        psp = 0.0

    trans_markers = [
        "next",
        "then",
        "therefore",
        "however",
        "in summary",
        "接下来",
        "然后",
        "因此",
        "但是",
        "总结",
        "最后",
    ]
    notes_all = (deck.deck_notes or "").lower()
    hit = sum(1 for m in trans_markers if m.lower() in notes_all)
    trn = min(1.0, hit / 4.0)
    return float((tda + psp + trn) / 3.0), {"TDA": tda, "PSP": psp, "TRN": trn, "est_total_seconds": est_total, "per_slide_seconds": per_slide_seconds}


def compute_ndc_proxy(deck: DeckContent, embedder: Embedder, eta: float = 0.4) -> tuple[float, Dict]:
    titles = []
    for s in deck.slides:
        t = (s.text_final or "").split("\n", 1)[0].strip()
        titles.append(t)
    title_rate = float(sum(1 for t in titles if t) / max(1, len(titles)))

    texts = [(s.text_final + "\n" + s.notes).strip() for s in deck.slides]
    texts = [t if t else "" for t in texts]
    coh = 0.0
    drift = []
    try:
        embs = embedder.embed(texts).astype(np.float32)
        if embs.shape[0] >= 2:
            for i in range(1, embs.shape[0]):
                x = embs[i - 1]
                y = embs[i]
                denom = (np.linalg.norm(x) * np.linalg.norm(y)) + 1e-12
                drift.append(1.0 - float(np.dot(x, y) / denom))
            std = float(np.std(drift))
            coh = float(np.exp(-std / 0.25))
    except Exception:
        coh = 0.0

    div = 0.0
    ctrl = float((title_rate + coh) / 2.0)
    ndc = float(eta * div + (1.0 - eta) * ctrl)
    return ndc, {"Div": div, "Ctrl_proxy": ctrl, "title_rate": title_rate, "coherence": coh, "drift": drift}


def compute_acq_proxy(deck: DeckContent, embedder: Embedder) -> tuple[float, Dict]:
    sims = []
    script_ok = []
    for s in deck.slides:
        a = (s.text_final or "").strip()
        b = (s.notes or "").strip()
        sims.append(_cosine_sim(a, b, embedder))
        script_ok.append(1.0 if b else 0.0)
    fsa = float(np.mean(sims)) if sims else 0.0
    fcv = float(np.mean(script_ok)) if script_ok else 0.0
    dsp = 1.0
    acq = float((fsa + fcv + dsp) / 3.0)
    return acq, {"FSA_proxy": fsa, "FCV_proxy": fcv, "DSP_proxy": dsp}


def compute_rr_proxy(deck: DeckContent, f_text: float) -> tuple[float, Dict]:
    notes_ratio = float(sum(1 for s in deck.slides if (s.notes or "").strip()) / max(1, len(deck.slides)))
    ocr_ratio = float(sum(1 for s in deck.slides if getattr(s, "ocr_used", False)) / max(1, len(deck.slides)))
    confs = [float(s.ocr_confidence) for s in deck.slides if getattr(s, "ocr_confidence", None) is not None]
    conf = float(sum(confs) / len(confs)) if confs else None

    frs = float(min(1.0, notes_ratio * 1.25))
    pc = float(max(0.0, 1.0 - (1.0 - notes_ratio) * 0.8 - ocr_ratio * 0.2))
    lc = float(max(0.0, min(1.0, f_text)))
    rr = float((frs + pc + lc) / 3.0)
    return rr, {"FRS_proxy": frs, "PC_proxy": pc, "LC_proxy": lc, "notes_ratio": notes_ratio, "ocr_ratio": ocr_ratio, "ocr_conf_avg": conf}


def compute_rsat(deck: DeckContent, duration_seconds: int) -> tuple[float, Dict]:
    if duration_seconds <= 0:
        return 0.0, {"reason": "missing_duration"}
    slide_cnt = len(deck.slides)
    if slide_cnt == 0:
        return 0.0, {"reason": "no_slides"}

    expected = max(6, int(round(duration_seconds / 60.0)))
    lower = max(3, int(expected * 0.6))
    upper = int(expected * 2.0)

    sec_per_slide = float(duration_seconds) / float(max(1, slide_cnt))
    sweet_l = 12.0
    sweet_u = 60.0
    hard_l = 6.0
    hard_u = 120.0

    if sweet_l <= sec_per_slide <= sweet_u:
        slide_fit = 1.0
    elif sec_per_slide < sweet_l:
        if sec_per_slide <= hard_l:
            slide_fit = 0.0
        else:
            slide_fit = (sec_per_slide - hard_l) / (sweet_l - hard_l)
    else:
        if sec_per_slide >= hard_u:
            slide_fit = 0.0
        else:
            slide_fit = (hard_u - sec_per_slide) / (hard_u - sweet_u)

    slide_fit = float(max(0.0, min(1.0, slide_fit)))
    return float(slide_fit), {
        "slide_cnt": slide_cnt,
        "expected": expected,
        "range": [lower, upper],
        "sec_per_slide": sec_per_slide,
        "sec_per_slide_sweet": [sweet_l, sweet_u],
        "sec_per_slide_hard": [hard_l, hard_u],
    }


def compute_delivery_metrics(
    deck_ok: bool,
    deck: Optional[DeckContent],
    embedder: Embedder,
    duration_seconds: int,
    wpm: int,
    f_text: float = 0.0,
) -> DeliveryMetrics:
    if not (deck_ok and deck is not None):
        return DeliveryMetrics(RSat=0.0, SSC=0.0, TDQ=0.0, ACQ=0.0, RR=0.0, NDC=0.0, details={"reason": "missing_deck"})

    rsat, d_rsat = compute_rsat(deck, duration_seconds=duration_seconds)
    ssc, d_ssc = compute_ssc(deck, embedder=embedder)
    tdq, d_tdq = compute_tdq(deck, duration_seconds=duration_seconds, wpm=wpm)

    ndc, d_ndc = compute_ndc_proxy(deck, embedder=embedder)
    acq, d_acq = compute_acq_proxy(deck, embedder=embedder)
    rr, d_rr = compute_rr_proxy(deck, f_text=f_text)
    details = {"RSat": d_rsat, "SSC": d_ssc, "TDQ": d_tdq, "NDC": d_ndc, "ACQ": d_acq, "RR": d_rr}
    return DeliveryMetrics(RSat=rsat, SSC=ssc, TDQ=tdq, ACQ=acq, RR=rr, NDC=ndc, details=details)


def compute_delivery_metrics_with_overrides(
    deck_ok: bool,
    deck: Optional[DeckContent],
    embedder: Embedder,
    duration_seconds: int,
    wpm: int,
    overrides: Optional[Dict[str, float]] = None,
    override_details: Optional[Dict[str, Dict]] = None,
    f_text: float = 0.0,
) -> DeliveryMetrics:
    base = compute_delivery_metrics(deck_ok, deck, embedder=embedder, duration_seconds=duration_seconds, wpm=wpm, f_text=f_text)
    if not overrides:
        return base

    rsat = float(overrides.get("RSat", base.RSat))
    ssc = float(overrides.get("SSC", base.SSC))
    tdq = float(overrides.get("TDQ", base.TDQ))
    acq = float(overrides.get("ACQ", base.ACQ))
    rr = float(overrides.get("RR", base.RR))
    details = dict(base.details)
    if override_details:
        details.update(override_details)
    return DeliveryMetrics(RSat=rsat, SSC=ssc, TDQ=tdq, ACQ=acq, RR=rr, NDC=base.NDC, details=details)
