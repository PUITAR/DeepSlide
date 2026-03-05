from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd


def write_scores_csv(rows: List[Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)


def write_leaderboard_md(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "system",
        "S_Artifact",
        "S_Delivery",
        "ACSR",
        "F_text",
        "F_vis",
        "L",
        "RSat",
        "SSC",
        "TDQ",
    ]
    cols = [c for c in cols if c in df.columns]
    table = df[cols].sort_values(["S_Delivery", "S_Artifact"], ascending=False)
    md = "# Leaderboard\n\n" + table.to_markdown(index=False) + "\n"
    out_path.write_text(md, encoding="utf-8")


def write_metrics_long_csv(rows: List[Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
