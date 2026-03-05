from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def find_repo_root(start: Optional[Path] = None) -> Path:
    p = (start or Path(__file__)).resolve()
    for _ in range(12):
        if (p / "experiments").exists() and (p / "dataset").exists():
            return p
        p = p.parent
    return Path.cwd().resolve()


REPO_ROOT = find_repo_root()
EVAL_PKG_ROOT = REPO_ROOT / "experiments" / "main"
sys.path.insert(0, str(EVAL_PKG_ROOT))

from deepslide_eval.alignment import Embedder  # noqa: E402
from deepslide_eval.extractors.common import DeckContent, SlideText  # noqa: E402
from deepslide_eval.extractors.pdf_extractor import extract_deck_from_pdf  # noqa: E402
from deepslide_eval.io_utils import ensure_dir, sha1_bytes, try_read_text, write_json  # noqa: E402
from deepslide_eval.llm import rubrics  # noqa: E402
from deepslide_eval.llm.env import load_eval_dotenv, resolve_llm_env  # noqa: E402
from deepslide_eval.llm.judge import JudgeConfig, LLMJudge  # noqa: E402
from deepslide_eval.metrics.artifact import compute_legibility  # noqa: E402
from deepslide_eval.metrics.delivery import compute_rsat, compute_ssc, compute_tdq, compute_delivery_metrics_with_overrides  # noqa: E402
from deepslide_eval.ocr.augment import augment_deck_with_ocr  # noqa: E402
from deepslide_eval.ocr.config import load_ocr_config  # noqa: E402


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


def _parse_condition(stem: str) -> Tuple[str, int]:
    s = stem.strip().lower().replace("_", "-")
    if "-" not in s:
        raise ValueError(f"bad_zip_stem: {stem}")
    aud, dur = s.rsplit("-", 1)
    dur_min = int(dur)
    return aud, dur_min


def unpack_case1_zips(cache_root: Path) -> List[Dict[str, Any]]:
    ensure_dir(cache_root)
    zips = sorted([p for p in cache_root.glob("*.zip") if p.is_file()], key=lambda x: x.name)
    runs: List[Dict[str, Any]] = []
    for z in zips:
        audience, dur_min = _parse_condition(z.stem)
        out_dir = cache_root / z.stem
        base_pdf = out_dir / "recipe" / "base.pdf"
        if not base_pdf.exists():
            ensure_dir(out_dir)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(out_dir)
        if not base_pdf.exists():
            raise FileNotFoundError(str(base_pdf))
        runs.append(
            {
                "condition": z.stem,
                "audience": audience,
                "duration_min": dur_min,
                "base_pdf": str(base_pdf),
                "root_dir": str(out_dir),
            }
        )
    if not runs:
        raise FileNotFoundError(f"no_zip_found_under: {cache_root}")
    return runs


def scan_case1_runs(cache_root: Path, systems: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    ensure_dir(cache_root)
    allow = {s.strip().lower() for s in (systems or []) if s.strip()}

    runs: List[Dict[str, Any]] = []

    zips = sorted([p for p in cache_root.glob("*.zip") if p.is_file()], key=lambda x: x.name)
    for z in zips:
        audience, dur_min = _parse_condition(z.stem)
        out_dir = cache_root / z.stem
        base_pdf = out_dir / "recipe" / "base.pdf"
        if not base_pdf.exists():
            ensure_dir(out_dir)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(out_dir)
        if not base_pdf.exists():
            raise FileNotFoundError(str(base_pdf))
        runs.append(
            {
                "condition": z.stem,
                "audience": audience,
                "duration_min": dur_min,
                "system": "deepslide",
                "artifact_type": "pdf",
                "artifact_path": str(base_pdf),
                "root_dir": str(out_dir),
            }
        )

    if (not allow) or ("deepslide" in allow):
        for base_pdf in sorted(cache_root.glob("deepslide/*/recipe/base.pdf")):
            condition = base_pdf.parent.parent.name
            try:
                audience, dur_min = _parse_condition(condition)
            except Exception:
                continue
            runs.append(
                {
                    "condition": condition,
                    "audience": audience,
                    "duration_min": dur_min,
                    "system": "deepslide",
                    "artifact_type": "pdf",
                    "artifact_path": str(base_pdf),
                    "root_dir": str(base_pdf.parent.parent.parent),
                }
            )

    if (not allow) or ("manus" in allow):
        for pptx in sorted(cache_root.glob("manus/*.pptx")):
            condition = pptx.stem
            try:
                audience, dur_min = _parse_condition(condition)
            except Exception:
                continue
            runs.append(
                {
                    "condition": condition,
                    "audience": audience,
                    "duration_min": dur_min,
                    "system": "manus",
                    "artifact_type": "pptx",
                    "artifact_path": str(pptx),
                    "root_dir": str(pptx.parent),
                }
            )

    uniq: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in runs:
        k = (str(r.get("system", "")), str(r.get("condition", "")))
        if k not in uniq:
            uniq[k] = r
    out = list(uniq.values())
    out.sort(key=lambda x: (str(x.get("condition", "")), str(x.get("system", ""))))
    if not out:
        raise FileNotFoundError(f"no_runs_found_under: {cache_root}")
    return out


def _load_dotenvs(evaluation_root: Path, repo_root: Path) -> None:
    load_eval_dotenv(evaluation_root)
    extra = repo_root / "deepslide-v4" / ".env"
    if extra.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(extra)
        except Exception:
            pass


def evaluate_case1(
    runs: Iterable[Dict[str, Any]],
    cache_dir: Path,
    out_csv: Path,
    out_jsonl: Path,
    wpm: int = 150,
    judge_mode: str = "auto",
    ocr_mode: str = "auto",
) -> None:
    ensure_dir(cache_dir)
    ensure_dir(out_csv.parent)
    ensure_dir(out_jsonl.parent)

    ocr_mode_norm = str(ocr_mode).strip().lower()
    if ocr_mode_norm == "none":
        raise RuntimeError("OCR must be enabled for case1: pass --ocr auto and configure EVAL_OCR_* (or DEFAULT_VLM_*) env vars")
    ocr_cfg = load_ocr_config()
    if ocr_cfg.provider == "none":
        raise RuntimeError("OCR is disabled: set EVAL_OCR_* or DEFAULT_VLM_* env vars")

    judge_mode_norm = str(judge_mode).strip().lower()
    env = resolve_llm_env("JUDGE")
    if judge_mode_norm == "none":
        raise RuntimeError("LLM judge must be enabled for case1: pass --judge llm and configure EVAL_JUDGE_MODEL_* env vars")
    if not env.api_key:
        raise RuntimeError("LLM judge is disabled: set EVAL_JUDGE_MODEL_API_KEY (or EVAL_MODEL_API_KEY/OPENAI_API_KEY)")
    judge = LLMJudge(cache_dir=cache_dir / "judgements", config=JudgeConfig(agent_name="JUDGE"))
    embedder = Embedder(method="tfidf")

    rows: List[Dict[str, Any]] = []
    with out_jsonl.open("w", encoding="utf-8") as f_jsonl:
        for run in runs:
            audience = str(run["audience"])
            dur_min = int(run["duration_min"])
            duration_seconds = dur_min * 60
            system = str(run.get("system") or "")
            artifact_type = str(run.get("artifact_type") or "").lower()
            artifact_path = str(run.get("artifact_path") or run.get("base_pdf") or "")
            if not artifact_type:
                artifact_type = "pdf" if artifact_path.lower().endswith(".pdf") else "pptx" if artifact_path.lower().endswith(".pptx") else ""
            cache_key = _artifact_cache_key(artifact_path)
            deck_cache_path = cache_dir / f"deck_{cache_key}.json"

            deck_ok = False
            deck_content = None
            deck_err = None
            if deck_cache_path.exists():
                try:
                    obj = json.loads(deck_cache_path.read_text(encoding="utf-8"))
                    deck_ok = bool(obj.get("ok"))
                    deck_content = obj.get("content") if deck_ok else None
                    deck_err = obj.get("error")
                except Exception:
                    deck_ok = False

            if not deck_ok:
                if artifact_type == "pptx" or artifact_path.lower().endswith(".pptx"):
                    from deepslide_eval.extractors.pptx_extractor import extract_deck_from_pptx

                    dres = extract_deck_from_pptx(Path(artifact_path))
                else:
                    dres = extract_deck_from_pdf(Path(artifact_path))
                deck_ok = dres.ok
                deck_content = asdict(dres.content) if dres.ok and dres.content is not None else None
                deck_err = dres.error
                write_json(deck_cache_path, {"ok": deck_ok, "error": deck_err, "diagnostics": dres.diagnostics, "content": deck_content})

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

            if deck_ok and deck_obj is not None and system == "deepslide" and str(artifact_path).endswith("/recipe/base.pdf"):
                deck_obj = _inject_deepslide_speech_notes(deck_obj, base_pdf_path=str(artifact_path))

            ocr_error: Optional[str] = None
            if deck_ok and deck_obj is not None:
                try:
                    if ocr_cfg is not None:
                        deck_obj = augment_deck_with_ocr(deck_obj, cache_root=cache_dir, ocr_cfg=ocr_cfg)
                except Exception as e:
                    ocr_error = str(e)

            if deck_ok and deck_obj is not None:
                deck_final_path = cache_dir / f"deck_final_{cache_key}.json"
                ocr_meta = (
                    {"mode": ocr_cfg.mode, "provider": ocr_cfg.provider, "url": ocr_cfg.url}
                    if ocr_cfg is not None
                    else {"mode": "none", "provider": "none", "url": None}
                )
                write_json(
                    deck_final_path,
                    {
                        "ok": True,
                        "artifact_path": deck_obj.artifact_path,
                        "artifact_type": deck_obj.artifact_type,
                        "ocr": {**ocr_meta, "error": ocr_error},
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

            req_profile = {
                "audience": audience,
                "duration_minutes": dur_min,
                "duration_seconds": duration_seconds,
                "wpm": wpm,
                "focus_priorities": "balanced",
                "style_constraints": "clear, structured, and concise",
            }

            llm_ok = False
            llm_parsed: Optional[Dict[str, Any]] = None
            packed_resp: Optional[Dict[str, Any]] = None

            if deck_ok and deck_obj is not None:
                deck_summary = {
                    "slides": [
                        {"index": s.slide_index, "slide_text": s.text_final, "notes": s.notes}
                        for s in deck_obj.slides[:12]
                    ]
                }
                try:
                    packed_payload = {"U": req_profile, "deck": deck_summary, "fidelity_items": []}
                    packed_resp = judge.judge_json(rubrics.PACKED_JUDGE_RUBRIC, packed_payload)
                    if packed_resp.get("ok") and isinstance(packed_resp.get("parsed"), dict):
                        llm_ok = True
                        llm_parsed = packed_resp["parsed"]
                except Exception as e:
                    packed_resp = {"ok": False, "error": str(e)}

            if deck_ok and deck_obj is not None:
                rsat_rule, rsat_rule_details = compute_rsat(deck_obj, duration_seconds=duration_seconds)
                tdq_rule, tdq_rule_details = compute_tdq(deck_obj, duration_seconds=duration_seconds, wpm=wpm)
                ssc_rule, ssc_rule_details = compute_ssc(deck_obj, embedder=embedder)
                tda = float(tdq_rule_details.get("TDA", 0.0))
                psp = float(tdq_rule_details.get("PSP", 0.0))
                trn_rule = float(tdq_rule_details.get("TRN", 0.0))
            else:
                rsat_rule, rsat_rule_details = 0.0, {"reason": "missing_deck"}
                tdq_rule, tdq_rule_details = 0.0, {"reason": "missing_deck"}
                ssc_rule, ssc_rule_details = 0.0, {"reason": "missing_deck"}
                tda, psp, trn_rule = 0.0, 0.0, 0.0

            overrides: Dict[str, float] = {}
            override_details: Dict[str, Dict] = {}
            trn_llm: Optional[float] = None
            rsat_subj: Optional[float] = None
            ssc_llm: Optional[float] = None

            if llm_ok and llm_parsed is not None:
                try:
                    if "rsat_subjective" in llm_parsed:
                        rsat_subj = float(llm_parsed["rsat_subjective"])
                        overrides["RSat"] = float(0.2 * rsat_rule + 0.2 * tda + 0.6 * rsat_subj)
                    if "ssc" in llm_parsed:
                        ssc_llm = float(llm_parsed["ssc"])
                        overrides["SSC"] = float(ssc_llm)
                    if "trn" in llm_parsed:
                        trn_llm = float(llm_parsed["trn"])
                        overrides["TDQ"] = float((tda + psp + trn_llm) / 3.0)
                    override_details["packed_llm"] = packed_resp or {}
                    override_details["rule"] = {
                        "RSat_rule": rsat_rule,
                        "RSat_rule_details": rsat_rule_details,
                        "TDQ_rule": tdq_rule,
                        "TDQ_rule_details": tdq_rule_details,
                        "SSC_rule": ssc_rule,
                        "SSC_rule_details": ssc_rule_details,
                    }
                except Exception as e:
                    llm_ok = False
                    override_details["packed_llm_error"] = {"error": str(e), "resp": packed_resp}

            del_m = compute_delivery_metrics_with_overrides(
                deck_ok=deck_ok,
                deck=deck_obj,
                embedder=embedder,
                duration_seconds=duration_seconds,
                wpm=wpm,
                overrides=overrides or None,
                override_details=override_details or None,
                f_text=0.0,
            )

            if deck_ok and deck_obj is not None:
                leg, leg_details = compute_legibility(deck_obj)
                slide_cnt = len(deck_obj.slides)
                ocr_used_ratio = float(sum(1 for s in deck_obj.slides if getattr(s, "ocr_used", False)) / max(1, slide_cnt))
                est_total_seconds = float(tdq_rule_details.get("est_total_seconds", 0.0))
                notes_words = int(sum(len([w for w in (s.notes or "").split() if w]) for s in deck_obj.slides))
            else:
                leg, leg_details = 0.0, {"reason": "missing_deck"}
                slide_cnt = 0
                ocr_used_ratio = 0.0
                est_total_seconds = 0.0
                notes_words = 0

            row: Dict[str, Any] = {
                "condition": str(run["condition"]),
                "audience": audience,
                "duration_min": dur_min,
                "duration_seconds": duration_seconds,
                "system": system or ("deepslide" if artifact_type == "pdf" else ""),
                "artifact_type": artifact_type,
                "artifact_path": artifact_path,
                "base_pdf": artifact_path,
                "slide_count": slide_cnt,
                "notes_word_count": notes_words,
                "ocr_provider": (ocr_cfg.provider if ocr_cfg is not None else "none"),
                "ocr_mode": (ocr_cfg.mode if ocr_cfg is not None else "none"),
                "ocr_used_ratio": ocr_used_ratio,
                "llm_judge_ok": llm_ok,
                "RSat": float(del_m.RSat),
                "TDQ": float(del_m.TDQ),
                "SSC": float(del_m.SSC),
                "Legibility": float(leg),
                "RSat_rule": float(rsat_rule),
                "TDQ_rule": float(tdq_rule),
                "SSC_rule": float(ssc_rule),
                "TDA_rule": float(tda),
                "PSP_rule": float(psp),
                "TRN_rule": float(trn_rule),
                "TRN_llm": trn_llm,
                "RSat_subjective_llm": rsat_subj,
                "SSC_llm": ssc_llm,
                "est_total_seconds_rule": est_total_seconds,
            }
            rows.append(row)

            f_jsonl.write(
                json.dumps(
                    {
                        "run": run,
                        "req_profile": req_profile,
                        "deck": {"ok": deck_ok, "error": deck_err, "artifact_cache_key": cache_key},
                        "ocr": {"provider": (ocr_cfg.provider if ocr_cfg is not None else "none"), "mode": (ocr_cfg.mode if ocr_cfg is not None else "none"), "error": ocr_error},
                        "llm": {"ok": llm_ok, "resp": packed_resp},
                        "metrics": {
                            "delivery": asdict(del_m),
                            "legibility": {"score": leg, "details": leg_details},
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def default_output_paths(repo_root: Path) -> Tuple[Path, Path, Path]:
    out_root = repo_root / "experiments" / "case1" / "outputs"
    return out_root / "caches", out_root / "scores" / "case1_metrics.csv", out_root / "scores" / "case1_details.jsonl"
