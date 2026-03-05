from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(12):
        if (p / "experiments").exists() and (p / "dataset").exists():
            return p
        p = p.parent
    return Path.cwd().resolve()


REPO_ROOT = _find_repo_root()
EVAL_PKG_ROOT = REPO_ROOT / "experiments" / "main"
sys.path.insert(0, str(EVAL_PKG_ROOT))

from deepslide_eval.llm.env import resolve_llm_env  # noqa: E402
from deepslide_eval.ocr.config import load_ocr_config  # noqa: E402
from deepslide_eval.reporting import write_leaderboard_md  # noqa: E402

from xr_kl_paths import XREvalPaths  # noqa: E402
from xr_kl_report import export_ablation_tables  # noqa: E402
from xr_kl_scan import scan_xr_kl  # noqa: E402


def _load_dotenvs(repo_root: Path) -> None:
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(repo_root / "experiments" / "main" / ".env", override=False)
    load_dotenv(repo_root / "experiments" / "xr" / ".env", override=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan_p = sub.add_parser("scan")
    scan_p.add_argument("--source-pdf", type=str, default=None)
    scan_p.add_argument("--paper-id", type=str, default=None)

    eval_p = sub.add_parser("evaluate")
    eval_p.add_argument("--embed", type=str, default="tfidf", choices=["tfidf", "st"])
    eval_p.add_argument("--st-model", type=str, default=None)
    eval_p.add_argument("--limit", type=int, default=None)
    eval_p.add_argument("--systems", type=str, default=None, help="comma-separated, e.g. L8192_K5,L4096_K5")
    eval_p.add_argument("--judge", type=str, default="llm", choices=["llm", "hybrid"])
    eval_p.add_argument("--llm-mode", type=str, default="packed", choices=["packed", "per_metric"])
    eval_p.add_argument("--write-mode", type=str, default="overwrite", choices=["insert", "overwrite"])
    eval_p.add_argument("--require-judge", type=str, default="1", choices=["0", "1"])
    eval_p.add_argument("--require-ocr", type=str, default="1", choices=["0", "1"])
    eval_p.add_argument("--ocr-provider", type=str, default=None)
    eval_p.add_argument("--ocr-url", type=str, default=None)
    eval_p.add_argument("--ocr-mode", type=str, default="on", choices=["auto", "on", "off"])

    eval_s_p = sub.add_parser("evaluate-s")
    eval_s_p.add_argument("--embed", type=str, default="tfidf", choices=["tfidf", "st"])
    eval_s_p.add_argument("--st-model", type=str, default=None)
    eval_s_p.add_argument("--limit", type=int, default=None)
    eval_s_p.add_argument("--judge", type=str, default="llm", choices=["llm", "hybrid"])
    eval_s_p.add_argument("--llm-mode", type=str, default="packed", choices=["packed", "per_metric"])
    eval_s_p.add_argument("--write-mode", type=str, default="insert", choices=["insert", "overwrite"])
    eval_s_p.add_argument("--require-judge", type=str, default="1", choices=["0", "1"])
    eval_s_p.add_argument("--require-ocr", type=str, default="1", choices=["0", "1"])
    eval_s_p.add_argument("--ocr-provider", type=str, default=None)
    eval_s_p.add_argument("--ocr-url", type=str, default=None)
    eval_s_p.add_argument("--ocr-mode", type=str, default="on", choices=["auto", "on", "off"])

    sub.add_parser("report")

    args = parser.parse_args()
    paths = XREvalPaths(repo_root=REPO_ROOT)
    _load_dotenvs(REPO_ROOT)

    if args.cmd == "scan":
        scan_xr_kl(paths, source_pdf=args.source_pdf, paper_id=args.paper_id)
        return 0

    if args.cmd == "evaluate":
        if args.ocr_provider is not None:
            os.environ["EVAL_OCR_PROVIDER"] = str(args.ocr_provider)
        if args.ocr_url is not None:
            os.environ["EVAL_OCR_URL"] = str(args.ocr_url)
        if args.ocr_mode is not None:
            os.environ["EVAL_OCR_MODE"] = str(args.ocr_mode)

        if args.require_judge == "1":
            env = resolve_llm_env("JUDGE")
            if not env.api_key:
                raise RuntimeError("LLM judge is required but missing EVAL_MODEL_API_KEY (or OPENAI_API_KEY/LLM_API_KEY)")

        if args.require_ocr == "1":
            ocr_cfg = load_ocr_config()
            if (ocr_cfg.provider or "").strip().lower() in {"", "none"}:
                raise RuntimeError("OCR is required but EVAL_OCR_PROVIDER is not configured")
            if (ocr_cfg.mode or "").strip().lower() == "off":
                raise RuntimeError("OCR is required but EVAL_OCR_MODE=off")

        from deepslide_eval.pipeline import evaluate  # noqa: E402

        systems = [s.strip() for s in (args.systems or "").split(",") if s.strip()] or None
        evaluate(
            paths,
            embed_method=args.embed,
            st_model=args.st_model,
            limit_instances=args.limit,
            systems=systems,
            judge=args.judge,
            llm_mode=args.llm_mode,
            write_mode=args.write_mode,
        )
        export_ablation_tables(paths)
        return 0

    if args.cmd == "evaluate-s":
        if args.ocr_provider is not None:
            os.environ["EVAL_OCR_PROVIDER"] = str(args.ocr_provider)
        if args.ocr_url is not None:
            os.environ["EVAL_OCR_URL"] = str(args.ocr_url)
        if args.ocr_mode is not None:
            os.environ["EVAL_OCR_MODE"] = str(args.ocr_mode)

        if args.require_judge == "1":
            env = resolve_llm_env("JUDGE")
            if not env.api_key:
                raise RuntimeError("LLM judge is required but missing EVAL_MODEL_API_KEY (or OPENAI_API_KEY/LLM_API_KEY)")

        if args.require_ocr == "1":
            ocr_cfg = load_ocr_config()
            if (ocr_cfg.provider or "").strip().lower() in {"", "none"}:
                raise RuntimeError("OCR is required but EVAL_OCR_PROVIDER is not configured")
            if (ocr_cfg.mode or "").strip().lower() == "off":
                raise RuntimeError("OCR is required but EVAL_OCR_MODE=off")

        outputs_path = paths.manifests_dir / "outputs.jsonl"
        if not outputs_path.exists():
            raise FileNotFoundError(f"missing manifests: run scan first: {outputs_path}")

        s_systems = set()
        with outputs_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                sys_name = str(obj.get("system") or "")
                if sys_name.startswith("S"):
                    s_systems.add(sys_name)
        systems = sorted(s_systems, key=lambda x: float(x[1:]) if x[1:].replace(".", "", 1).isdigit() else x)
        if not systems:
            raise RuntimeError("no S systems found in outputs.jsonl; check experiments/.cache/xr/S and rerun scan")

        from deepslide_eval.pipeline import evaluate  # noqa: E402

        evaluate(
            paths,
            embed_method=args.embed,
            st_model=args.st_model,
            limit_instances=args.limit,
            systems=systems,
            judge=args.judge,
            llm_mode=args.llm_mode,
            write_mode=args.write_mode,
        )
        export_ablation_tables(paths)
        return 0

    if args.cmd == "report":
        import pandas as pd

        systems_csv = paths.scores_dir / "systems.csv"
        if not systems_csv.exists():
            raise FileNotFoundError(str(systems_csv))
        df = pd.read_csv(systems_csv)
        write_leaderboard_md(df, paths.reports_dir / "leaderboard.md")
        export_ablation_tables(paths)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
