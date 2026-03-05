from __future__ import annotations

import argparse
import sys
from pathlib import Path


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

from deepslide_eval.reporting import write_leaderboard_md  # noqa: E402

from role_paths import RoleEvalPaths  # noqa: E402
from role_scan import scan_role  # noqa: E402


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
    eval_p.add_argument("--systems", type=str, default=None, help="comma-separated, e.g. manus,gamma")
    eval_p.add_argument("--judge", type=str, default="none", choices=["none", "llm", "hybrid"])
    eval_p.add_argument("--llm-mode", type=str, default="packed", choices=["packed", "per_metric"])
    eval_p.add_argument("--write-mode", type=str, default="overwrite", choices=["insert", "overwrite"])

    sub.add_parser("report")

    args = parser.parse_args()
    paths = RoleEvalPaths(repo_root=REPO_ROOT)

    if args.cmd == "scan":
        scan_role(paths, source_pdf=args.source_pdf, paper_id=args.paper_id)
        return 0

    if args.cmd == "evaluate":
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
        return 0

    if args.cmd == "report":
        import pandas as pd

        systems_csv = paths.scores_dir / "systems.csv"
        if not systems_csv.exists():
            raise FileNotFoundError(str(systems_csv))
        df = pd.read_csv(systems_csv)
        write_leaderboard_md(df, paths.reports_dir / "leaderboard.md")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
