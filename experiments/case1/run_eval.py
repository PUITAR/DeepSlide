from __future__ import annotations

import argparse
import sys
from pathlib import Path

from case1_eval import REPO_ROOT, _load_dotenvs, default_output_paths, evaluate_case1, scan_case1_runs
from case1_paths import Case1EvalPaths


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("unpack")

    eval_p = sub.add_parser("evaluate")
    eval_p.add_argument("--wpm", type=int, default=150)
    eval_p.add_argument("--out", type=str, default=None, help="output csv path")
    eval_p.add_argument("--systems", type=str, default=None, help="comma-separated systems, e.g. deepslide,manus")
    eval_p.add_argument("--judge", type=str, default="llm", choices=["llm"])
    eval_p.add_argument("--ocr", type=str, default="auto", choices=["auto"])

    args = parser.parse_args()
    paths = Case1EvalPaths(repo_root=REPO_ROOT)

    _load_dotenvs(paths.evaluation_root, REPO_ROOT)

    systems = [s.strip() for s in (args.systems or "").split(",") if s.strip()]
    runs = scan_case1_runs(paths.outputs_cache_root, systems=systems or None)
    if args.cmd == "unpack":
        print(f"ok: extracted {len(runs)} runs under {paths.outputs_cache_root}")
        return 0

    if args.cmd == "evaluate":
        cache_dir, out_csv, out_jsonl = default_output_paths(REPO_ROOT)
        if args.out:
            out_csv = Path(args.out).expanduser().resolve()
        evaluate_case1(
            runs=runs,
            cache_dir=cache_dir,
            out_csv=out_csv,
            out_jsonl=out_jsonl,
            wpm=int(args.wpm),
            judge_mode=str(args.judge),
            ocr_mode=str(args.ocr),
        )
        print(f"ok: wrote {out_csv}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
