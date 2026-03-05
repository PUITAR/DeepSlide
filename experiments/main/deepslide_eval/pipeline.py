from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from tqdm import tqdm

from .alignment import Embedder
from .extractors.common import DeckContent, SlideText, SourceDocContent
from .extractors.pdf_extractor import extract_deck_from_pdf, extract_source_from_pdf
from .extractors.pptx_extractor import extract_deck_from_pptx
from .io_utils import ensure_dir, iter_jsonl, sha1_bytes, try_read_text, write_json, write_jsonl
from .manifest import (
    DatasetInstance,
    OutputArtifact,
    dataset_instances_to_rows,
    output_artifacts_to_rows,
    scan_dataset_cache,
    scan_outputs_cache,
)
from .metrics.aggregation import aggregate_scores
from .metrics.artifact import compute_artifact_metrics_with_overrides
from .metrics.delivery import compute_rsat, compute_tdq, compute_delivery_metrics_with_overrides
from .llm.env import load_eval_dotenv, resolve_llm_env
from .llm.judge import JudgeConfig, LLMJudge
from .llm import rubrics
from .ocr.config import load_ocr_config
from .ocr.augment import augment_deck_with_ocr
from .paths import EvalPaths
from .reporting import write_leaderboard_md, write_metrics_long_csv, write_scores_csv


def load_yaml(path: Path) -> Dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


_SPEECH_SPLIT_RE = re.compile(r"\s*<next>\s*", re.IGNORECASE)


def _inject_deepslide_speech_notes(deck: DeckContent, base_pdf_path: str) -> DeckContent:
    p = Path(base_pdf_path)
    speech_path = p.parent / "speech.txt"
    text = try_read_text(speech_path)
    if not text:
        return deck

    parts = [x.strip() for x in _SPEECH_SPLIT_RE.split(text)]
    parts = [x for x in parts if x.strip()]
    if not parts:
        return deck

    slides = list(deck.slides)
    if len(parts) == len(slides) + 1 and len(parts[0]) <= 120:
        parts = parts[1:]

    if len(parts) < len(slides):
        parts = parts + [""] * (len(slides) - len(parts))
    elif len(parts) > len(slides):
        head = parts[: len(slides) - 1]
        tail = "\n\n".join(parts[len(slides) - 1 :]).strip()
        parts = head + [tail]

    for i, s in enumerate(slides):
        slides[i] = SlideText(
            slide_index=s.slide_index,
            text=s.text,
            text_ocr=s.text_ocr,
            text_final=s.text_final,
            notes=parts[i],
            word_count=s.word_count,
            min_font_pt=s.min_font_pt,
            num_shapes=s.num_shapes,
            num_images=s.num_images,
            ocr_used=s.ocr_used,
            ocr_confidence=s.ocr_confidence,
        )

    deck_notes = "\n\n".join([x for x in parts if x.strip()]).strip()
    return DeckContent(
        artifact_path=deck.artifact_path,
        artifact_type=deck.artifact_type,
        slides=slides,
        deck_text=deck.deck_text,
        deck_text_final=deck.deck_text_final,
        deck_notes=deck_notes,
        image_hashes=deck.image_hashes,
    )


def _artifact_cache_key(path_str: str) -> str:
    p = Path(path_str)
    try:
        st = p.stat()
        sig = f"{path_str}|{st.st_size}|{st.st_mtime_ns}"
    except Exception:
        sig = path_str
    return sha1_bytes(sig.encode("utf-8"))


def scan(paths: EvalPaths) -> Tuple[List[DatasetInstance], List[OutputArtifact]]:
    instances = scan_dataset_cache(paths.dataset_cache_root)
    artifacts = scan_outputs_cache(paths.outputs_cache_root)
    ensure_dir(paths.manifests_dir)
    write_jsonl(paths.manifests_dir / "dataset.jsonl", dataset_instances_to_rows(instances))
    write_jsonl(paths.manifests_dir / "outputs.jsonl", output_artifacts_to_rows(artifacts))
    return instances, artifacts


def _load_manifests(paths: EvalPaths) -> Tuple[List[DatasetInstance], List[OutputArtifact]]:
    dataset_path = paths.manifests_dir / "dataset.jsonl"
    outputs_path = paths.manifests_dir / "outputs.jsonl"
    instances = [DatasetInstance(**row) for row in iter_jsonl(dataset_path)]
    artifacts = [OutputArtifact(**row) for row in iter_jsonl(outputs_path)]
    return instances, artifacts


def _pick_primary_artifact(artifacts: List[OutputArtifact]) -> Optional[OutputArtifact]:
    if not artifacts:
        return None
    pri = {"pptx": 0, "ppt": 1, "pdf": 2, "html": 3}
    return sorted(artifacts, key=lambda a: (pri.get(a.artifact_type, 99), a.artifact_path))[0]


def evaluate(
    paths: EvalPaths,
    embed_method: str = "tfidf",
    st_model: Optional[str] = None,
    limit_instances: Optional[int] = None,
    systems: Optional[List[str]] = None,
    judge: str = "none",
    llm_mode: str = "packed",
    write_mode: str = "overwrite",
) -> List[Dict]:
    ensure_dir(paths.cache_dir)
    ensure_dir(paths.scores_dir)
    ensure_dir(paths.reports_dir)

    load_eval_dotenv(paths.evaluation_root)
    ocr_cfg = load_ocr_config()

    weights = load_yaml(paths.evaluation_root / "configs" / "weights_default.yaml")
    reqs = load_yaml(paths.evaluation_root / "configs" / "requirements_default.yaml")
    duration_seconds = int(reqs.get("default", {}).get("duration_seconds", 600))
    wpm = int(reqs.get("default", {}).get("wpm", 150))

    instances, all_artifacts = _load_manifests(paths)
    by_inst: Dict[str, Dict[str, List[OutputArtifact]]] = {}
    for a in all_artifacts:
        by_inst.setdefault(a.instance_id, {}).setdefault(a.system, []).append(a)

    embedder = Embedder(method=("sentence_transformers" if embed_method == "st" else "tfidf"), model_name=st_model)

    judge_obj = None
    if judge in {"llm", "hybrid"}:
        env = resolve_llm_env("JUDGE")
        if env.api_key:
            judge_obj = LLMJudge(cache_dir=paths.cache_dir / "judgements", config=JudgeConfig(agent_name="JUDGE"))
    judge_enabled = judge_obj is not None

    score_rows: List[Dict] = []
    detail_rows: List[Dict] = []
    long_rows: List[Dict] = []

    if systems is not None:
        systems_set = set(systems)
    else:
        systems_set = None

    existing_score_rows: List[Dict] = []
    existing_detail_rows: List[Dict] = []
    existing_long_rows: List[Dict] = []
    existing_keys: set[tuple[str, str]] = set()

    if write_mode in {"insert", "overwrite"}:
        import pandas as pd

        scores_csv = paths.scores_dir / "scores.csv"
        if scores_csv.exists():
            try:
                df = pd.read_csv(scores_csv)
            except Exception:
                df = None
            if df is not None:
                existing_score_rows = df.to_dict(orient="records")
                for r in existing_score_rows:
                    existing_keys.add((str(r.get("system", "")), str(r.get("instance_id", ""))))

        details_jsonl = paths.scores_dir / "details.jsonl"
        if details_jsonl.exists():
            existing_detail_rows = list(iter_jsonl(details_jsonl))

        long_csv = paths.scores_dir / "metrics_long.csv"
        if long_csv.exists():
            try:
                df = pd.read_csv(long_csv)
            except Exception:
                df = None
            if df is not None:
                existing_long_rows = df.to_dict(orient="records")

    total = 0
    for inst_i, inst in enumerate(instances):
        if limit_instances is not None and inst_i >= limit_instances:
            break
        for system, arts in by_inst.get(inst.instance_id, {}).items():
            if systems_set is not None and system not in systems_set:
                continue
            if _pick_primary_artifact(arts) is None:
                continue
            if write_mode == "insert" and (system, inst.instance_id) in existing_keys:
                continue
            total += 1

    pbar = tqdm(total=total, desc="Evaluating", unit="deck") if total > 0 else None

    for inst_i, inst in enumerate(instances):
        if limit_instances is not None and inst_i >= limit_instances:
            break
        src_pdf = Path(inst.paper_pdf_path)
        src_cache_key = sha1_bytes(str(src_pdf).encode("utf-8"))
        src_cache_path = paths.cache_dir / f"source_{src_cache_key}.json"

        src_ok = False
        src_content = None
        if src_cache_path.exists():
            try:
                obj = json.loads(src_cache_path.read_text(encoding="utf-8"))
                src_ok = bool(obj.get("ok"))
                if src_ok:
                    src_content = obj.get("content")
            except Exception:
                src_ok = False

        if not src_ok:
            res = extract_source_from_pdf(src_pdf)
            src_ok = res.ok
            src_content = asdict(res.content) if res.ok and res.content is not None else None
            write_json(src_cache_path, {"ok": src_ok, "error": res.error, "diagnostics": res.diagnostics, "content": src_content})

        inst_artifacts_by_system = by_inst.get(inst.instance_id, {})
        for system, arts in inst_artifacts_by_system.items():
            if systems_set is not None and system not in systems_set:
                continue
            if write_mode == "insert" and (system, inst.instance_id) in existing_keys:
                continue
            primary = _pick_primary_artifact(arts)
            if primary is None:
                continue

            if pbar is not None:
                pbar.set_postfix({"system": system, "paper": inst.paper_id, "type": primary.artifact_type})

            deck_ok = False
            deck_content = None
            deck_err = None
            deck_cache_key = _artifact_cache_key(primary.artifact_path)
            if primary.artifact_type == "pptx":
                deck_cache_path = paths.cache_dir / f"deck_{deck_cache_key}.json"
                if deck_cache_path.exists():
                    try:
                        obj = json.loads(deck_cache_path.read_text(encoding="utf-8"))
                        deck_ok = bool(obj.get("ok"))
                        deck_content = obj.get("content") if deck_ok else None
                        deck_err = obj.get("error")
                    except Exception:
                        deck_ok = False

                if not deck_ok:
                    dres = extract_deck_from_pptx(Path(primary.artifact_path))
                    deck_ok = dres.ok
                    deck_content = asdict(dres.content) if dres.ok and dres.content is not None else None
                    deck_err = dres.error
                    write_json(deck_cache_path, {"ok": deck_ok, "error": deck_err, "diagnostics": dres.diagnostics, "content": deck_content})
            elif primary.artifact_type == "pdf":
                deck_cache_path = paths.cache_dir / f"deck_{deck_cache_key}.json"
                if deck_cache_path.exists():
                    try:
                        obj = json.loads(deck_cache_path.read_text(encoding="utf-8"))
                        deck_ok = bool(obj.get("ok"))
                        deck_content = obj.get("content") if deck_ok else None
                        deck_err = obj.get("error")
                    except Exception:
                        deck_ok = False

                if not deck_ok:
                    dres = extract_deck_from_pdf(Path(primary.artifact_path))
                    deck_ok = dres.ok
                    deck_content = asdict(dres.content) if dres.ok and dres.content is not None else None
                    deck_err = dres.error
                    write_json(deck_cache_path, {"ok": deck_ok, "error": deck_err, "diagnostics": dres.diagnostics, "content": deck_content})
            else:
                deck_err = f"unsupported_primary_artifact: {primary.artifact_type}"

            if src_ok and src_content is not None:
                source_obj = SourceDocContent(**src_content)
            else:
                source_obj = None

            if deck_ok and deck_content is not None:
                deck_obj = DeckContent(
                    artifact_path=deck_content["artifact_path"],
                    artifact_type=deck_content["artifact_type"],
                    slides=[
                        SlideText(
                            slide_index=s.get("slide_index"),
                            text=s.get("text", ""),
                            text_ocr=s.get("text_ocr", ""),
                            text_final=s.get("text_final", s.get("text", "")),
                            notes=s.get("notes", ""),
                            word_count=s.get("word_count", 0),
                            min_font_pt=s.get("min_font_pt"),
                            num_shapes=s.get("num_shapes", 0),
                            num_images=s.get("num_images", 0),
                            ocr_used=s.get("ocr_used", False),
                            ocr_confidence=s.get("ocr_confidence"),
                        )
                        for s in deck_content["slides"]
                    ],
                    deck_text=deck_content.get("deck_text", ""),
                    deck_text_final=deck_content.get("deck_text_final", deck_content.get("deck_text", "")),
                    deck_notes=deck_content["deck_notes"],
                    image_hashes=deck_content["image_hashes"],
                )
            else:
                deck_obj = None

            if deck_ok and deck_obj is not None:
                p = Path(str(primary.artifact_path))
                if p.name == "base.pdf" and p.parent.name == "recipe" and (p.parent / "speech.txt").exists():
                    deck_obj = _inject_deepslide_speech_notes(deck_obj, base_pdf_path=str(primary.artifact_path))

            if deck_ok and deck_obj is not None:
                try:
                    deck_obj = augment_deck_with_ocr(deck_obj, cache_root=paths.cache_dir, ocr_cfg=ocr_cfg)
                    ocr_error = None
                except Exception as e:
                    ocr_error = str(e)
            else:
                ocr_error = None

            if deck_ok and deck_obj is not None:
                deck_final_path = paths.cache_dir / f"deck_final_{deck_cache_key}.json"
                write_json(
                    deck_final_path,
                    {
                        "ok": True,
                        "artifact_path": deck_obj.artifact_path,
                        "artifact_type": deck_obj.artifact_type,
                        "ocr": {"mode": ocr_cfg.mode, "url": ocr_cfg.url, "error": ocr_error},
                        "slides": [
                            {
                                "slide_index": s.slide_index,
                                "text": s.text,
                                "text_ocr": s.text_ocr,
                                "text_final": s.text_final,
                                "notes": s.notes,
                                "word_count": s.word_count,
                                "num_images": s.num_images,
                                "ocr_used": s.ocr_used,
                                "ocr_confidence": s.ocr_confidence,
                            }
                            for s in deck_obj.slides
                        ],
                        "deck_text": deck_obj.deck_text,
                        "deck_text_final": deck_obj.deck_text_final,
                        "deck_notes": deck_obj.deck_notes,
                    },
                )

            art_overrides: Dict[str, float] = {}
            art_override_details: Dict[str, Dict] = {}
            del_overrides: Dict[str, float] = {}
            del_override_details: Dict[str, Dict] = {}
            m_art_base = compute_artifact_metrics_with_overrides(
                src_ok,
                deck_ok,
                source_obj,
                deck_obj,
                embedder=embedder,
                overrides=None,
                override_details=None,
            )

            if judge_obj is not None and src_ok and deck_ok and source_obj is not None and deck_obj is not None:
                deck_summary = {
                    "slides": [
                        {
                            "index": s.slide_index,
                            "slide_text": s.text_final,
                            "notes": s.notes,
                        }
                        for s in deck_obj.slides[:12]
                    ]
                }

                base_rsat, base_rsat_details = compute_rsat(deck_obj, duration_seconds=duration_seconds)
                base_tdq, base_tdq_details = compute_tdq(deck_obj, duration_seconds=duration_seconds, wpm=wpm)
                base_tda = float(base_tdq_details.get("TDA", 0.0))

                f_text_details = (m_art_base.details or {}).get("F_text", {})
                top_matches = f_text_details.get("top_matches")
                fidelity_items = []
                if isinstance(top_matches, list) and source_obj.chunks:
                    for i, slide in enumerate(deck_obj.slides[:8]):
                        m = top_matches[i] if i < len(top_matches) else []
                        chunk_texts = []
                        for pair in (m[:3] if isinstance(m, list) else []):
                            if not isinstance(pair, (list, tuple)) or len(pair) < 1:
                                continue
                            idx = int(pair[0])
                            if 0 <= idx < len(source_obj.chunks):
                                chunk_texts.append(source_obj.chunks[idx])
                        fidelity_items.append({"slide_index": slide.slide_index, "slide": (slide.text_final + "\n" + slide.notes).strip(), "chunks": chunk_texts})

                if llm_mode == "packed":
                    try:
                        packed_payload = {"U": reqs.get("default", {}), "deck": deck_summary, "fidelity_items": fidelity_items}
                        packed_resp = judge_obj.judge_json(rubrics.PACKED_JUDGE_RUBRIC, packed_payload)
                        if packed_resp.get("ok") and isinstance(packed_resp.get("parsed"), dict):
                            parsed = packed_resp["parsed"]
                            if "rsat_subjective" in parsed:
                                subj = float(parsed["rsat_subjective"])
                                del_overrides["RSat"] = float(0.2 * base_rsat + 0.2 * base_tda + 0.6 * subj)
                                del_override_details["RSat_packed_llm"] = packed_resp
                                del_override_details["RSat_rule"] = {"slide_count_fit": base_rsat, "TDA": base_tda, "raw": base_rsat_details}
                            if "ssc" in parsed:
                                del_overrides["SSC"] = float(parsed["ssc"])
                                del_override_details["SSC_packed_llm"] = packed_resp
                            if "trn" in parsed:
                                tda = float(base_tdq_details.get("TDA", 0.0))
                                psp = float(base_tdq_details.get("PSP", 0.0))
                                trn = float(parsed["trn"])
                                del_overrides["TDQ"] = float((tda + psp + trn) / 3.0)
                                del_override_details["TRN_packed_llm"] = packed_resp
                            if "fidelity" in parsed:
                                art_overrides["F_text"] = float(parsed["fidelity"])
                                art_override_details["F_text_packed_llm"] = packed_resp
                    except Exception as e:
                        del_override_details["packed_llm_error"] = {"error": str(e)}
                else:
                    try:
                        rsat_payload = {"U": reqs.get("default", {}), "deck": deck_summary}
                        rsat_resp = judge_obj.judge_json(rubrics.RSAT_RUBRIC, rsat_payload)
                        if rsat_resp.get("ok") and isinstance(rsat_resp.get("parsed"), dict) and "score" in rsat_resp["parsed"]:
                            subj = float(rsat_resp["parsed"]["score"])
                            del_overrides["RSat"] = float(0.2 * base_rsat + 0.2 * base_tda + 0.6 * subj)
                            del_override_details["RSat_llm"] = rsat_resp
                            del_override_details["RSat_rule"] = {"slide_count_fit": base_rsat, "TDA": base_tda, "raw": base_rsat_details}
                    except Exception as e:
                        del_override_details["RSat_llm_error"] = {"error": str(e)}

                    try:
                        ssc_payload = {"slides": deck_summary["slides"]}
                        ssc_resp = judge_obj.judge_json(rubrics.SSC_RUBRIC, ssc_payload)
                        if ssc_resp.get("ok") and isinstance(ssc_resp.get("parsed"), dict) and "score" in ssc_resp["parsed"]:
                            del_overrides["SSC"] = float(ssc_resp["parsed"]["score"])
                            del_override_details["SSC_llm"] = ssc_resp
                    except Exception as e:
                        del_override_details["SSC_llm_error"] = {"error": str(e)}

                    try:
                        trn_payload = {
                            "slides": [
                                {
                                    "index": s.slide_index,
                                    "title": (s.text_final.split("\n", 1)[0] if s.text_final else ""),
                                    "notes_head": (s.notes.split("\n", 1)[0] if s.notes else ""),
                                }
                                for s in deck_obj.slides[:20]
                            ]
                        }
                        trn_resp = judge_obj.judge_json(rubrics.TRN_RUBRIC, trn_payload)
                        if trn_resp.get("ok") and isinstance(trn_resp.get("parsed"), dict) and "score" in trn_resp["parsed"]:
                            tda = float(base_tdq_details.get("TDA", 0.0))
                            psp = float(base_tdq_details.get("PSP", 0.0))
                            trn = float(trn_resp["parsed"]["score"])
                            del_overrides["TDQ"] = float((tda + psp + trn) / 3.0)
                            del_override_details["TRN_llm"] = trn_resp
                    except Exception as e:
                        del_override_details["TRN_llm_error"] = {"error": str(e)}

                    try:
                        fid_payload = {"items": fidelity_items}
                        fid_resp = judge_obj.judge_json(rubrics.FIDELITY_RUBRIC, fid_payload)
                        if fid_resp.get("ok") and isinstance(fid_resp.get("parsed"), dict) and "score" in fid_resp["parsed"]:
                            art_overrides["F_text"] = float(fid_resp["parsed"]["score"])
                            art_override_details["F_text_llm"] = fid_resp
                    except Exception as e:
                        art_override_details["F_text_llm_error"] = {"error": str(e)}

            m_art = compute_artifact_metrics_with_overrides(
                src_ok,
                deck_ok,
                source_obj,
                deck_obj,
                embedder=embedder,
                overrides=art_overrides or None,
                override_details=art_override_details or None,
            )
            m_del = compute_delivery_metrics_with_overrides(
                deck_ok,
                deck_obj,
                embedder=embedder,
                duration_seconds=duration_seconds,
                wpm=wpm,
                overrides=del_overrides or None,
                override_details=del_override_details or None,
                f_text=m_art.F_text,
            )
            agg = aggregate_scores(m_art, m_del, weights=weights)

            beta = float(weights["artifact"]["beta_text_vs_vis"])
            gamma = float(weights["artifact"]["gamma_legibility_vs_human"])
            fid = beta * m_art.F_text + (1 - beta) * m_art.F_vis
            read = gamma * m_art.L + (1 - gamma) * m_art.A

            a_w = weights["artifact"]
            d_w = weights["delivery"]

            long_rows.extend(
                [
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "ACSR",
                        "value": m_art.ACSR,
                        "source": "rule",
                        "weight": float(a_w["alpha_stab"]),
                        "weighted_value": float(a_w["alpha_stab"]) * float(m_art.ACSR),
                        "leaderboard": "artifact",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "F_text",
                        "value": m_art.F_text,
                        "source": "rule/llm/proxy",
                        "weight": float(a_w["alpha_fid"]) * beta,
                        "weighted_value": float(a_w["alpha_fid"]) * beta * float(m_art.F_text),
                        "leaderboard": "artifact",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "F_vis",
                        "value": m_art.F_vis,
                        "source": "rule",
                        "weight": float(a_w["alpha_fid"]) * (1 - beta),
                        "weighted_value": float(a_w["alpha_fid"]) * (1 - beta) * float(m_art.F_vis),
                        "leaderboard": "artifact",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "L",
                        "value": m_art.L,
                        "source": "rule",
                        "weight": float(a_w["alpha_read"]) * gamma,
                        "weighted_value": float(a_w["alpha_read"]) * gamma * float(m_art.L),
                        "leaderboard": "artifact",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "A",
                        "value": m_art.A,
                        "source": "proxy",
                        "weight": float(a_w["alpha_read"]) * (1 - gamma),
                        "weighted_value": float(a_w["alpha_read"]) * (1 - gamma) * float(m_art.A),
                        "leaderboard": "artifact",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "S_Artifact",
                        "value": agg.S_Artifact,
                        "source": "aggregate",
                        "weight": 1.0,
                        "weighted_value": agg.S_Artifact,
                        "leaderboard": "artifact",
                    },
                ]
            )

            long_rows.extend(
                [
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "RSat",
                        "value": m_del.RSat,
                        "source": "rule/llm",
                        "weight": float(d_w["omega_RSat"]),
                        "weighted_value": float(d_w["omega_RSat"]) * float(m_del.RSat),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "NDC",
                        "value": m_del.NDC,
                        "source": "proxy",
                        "weight": float(d_w["omega_NDC"]),
                        "weighted_value": float(d_w["omega_NDC"]) * float(m_del.NDC),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "SSC",
                        "value": m_del.SSC,
                        "source": "rule/llm",
                        "weight": float(d_w["omega_SSC"]),
                        "weighted_value": float(d_w["omega_SSC"]) * float(m_del.SSC),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "TDQ",
                        "value": m_del.TDQ,
                        "source": "rule/llm",
                        "weight": float(d_w["omega_TDQ"]),
                        "weighted_value": float(d_w["omega_TDQ"]) * float(m_del.TDQ),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "ACQ",
                        "value": m_del.ACQ,
                        "source": "proxy",
                        "weight": float(d_w["omega_ACQ"]),
                        "weighted_value": float(d_w["omega_ACQ"]) * float(m_del.ACQ),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "RR",
                        "value": m_del.RR,
                        "source": "proxy",
                        "weight": float(d_w["omega_RR"]),
                        "weighted_value": float(d_w["omega_RR"]) * float(m_del.RR),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "ACSR_in_delivery",
                        "value": m_art.ACSR,
                        "source": "rule",
                        "weight": float(d_w["omega_stab"]),
                        "weighted_value": float(d_w["omega_stab"]) * float(m_art.ACSR),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "Fidelity_in_delivery",
                        "value": fid,
                        "source": "rule/llm/proxy",
                        "weight": float(d_w["omega_fid"]),
                        "weighted_value": float(d_w["omega_fid"]) * float(fid),
                        "leaderboard": "delivery",
                    },
                    {
                        "instance_id": inst.instance_id,
                        "system": system,
                        "metric": "S_Delivery",
                        "value": agg.S_Delivery,
                        "source": "aggregate",
                        "weight": 1.0,
                        "weighted_value": agg.S_Delivery,
                        "leaderboard": "delivery",
                    },
                ]
            )

            score_rows.append(
                {
                    "instance_id": inst.instance_id,
                    "domain": inst.domain,
                    "subpath": inst.subpath,
                    "paper_id": inst.paper_id,
                    "system": system,
                    "primary_artifact": primary.artifact_path,
                    "primary_type": primary.artifact_type,
                    "judge": judge,
                    "judge_enabled": judge_enabled,
                    "source_ok": src_ok,
                    "deck_ok": deck_ok,
                    "deck_error": deck_err,
                    "ACSR": m_art.ACSR,
                    "F_rouge": m_art.F_rouge,
                    "F_bert": m_art.F_bert,
                    "F_text": m_art.F_text,
                    "F_vis": m_art.F_vis,
                    "L": m_art.L,
                    "A": m_art.A,
                    "RSat": m_del.RSat,
                    "SSC": m_del.SSC,
                    "TDQ": m_del.TDQ,
                    "ACQ": getattr(m_del, "ACQ", 0.0),
                    "RR": getattr(m_del, "RR", 0.0),
                    "NDC": getattr(m_del, "NDC", 0.0),
                    "S_Artifact": agg.S_Artifact,
                    "S_Delivery": agg.S_Delivery,
                }
            )

            detail_rows.append(
                {
                    "instance_id": inst.instance_id,
                    "system": system,
                    "primary_artifact": primary.artifact_path,
                    "judge": judge,
                    "judge_enabled": judge_enabled,
                    "artifact_details": m_art.details,
                    "delivery_details": m_del.details,
                    "weights": weights,
                    "ocr": {"mode": ocr_cfg.mode, "url": ocr_cfg.url, "error": ocr_error},
                }
            )

            if pbar is not None:
                pbar.update(1)

    if pbar is not None:
        pbar.close()

    combined_score_rows = score_rows
    combined_detail_rows = detail_rows
    combined_long_rows = long_rows

    if write_mode == "insert":
        combined_score_rows = existing_score_rows + score_rows
        combined_detail_rows = existing_detail_rows + detail_rows
        combined_long_rows = existing_long_rows + long_rows
    elif write_mode == "overwrite" and systems_set is not None and existing_score_rows:
        combined_score_rows = [r for r in existing_score_rows if str(r.get("system", "")) not in systems_set] + score_rows
        combined_detail_rows = [r for r in existing_detail_rows if str(r.get("system", "")) not in systems_set] + detail_rows
        combined_long_rows = [r for r in existing_long_rows if str(r.get("system", "")) not in systems_set] + long_rows

    combined_score_rows.sort(key=lambda r: (str(r.get("system", "")), str(r.get("instance_id", ""))))
    combined_detail_rows.sort(key=lambda r: (str(r.get("system", "")), str(r.get("instance_id", ""))))
    combined_long_rows.sort(
        key=lambda r: (
            str(r.get("system", "")),
            str(r.get("instance_id", "")),
            str(r.get("leaderboard", "")),
            str(r.get("metric", "")),
        )
    )

    write_scores_csv(combined_score_rows, paths.scores_dir / "scores.csv")
    write_jsonl(paths.scores_dir / "details.jsonl", combined_detail_rows)
    write_metrics_long_csv(combined_long_rows, paths.scores_dir / "metrics_long.csv")

    import pandas as pd

    df = pd.DataFrame(combined_score_rows)
    if not df.empty:
        agg_cols = [
            "S_Artifact",
            "S_Delivery",
            "ACSR",
            "F_rouge",
            "F_bert",
            "F_text",
            "F_vis",
            "L",
            "A",
            "RSat",
            "SSC",
            "TDQ",
            "ACQ",
            "RR",
            "NDC",
        ]
        agg_map = {c: "mean" for c in agg_cols if c in df.columns}
        sys_df = df.groupby("system").agg(agg_map).reset_index()
        sys_df.to_csv(paths.scores_dir / "systems.csv", index=False)
        write_leaderboard_md(sys_df, paths.reports_dir / "leaderboard.md")

    return score_rows
