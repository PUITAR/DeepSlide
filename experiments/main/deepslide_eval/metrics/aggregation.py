from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .artifact import ArtifactMetrics
from .delivery import DeliveryMetrics


@dataclass(frozen=True)
class AggregateScores:
    S_Artifact: float
    S_Delivery: float
    details: Dict


def aggregate_artifact(m: ArtifactMetrics, weights: Dict) -> float:
    alpha_stab = float(weights["artifact"]["alpha_stab"])
    alpha_fid = float(weights["artifact"]["alpha_fid"])
    alpha_read = float(weights["artifact"]["alpha_read"])
    beta = float(weights["artifact"]["beta_text_vs_vis"])
    gamma = float(weights["artifact"]["gamma_legibility_vs_human"])

    fid = beta * m.F_text + (1 - beta) * m.F_vis
    read = gamma * m.L + (1 - gamma) * m.A
    return float(alpha_stab * m.ACSR + alpha_fid * fid + alpha_read * read)


def aggregate_delivery(m_art: ArtifactMetrics, m_del: DeliveryMetrics, weights: Dict) -> float:
    w = weights["delivery"]
    beta = float(weights["artifact"]["beta_text_vs_vis"])
    fid = beta * m_art.F_text + (1 - beta) * m_art.F_vis

    total = 0.0
    total += float(w["omega_RSat"]) * m_del.RSat
    total += float(w["omega_NDC"]) * m_del.NDC
    total += float(w["omega_SSC"]) * m_del.SSC
    total += float(w["omega_TDQ"]) * m_del.TDQ
    total += float(w["omega_ACQ"]) * m_del.ACQ
    total += float(w["omega_RR"]) * m_del.RR
    total += float(w["omega_stab"]) * m_art.ACSR
    total += float(w["omega_fid"]) * fid
    return float(total)


def aggregate_scores(m_art: ArtifactMetrics, m_del: DeliveryMetrics, weights: Dict) -> AggregateScores:
    s_a = aggregate_artifact(m_art, weights=weights)
    s_d = aggregate_delivery(m_art, m_del, weights=weights)
    return AggregateScores(S_Artifact=s_a, S_Delivery=s_d, details={"artifact": m_art.details, "delivery": m_del.details})
