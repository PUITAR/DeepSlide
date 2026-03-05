from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .manifest import scan_dataset_cache
from .metrics.vision import VisionEmbedder, compute_f_vis_vit, extract_images_from_pdf, extract_images_from_pptx, filter_images
from .paths import default_paths


def _parse_float(s: str) -> float:
    try:
        return float(s)
    except Exception:
        return float("nan")


def _fmt_float(x: float) -> str:
    if x is None:
        return "nan"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "nan"
    return str(float(x))


def _mean_ignore_nan(xs: Iterable[float]) -> float:
    vals = [x for x in xs if x is not None and isinstance(x, (int, float)) and not math.isnan(float(x))]
    if not vals:
        return float("nan")
    return float(sum(float(x) for x in vals) / len(vals))


def _load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return [dict(row) for row in r]


def _write_csv_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _iter_details(path: Path) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _write_details(path: Path, rows: Iterable[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for obj in rows:
            f.write(json.dumps(obj, ensure_ascii=False))
            f.write("\n")


def _artifact_type_from_path(p: Path) -> str:
    suf = p.suffix.lower()
    if suf == ".pptx":
        return "pptx"
    if suf == ".pdf":
        return "pdf"
    return "unknown"


def recompute_fvis(
    details_path: Path,
    scores_path: Path,
    metrics_long_path: Path,
    systems_path: Path,
    dataset_cache_root: Path,
    threshold: float,
    min_edge_px: int,
    min_area_px: int,
) -> None:
    inst_map = {i.instance_id: i for i in scan_dataset_cache(dataset_cache_root)}

    embedder = VisionEmbedder()
    src_cache: Dict[str, Tuple[Optional[float], Dict, int]] = {}
    deck_cache: Dict[str, Tuple[List, Dict]] = {}
    src_img_cache: Dict[str, Tuple[List, Dict]] = {}

    fvis_by_key: Dict[Tuple[str, str], float] = {}
    fvis_details_by_key: Dict[Tuple[str, str], Dict] = {}
    na_by_key: Dict[Tuple[str, str], bool] = {}

    updated_details_rows: List[Dict] = []
    for obj in _iter_details(details_path):
        system = obj.get("system")
        instance_id = obj.get("instance_id")
        if not system or not instance_id:
            updated_details_rows.append(obj)
            continue

        inst = inst_map.get(instance_id)
        if inst is None:
            new_details = {
                "reason": "missing_instance",
                "na": True,
                "method": "vit_cls_cosine",
                "threshold": float(threshold),
            }
            fvis = float("nan")
        else:
            src_pdf = Path(inst.paper_pdf_path)
            src_key = str(src_pdf)
            if src_key not in src_img_cache:
                src_items, src_diag = extract_images_from_pdf(src_pdf)
                src_items, src_f = filter_images(src_items, min_edge_px=min_edge_px, min_area_px=min_area_px)
                src_img_cache[src_key] = (src_items, {"extract": src_diag, "filter": src_f})
            src_items, src_meta = src_img_cache[src_key]

            art_path = Path(obj.get("primary_artifact") or "")
            art_key = str(art_path)
            if art_key not in deck_cache:
                if _artifact_type_from_path(art_path) == "pptx":
                    deck_items, deck_diag = extract_images_from_pptx(art_path)
                else:
                    deck_items, deck_diag = extract_images_from_pdf(art_path)
                deck_items, deck_f = filter_images(deck_items, min_edge_px=min_edge_px, min_area_px=min_area_px)
                deck_cache[art_key] = (deck_items, {"extract": deck_diag, "filter": deck_f})
            deck_items, deck_meta = deck_cache[art_key]

            fvis, new_details = compute_f_vis_vit(src_items, deck_items, embedder=embedder, threshold=float(threshold))
            if fvis is None:
                fvis = float("nan")
                if not isinstance(new_details, dict):
                    new_details = {}
                new_details.update(
                    {
                        "na": True,
                        "method": "vit_cls_cosine",
                        "model": embedder.model_id,
                        "threshold": float(threshold),
                        "source": src_meta,
                        "deck": deck_meta,
                    }
                )
            else:
                if not isinstance(new_details, dict):
                    new_details = {}
                new_details.update({"na": False, "source": src_meta, "deck": deck_meta})

        k = (system, instance_id)
        fvis_by_key[k] = float(fvis)
        fvis_details_by_key[k] = new_details if isinstance(new_details, dict) else {}
        na_by_key[k] = bool(isinstance(new_details, dict) and new_details.get("na"))

        ad = obj.get("artifact_details") or {}
        if isinstance(ad, dict):
            ad = dict(ad)
            ad["F_vis"] = new_details
            obj["artifact_details"] = ad
        updated_details_rows.append(obj)

    _write_details(details_path, updated_details_rows)

    scores_rows = _load_csv_rows(scores_path)
    scores_fields = list(scores_rows[0].keys()) if scores_rows else []
    for row in scores_rows:
        system = row.get("system")
        instance_id = row.get("instance_id")
        if not system or not instance_id:
            continue
        v = fvis_by_key.get((system, instance_id))
        if v is None:
            continue
        row["F_vis"] = _fmt_float(v)
    if scores_fields:
        _write_csv_rows(scores_path, scores_rows, scores_fields)

    long_rows = _load_csv_rows(metrics_long_path)
    long_fields = list(long_rows[0].keys()) if long_rows else []
    for row in long_rows:
        if row.get("metric") != "F_vis":
            continue
        system = row.get("system")
        instance_id = row.get("instance_id")
        if not system or not instance_id:
            continue
        v = fvis_by_key.get((system, instance_id))
        if v is None:
            continue
        row["value"] = _fmt_float(v)
        w = _parse_float(row.get("weight", "nan"))
        row["weighted_value"] = _fmt_float(float(v) * float(w) if not math.isnan(float(v)) and not math.isnan(float(w)) else float("nan"))
    if long_fields:
        _write_csv_rows(metrics_long_path, long_rows, long_fields)

    systems_rows = _load_csv_rows(systems_path)
    systems_fields = list(systems_rows[0].keys()) if systems_rows else []

    by_sys: Dict[str, List[float]] = defaultdict(list)
    for row in scores_rows:
        sys = row.get("system")
        if not sys:
            continue
        by_sys[sys].append(_parse_float(row.get("F_vis", "nan")))

    for row in systems_rows:
        sys = row.get("system")
        if not sys:
            continue
        row["F_vis"] = _fmt_float(_mean_ignore_nan(by_sys.get(sys, [])))

    if systems_fields:
        _write_csv_rows(systems_path, systems_rows, systems_fields)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores-dir", type=str, default="", help="默认使用 experiments/evaluation/outputs/scores")
    ap.add_argument("--threshold", type=float, default=float((os.getenv("EVAL_FVIS_SIM_THRESHOLD") or "0.85").strip()))
    ap.add_argument("--min-edge-px", type=int, default=int((os.getenv("EVAL_FVIS_MIN_EDGE_PX") or "64").strip()))
    ap.add_argument("--min-area-px", type=int, default=int((os.getenv("EVAL_FVIS_MIN_AREA_PX") or str(64 * 64)).strip()))
    args = ap.parse_args()

    paths = default_paths()
    scores_dir = Path(args.scores_dir) if args.scores_dir else (paths.scores_dir)

    details_path = scores_dir / "details.jsonl"
    scores_path = scores_dir / "scores.csv"
    metrics_long_path = scores_dir / "metrics_long.csv"
    systems_path = scores_dir / "systems.csv"

    recompute_fvis(
        details_path=details_path,
        scores_path=scores_path,
        metrics_long_path=metrics_long_path,
        systems_path=systems_path,
        dataset_cache_root=paths.dataset_cache_root,
        threshold=float(args.threshold),
        min_edge_px=int(args.min_edge_px),
        min_area_px=int(args.min_area_px),
    )


if __name__ == "__main__":
    main()
