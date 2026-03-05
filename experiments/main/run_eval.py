from __future__ import annotations

import argparse

from deepslide_eval.paths import default_paths
from deepslide_eval.pipeline import evaluate, scan
from deepslide_eval.reporting import write_leaderboard_md


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan")

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
    paths = default_paths()
    if args.cmd == "scan":
        scan(paths)
        return 0

    if args.cmd == "evaluate":
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
