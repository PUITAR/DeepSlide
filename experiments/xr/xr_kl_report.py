from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from deepslide_eval.io_utils import ensure_dir

from xr_kl_paths import XREvalPaths


_SYS_LK_RE = re.compile(r"\bL(\d+)_K(\d+)\b", re.IGNORECASE)
_SYS_S_RE = re.compile(r"\bS([0-9]+(?:\.[0-9]+)?)\b", re.IGNORECASE)


def _parse_system_lk(system: str) -> Tuple[Optional[int], Optional[int]]:
    m = _SYS_LK_RE.search(system or "")
    if not m:
        return None, None
    try:
        return int(m.group(1)), int(m.group(2))
    except Exception:
        return None, None


def _parse_system_s(system: str) -> Optional[float]:
    m = _SYS_S_RE.search(system or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def export_ablation_tables(paths: XREvalPaths) -> Tuple[Path, Path]:
    ensure_dir(paths.reports_dir)
    systems_csv = paths.scores_dir / "systems.csv"
    if not systems_csv.exists():
        raise FileNotFoundError(str(systems_csv))

    df = pd.read_csv(systems_csv)
    if "system" not in df.columns:
        raise RuntimeError("missing column 'system' in systems.csv")

    ls, ks, ss = [], [], []
    for s in df["system"].astype(str).tolist():
        l, k = _parse_system_lk(s)
        ls.append(l)
        ks.append(k)
        ss.append(_parse_system_s(s))
    df["TRUNC_LEN"] = ls
    df["TopK"] = ks
    df["S"] = ss

    want = [
        "system",
        "TRUNC_LEN",
        "TopK",
        "S",
        "F_text",
        "SSC",
        "NDC",
        "F_vis",
        "S_Artifact",
        "S_Delivery",
    ]
    for c in want:
        if c not in df.columns:
            df[c] = None
    df_out = df[want].copy()

    baseline = df_out[(df_out["TRUNC_LEN"] == 8192) & (df_out["TopK"] == 5)]
    if len(baseline) >= 1:
        base = baseline.iloc[0]
        for m in ["F_text", "SSC", "NDC", "F_vis", "S_Artifact", "S_Delivery"]:
            try:
                df_out[f"Δ{m}"] = df_out[m].astype(float) - float(base[m])
            except Exception:
                df_out[f"Δ{m}"] = None
    else:
        for m in ["F_text", "SSC", "NDC", "F_vis", "S_Artifact", "S_Delivery"]:
            df_out[f"Δ{m}"] = None

    out_csv = paths.reports_dir / "ablation_scores.csv"
    df_out.sort_values(["TRUNC_LEN", "TopK", "S", "system"], na_position="last").to_csv(out_csv, index=False)

    def _fmt_table(dfx: pd.DataFrame) -> str:
        cols = ["system", "TRUNC_LEN", "TopK", "S", "F_text", "SSC", "NDC", "F_vis", "S_Artifact", "S_Delivery"]
        d = dfx[cols].copy()
        for c in ["TRUNC_LEN", "TopK", "S"]:
            if c in d.columns:
                d[c] = d[c].where(d[c].notna(), "")
        for c in ["F_text", "SSC", "NDC", "F_vis", "S_Artifact", "S_Delivery"]:
            try:
                d[c] = d[c].astype(float).round(4)
            except Exception:
                pass
        return d.to_markdown(index=False)

    kl_tbl = df_out[df_out["S"].isna()].copy()
    s_tbl = df_out[df_out["S"].notna()].copy()

    k_abl = kl_tbl[kl_tbl["TRUNC_LEN"] == 8192].sort_values(["TopK"])
    l_abl = kl_tbl[kl_tbl["TopK"] == 5].sort_values(["TRUNC_LEN"])
    s_abl = s_tbl.sort_values(["S"])
    all_tbl = df_out.sort_values(["TRUNC_LEN", "TopK", "S"])

    md = []
    md.append("# XR K/L/S 消融实验结果")
    md.append("")
    md.append("## 全量 (system=Ln_Km 或 Sx)")
    md.append("")
    md.append(_fmt_table(all_tbl))
    md.append("")
    md.append("## TopK 消融 (固定 TRUNC_LEN=8192)")
    md.append("")
    md.append(_fmt_table(k_abl))
    md.append("")
    md.append("## TRUNC_LEN 消融 (固定 TopK=5)")
    md.append("")
    md.append(_fmt_table(l_abl))
    md.append("")
    md.append("## S 消融")
    md.append("")
    md.append(_fmt_table(s_abl))
    md.append("")
    out_md = paths.reports_dir / "ablation_report.md"
    out_md.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")

    analysis_md = []
    analysis_md.append("# XR K/L/S 消融结论（自动草稿）")
    analysis_md.append("")
    analysis_md.append("## 基线")
    analysis_md.append("")
    if len(baseline) >= 1:
        base_sys = str(base.get("system"))
        analysis_md.append(f"- baseline: {base_sys} (TRUNC_LEN=8192, TopK=5)")
        for m in ["F_text", "SSC", "NDC", "F_vis", "S_Artifact", "S_Delivery"]:
            try:
                analysis_md.append(f"- {m}: {float(base[m]):.4f}")
            except Exception:
                analysis_md.append(f"- {m}: {base.get(m)}")
    else:
        analysis_md.append("- baseline 缺失：未找到 system=L8192_K5")
    analysis_md.append("")

    def _pick_best(dfx: pd.DataFrame, metric: str) -> Optional[pd.Series]:
        if metric not in dfx.columns:
            return None
        try:
            s = pd.to_numeric(dfx[metric], errors="coerce")
            if s.notna().sum() == 0:
                return None
            return dfx.loc[s.idxmax()]
        except Exception:
            return None

    analysis_md.append("## 现象摘要")
    analysis_md.append("")
    best_ndc = _pick_best(df_out, "NDC")
    if best_ndc is not None:
        analysis_md.append(f"- NDC 最优: {best_ndc['system']} (NDC={float(best_ndc['NDC']):.4f})")
    best_ftext = _pick_best(df_out, "F_text")
    if best_ftext is not None:
        analysis_md.append(f"- F_text 最优: {best_ftext['system']} (F_text={float(best_ftext['F_text']):.4f})")
    analysis_md.append("")
    analysis_md.append("### TopK (固定 TRUNC_LEN=8192)")
    analysis_md.append("")
    if len(k_abl) > 0:
        for _, r in k_abl.iterrows():
            try:
                analysis_md.append(
                    f"- {r['system']}: F_text={float(r['F_text']):.4f}, SSC={float(r['SSC']):.4f}, NDC={float(r['NDC']):.4f}, F_vis={float(r['F_vis']):.4f}"
                )
            except Exception:
                analysis_md.append(f"- {r.get('system')}")
    analysis_md.append("")
    analysis_md.append("### TRUNC_LEN (固定 TopK=5)")
    analysis_md.append("")
    if len(l_abl) > 0:
        for _, r in l_abl.iterrows():
            try:
                analysis_md.append(
                    f"- {r['system']}: F_text={float(r['F_text']):.4f}, SSC={float(r['SSC']):.4f}, NDC={float(r['NDC']):.4f}, F_vis={float(r['F_vis']):.4f}"
                )
            except Exception:
                analysis_md.append(f"- {r.get('system')}")
    analysis_md.append("")
    analysis_md.append("### S")
    analysis_md.append("")
    if len(s_abl) > 0:
        for _, r in s_abl.iterrows():
            try:
                analysis_md.append(
                    f"- {r['system']}: S={float(r['S']):g}, F_text={float(r['F_text']):.4f}, SSC={float(r['SSC']):.4f}, NDC={float(r['NDC']):.4f}, F_vis={float(r['F_vis']):.4f}"
                )
            except Exception:
                analysis_md.append(f"- {r.get('system')}")
    analysis_md.append("")

    analysis_md.append("## 解释（写论文可用的角度）")
    analysis_md.append("")
    analysis_md.append("- 将 TRUNC_LEN 与 TopK 合并称为 retrieval bandwidth；它优先影响“能否检索到正确 source nodes”，进而影响 F_text、以及由内容稳定性带来的 NDC/SSC。")
    analysis_md.append("- 典型模式是“带宽过小 → 证据缺失/选错节点 → F_text 与 NDC/SSC 同时下滑”；带宽过大 → 噪声上来 → NDC 可能下降（结构发散），同时 SSC 可能出现‘虚高但不好’（notes 变复述）。")
    analysis_md.append("")

    analysis_md.append("## 注意事项")
    analysis_md.append("")
    analysis_md.append("- 本次 report 只基于 systems.csv 的最终分数；若需要定位‘选错节点/没找到图表’的根因，建议同时查看 outputs/scores/details.jsonl 中每个 system 的 artifact_details。")
    analysis_md.append("- 如果希望严格满足“LLM 与 OCR 全开”，请在 experiments/xr/.env 配好 EVAL_MODEL_* 与 EVAL_OCR_*，然后用 run_eval.py evaluate 的默认参数跑一遍（默认 require-judge=1, require-ocr=1, ocr-mode=on）。")
    analysis_md.append("")

    out_analysis = paths.reports_dir / "ablation_conclusions.md"
    out_analysis.write_text("\n".join(analysis_md).rstrip() + "\n", encoding="utf-8")

    return out_csv, out_md
