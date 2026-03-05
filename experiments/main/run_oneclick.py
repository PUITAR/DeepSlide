from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    evaluation_root = Path(__file__).resolve().parent
    repo_root = evaluation_root.parent.parent
    # load_dotenv(repo_root / "deepslide-v4" / ".env")
    load_dotenv(repo_root / "deepslide" / ".env")
    load_dotenv(evaluation_root / ".env")

    def run_step(args):
        return subprocess.run([sys.executable, "run_eval.py", *args], cwd=str(evaluation_root), env=os.environ.copy()).returncode

    if run_step(["scan"]) != 0:
        return 1
    if run_step(["evaluate", "--judge", "llm", "--llm-mode", "packed"]) != 0:
        return 1
    if run_step(["report"]) != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
