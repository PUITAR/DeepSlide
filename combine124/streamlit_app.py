from __future__ import annotations

import html
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

# Make `combine124` importable regardless of Streamlit working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# NOTE: Do not rename these imports / call sites (external interfaces).
from combine124.backend import Combine124Backend
from combine124.chatter import PPTRequirementsCollector


# -------------------------
# UI helpers
# -------------------------

def _inject_css() -> None:
    st.markdown(
        """
<style>
:root{
  --bg: #0b1020;
  --panel: rgba(255,255,255,0.06);
  --panel2: rgba(255,255,255,0.08);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.70);
  --muted2: rgba(255,255,255,0.58);
  --line: rgba(255,255,255,0.12);
  --accent: #6ea8fe;
  --accent2: #b197fc;
  --good: #63e6be;
  --warn: #ffd43b;
  --bad: #ff6b6b;
}

section.main > div { padding-top: 1.0rem; }
.block-container { max-width: 1200px; }

h1, h2, h3, h4, h5, h6, p, li, div, span { color: var(--text); }
.small-muted { color: var(--muted2); font-size: 0.92rem; }
.hr { border-top: 1px solid var(--line); margin: 0.75rem 0 1rem; }

.kpi-card{
  border: 1px solid var(--line);
  background: linear-gradient(135deg, rgba(110,168,254,0.08), rgba(177,151,252,0.06));
  padding: 14px 14px;
  border-radius: 14px;
}
.kpi-title{ font-size: 0.9rem; color: var(--muted); }
.kpi-value{ font-size: 1.2rem; font-weight: 700; margin-top: 4px; }

.panel{
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 16px;
  padding: 14px 14px;
}

.panel-header{
  display:flex; align-items:center; justify-content:space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.badge{
  display:inline-flex; align-items:center; gap:6px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.05);
  font-size: 0.82rem;
  color: var(--muted);
  white-space: nowrap;
}

.badge.accent{
  background: rgba(110,168,254,0.12);
  border-color: rgba(110,168,254,0.25);
  color: rgba(110,168,254,0.95);
}
.badge.good{
  background: rgba(99,230,190,0.10);
  border-color: rgba(99,230,190,0.22);
  color: rgba(99,230,190,0.95);
}
.badge.warn{
  background: rgba(255,212,59,0.10);
  border-color: rgba(255,212,59,0.22);
  color: rgba(255,212,59,0.95);
}

.stChatMessage{ border-radius: 14px; }
[data-testid="stChatMessage"]{
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.04);
  border-radius: 14px;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p { color: var(--text); }

/* Streamlit widget spacing tweaks */
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

/* Link button style */
a.small-link { color: var(--accent); text-decoration: none; }
a.small-link:hover { text-decoration: underline; }

</style>
        """,
        unsafe_allow_html=True,
    )


def _escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def _short(s: str, n: int = 220) -> str:
    s = s or ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def _try_parse_duration_minutes(duration: Any) -> Optional[float]:
    """Best-effort parse for duration. Do NOT enforce any schema changes here."""
    if duration is None:
        return None
    # numeric
    if isinstance(duration, (int, float)):
        return float(duration)
    # common string patterns: "10", "10min", "10 minutes", "600s"
    if isinstance(duration, str):
        t = duration.strip().lower()
        # seconds
        if t.endswith("s"):
            try:
                sec = float(t[:-1].strip())
                return sec / 60.0
            except Exception:
                return None
        # minutes
        for suf in ["min", "mins", "minute", "minutes", "m"]:
            if t.endswith(suf):
                try:
                    val = float(t[: -len(suf)].strip())
                    return val
                except Exception:
                    return None
        # pure number string
        try:
            return float(t)
        except Exception:
            return None
    return None


def _save_uploaded_tex(upload) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tex")
    content = upload.getvalue().decode("utf-8", errors="ignore")
    tmp.write(content.encode("utf-8"))
    tmp.flush()
    return tmp.name


# -------------------------
# Interactive chain renderer (one chain per row)
# -------------------------

def _edge_reason_map(chain) -> Dict[Tuple[int, int], str]:
    m: Dict[Tuple[int, int], str] = {}
    for e in chain.edges:
        try:
            m[(int(e.from_index), int(e.to_index))] = (e.reason or "")
        except Exception:
            continue
    return m


def _render_chain_row_html(
    template_id: str,
    chain,
    is_hook: bool = False,
    highlight: bool = False,
    max_snippet: int = 180,
) -> str:
    """Render a single chain as a horizontal row of cards with hover/click details.
    Uses only HTML/CSS/JS (Streamlit components), no external dependencies.
    """
    nodes = list(chain.nodes)
    edge_map = _edge_reason_map(chain)

    # Build cards and simple step arrows between consecutive indices (best effort).
    cards: List[str] = []
    for i, node in enumerate(nodes):
        ratio = getattr(node, "duration_ratio", None)
        ratio_txt = ""
        if isinstance(ratio, (int, float)):
            ratio_txt = f"{ratio:.2f}"
        role = _escape(str(getattr(node, "role", "")))
        prov = _escape(str(getattr(node, "provenance", "")))
        text = str(getattr(node, "text", ""))

        # Badge colors by provenance
        prov_class = "prov-paper" if prov == "paper" else ("prov-bridge" if prov == "bridge" else "prov-rhet")
        hook_star = "★" if (is_hook and i == 0) else ""

        evidence = getattr(node, "evidence", None) or []
        evidence_html = ""
        if evidence:
            items = "".join(f"<li>{_escape(str(x))}</li>" for x in evidence[:8])
            more = ""
            if len(evidence) > 8:
                more = f'<div class="small-muted" style="margin-top:6px;">+{len(evidence)-8} more…</div>'
            evidence_html = f"""
            <div class="node-subtitle">Evidence</div>
            <ul class="evidence">{items}</ul>
            {more}
            """

        cards.append(
            f"""
            <div class="node-card" tabindex="0" role="button">
              <div class="node-top">
                <div class="node-left">
                  <span class="pill role">{_escape(f"[{node.index}] {role}")}</span>
                  <span class="pill {prov_class}">{prov}</span>
                </div>
                <div class="node-right">
                  <span class="pill ratio">{_escape(ratio_txt) if ratio_txt else "-"}</span>
                </div>
              </div>

              <div class="node-text" title="{_escape(text)}">{_escape(_short(text, max_snippet))}</div>

              <details class="node-details">
                <summary>Details</summary>
                <div class="details-body">
                  <div class="node-subtitle">Full text</div>
                  <div class="fulltext">{_escape(text)}</div>
                  {evidence_html}
                </div>
              </details>
            </div>
            """
        )

        # Add arrow between i and i+1 (if any)
        if i < len(nodes) - 1:
            fidx = int(getattr(node, "index", i))
            tidx = int(getattr(nodes[i + 1], "index", i + 1))
            reason = edge_map.get((fidx, tidx), "")
            cards.append(
                f"""
                <div class="arrow" title="{_escape(reason) if reason else ''}">
                  <div class="arrow-line"></div>
                  <div class="arrow-tip">➜</div>
                  {"<div class='arrow-reason'>" + _escape(_short(reason, 60)) + "</div>" if reason else ""}
                </div>
                """
            )

    hook_badge = '<span class="header-badge hook">Hook</span>' if is_hook else ""
    focus_badge = '<span class="header-badge focus">Selected</span>' if highlight else ""
    template_title = _escape(template_id)

    # One chain per row; horizontally scrollable.
    return f"""
<div class="chain-row {'highlight' if highlight else ''}">
  <div class="chain-header">
    <div class="chain-title">
      <span class="tid">{template_title}</span>
      {hook_badge}
      {focus_badge}
    </div>
    <div class="chain-meta">
      <span class="meta-pill">Nodes: {len(nodes)}</span>
      <span class="meta-pill">Edges: {len(getattr(chain, 'edges', []) or [])}</span>
    </div>
  </div>

  <div class="chain-strip">
    {''.join(cards)}
  </div>
</div>
"""


def _render_all_chains_html(options, selected_tid: str) -> str:
    # Build a minimal CSS block local to the component.
    # This ensures it looks consistent even if Streamlit theme changes.
    style = """
<style>
.wrap{
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
  color: rgba(255,255,255,0.92);
}
.chain-row{
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  border-radius: 16px;
  padding: 12px 12px;
  margin: 12px 0;
  position: relative;
  overflow: hidden;
}
.chain-row.highlight{
  border-color: rgba(110,168,254,0.36);
  box-shadow: 0 0 0 1px rgba(110,168,254,0.20) inset, 0 16px 36px rgba(0,0,0,0.25);
}
.chain-header{
  display:flex; align-items: flex-end; justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.chain-title{
  display:flex; align-items:center; gap:8px;
  font-weight: 800;
  letter-spacing: 0.2px;
}
.chain-title .tid{
  font-size: 1.02rem;
}
.header-badge{
  display:inline-flex; align-items:center; justify-content:center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  border: 1px solid rgba(255,255,255,0.16);
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.75);
}
.header-badge.hook{
  border-color: rgba(255,212,59,0.25);
  background: rgba(255,212,59,0.10);
  color: rgba(255,212,59,0.95);
}
.header-badge.focus{
  border-color: rgba(110,168,254,0.30);
  background: rgba(110,168,254,0.12);
  color: rgba(110,168,254,0.95);
}
.chain-meta{
  display:flex; gap:8px; flex-wrap: wrap;
}
.meta-pill{
  display:inline-flex; align-items:center; justify-content:center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(0,0,0,0.10);
  color: rgba(255,255,255,0.72);
}

.chain-strip{
  display:flex;
  align-items: stretch;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}
.chain-strip::-webkit-scrollbar{ height: 10px; }
.chain-strip::-webkit-scrollbar-thumb{
  background: rgba(255,255,255,0.14);
  border-radius: 999px;
}
.node-card{
  min-width: 280px;
  max-width: 280px;
  border: 1px solid rgba(255,255,255,0.12);
  background: linear-gradient(135deg, rgba(110,168,254,0.08), rgba(177,151,252,0.06));
  border-radius: 16px;
  padding: 12px 12px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.20);
  outline: none;
}
.node-card:focus{
  border-color: rgba(110,168,254,0.34);
  box-shadow: 0 0 0 2px rgba(110,168,254,0.18), 0 10px 24px rgba(0,0,0,0.20);
}
.node-top{
  display:flex; justify-content: space-between; align-items: flex-start; gap: 8px;
  margin-bottom: 8px;
}
.node-left{ display:flex; gap:6px; flex-wrap: wrap; }
.node-right{ display:flex; gap:6px; flex-wrap: wrap; }

.pill{
  display:inline-flex; align-items:center;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(0,0,0,0.10);
  font-size: 0.78rem;
  color: rgba(255,255,255,0.75);
  white-space: nowrap;
}
.pill.role{
  background: rgba(255,255,255,0.06);
}
.pill.ratio{
  border-color: rgba(99,230,190,0.22);
  background: rgba(99,230,190,0.10);
  color: rgba(99,230,190,0.95);
}
.pill.prov-paper{
  border-color: rgba(255,212,59,0.22);
  background: rgba(255,212,59,0.10);
  color: rgba(255,212,59,0.95);
}
.pill.prov-bridge{
  border-color: rgba(110,168,254,0.25);
  background: rgba(110,168,254,0.12);
  color: rgba(110,168,254,0.95);
}
.pill.prov-rhet{
  border-color: rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.78);
}

.node-text{
  font-size: 0.88rem;
  line-height: 1.35;
  color: rgba(255,255,255,0.86);
  min-height: 4.2em;
}

.node-details{
  margin-top: 10px;
  border-top: 1px dashed rgba(255,255,255,0.14);
  padding-top: 8px;
}
.node-details > summary{
  cursor:pointer;
  font-size: 0.82rem;
  color: rgba(255,255,255,0.74);
  user-select:none;
}
.details-body{ margin-top: 8px; }
.node-subtitle{
  font-size: 0.78rem;
  color: rgba(255,255,255,0.62);
  margin: 6px 0 4px;
}
.fulltext{
  font-size: 0.84rem;
  color: rgba(255,255,255,0.82);
  white-space: pre-wrap;
  background: rgba(0,0,0,0.14);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 8px 8px;
}
ul.evidence{
  margin: 6px 0 0 18px;
  padding: 0;
  color: rgba(255,255,255,0.82);
  font-size: 0.84rem;
}
.arrow{
  display:flex;
  flex-direction: column;
  align-items:center;
  justify-content:center;
  min-width: 86px;
  padding: 0 4px;
  opacity: 0.85;
}
.arrow-line{
  width: 100%;
  height: 1px;
  background: rgba(255,255,255,0.25);
  margin-bottom: 3px;
}
.arrow-tip{
  font-size: 1.1rem;
  color: rgba(255,255,255,0.78);
  margin-bottom: 4px;
}
.arrow-reason{
  font-size: 0.72rem;
  color: rgba(255,255,255,0.55);
  text-align: center;
  line-height: 1.15;
}
</style>
    """

    rows_html: List[str] = []
    for tid in options.chosen_template_ids:
        ch = options.chains.get(tid)
        if not ch:
            continue
        rows_html.append(
            _render_chain_row_html(
                template_id=tid,
                chain=ch,
                is_hook=(tid == options.hook_template_id),
                highlight=(tid == selected_tid),
            )
        )

    html_doc = f"""
<div class="wrap">
  {style}
  {''.join(rows_html) if rows_html else '<div style="opacity:0.7;">No chains.</div>'}
</div>
    """
    return html_doc


# -------------------------
# App state
# -------------------------

def _ensure_state() -> None:
    if "collector" not in st.session_state:
        st.session_state.collector = PPTRequirementsCollector()
    if "messages" not in st.session_state:
        st.session_state.messages = []  # list[{role, content}]
    if "requirements" not in st.session_state:
        st.session_state.requirements = None
    if "tex_text" not in st.session_state:
        st.session_state.tex_text = ""
    if "combined" not in st.session_state:
        st.session_state.combined = None


# -------------------------
# Page
# -------------------------

st.set_page_config(page_title="Combine124", layout="wide")

_inject_css()
_ensure_state()

st.markdown(
    """
<div class="panel">
  <div class="panel-header">
    <div>
      <div style="font-size:1.25rem; font-weight:900; letter-spacing:0.2px;">Combine124</div>
      <div class="small-muted">对话收集需求 → 上传 .tex → 生成逻辑链（可交互视图，一条链一行）</div>
    </div>
    <div style="display:flex; gap:8px; flex-wrap:wrap;">
      <span class="badge accent">Streamlit</span>
      <span class="badge">Only combine124/* at runtime</span>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# Sidebar: quick actions
with st.sidebar:
    st.markdown("### 控制台")
    st.caption("这里放最常用的动作：生成需求 / 上传 tex / 运行 pipeline / 下载结果。")

    # Requirements
    if st.button("生成/刷新 requirements JSON", type="primary"):
        st.session_state.requirements = st.session_state.collector.get_requirements()

    req = st.session_state.requirements
    if req:
        st.success("requirements 已就绪")
        st.json(req)
        req_bytes = json.dumps(req, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "下载 requirements.json",
            data=req_bytes,
            file_name="requirements.json",
            mime="application/json",
        )
    else:
        st.info("先在主页面对话，然后点击上面的按钮生成 requirements。")

    st.markdown("---")
    # Upload tex
    tex_file = st.file_uploader("上传文章 .tex（或合并后的 main.tex）", type=["tex"])
    if tex_file is not None:
        tex_text = tex_file.getvalue().decode("utf-8", errors="ignore")
        st.session_state.tex_text = tex_text
        st.success(f"已上传 tex：{len(tex_text):,} 字符")

        with st.expander("预览（前 2,000 字符）", expanded=False):
            st.code(tex_text[:2000])

    # Run pipeline
    st.markdown("---")
    can_run = bool(st.session_state.requirements) and bool(st.session_state.tex_text.strip())
    run = st.button("Generate Logic Chains", disabled=not can_run)

    if run:
        backend = Combine124Backend()
        requirements: Dict[str, Any] = st.session_state.requirements

        with st.spinner("运行端到端 pipeline..."):
            combined = backend.run_pipeline(raw_text=st.session_state.tex_text, requirements=requirements)

        st.session_state.combined = combined
        st.success("已生成逻辑链 ✅")

    st.markdown("---")
    st.caption("提示：如果你只想看某条链的节点时间分配，重点关注每个节点的 duration_ratio。")

# Main content: tabs
tabs = st.tabs(["① 对话收集需求", "② 逻辑链结果", "③ 导出与明细"])

# -------------------------
# Tab 1) Chatter
# -------------------------
with tabs[0]:
    st.markdown("## ① 多轮对话（chatter）")
    st.caption("每次你输入一句，agent 会追问/补全需求。等信息足够后，再点侧边栏按钮生成 requirements JSON。")

    # Lightweight KPIs
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown('<div class="kpi-card"><div class="kpi-title">Chat turns</div><div class="kpi-value">{}</div></div>'.format(len(st.session_state.messages)), unsafe_allow_html=True)
    with k2:
        has_req = "Yes" if st.session_state.requirements else "No"
        st.markdown('<div class="kpi-card"><div class="kpi-title">Requirements ready</div><div class="kpi-value">{}</div></div>'.format(has_req), unsafe_allow_html=True)
    with k3:
        tex_len = len(st.session_state.tex_text) if st.session_state.tex_text else 0
        st.markdown('<div class="kpi-card"><div class="kpi-title">Tex chars</div><div class="kpi-value">{:,}</div></div>'.format(tex_len), unsafe_allow_html=True)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    # Chat UI
    chat_panel = st.container()
    with chat_panel:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.write(m["content"])

        user_msg = st.chat_input("输入你的 PPT 需求（比如听众是谁、时长、重点、风格…）")
        if user_msg:
            st.session_state.messages.append({"role": "user", "content": user_msg})
            with st.chat_message("user"):
                st.write(user_msg)

            with st.spinner("LLM 正在回复..."):
                resp = st.session_state.collector.process_user_input(user_msg)

            st.session_state.messages.append({"role": "assistant", "content": resp})
            with st.chat_message("assistant"):
                st.write(resp)

    if not st.session_state.messages:
        st.info("从一句话开始，比如：听众是谁、总时长多少分钟、你想强调哪些部分。")

# -------------------------
# Tab 2) Results
# -------------------------
with tabs[1]:
    st.markdown("## ② 逻辑链结果（更美观 + 可交互，一条链一行）")

    combined = st.session_state.combined
    if not combined:
        st.info("先在侧边栏完成 requirements + 上传 tex，然后点击 **Generate Logic Chains**。")
    else:
        options = combined.logic_options

        # Template picker
        st.markdown("### 模板选择")
        # A clean rows display (no interface renames)
        rows = []
        for tid in options.chosen_template_ids:
            rows.append(
                {
                    "template_id": tid,
                    "is_hook": tid == options.hook_template_id,
                    "reason": options.reasons.get(tid, ""),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        default_idx = (
            options.chosen_template_ids.index(options.hook_template_id)
            if options.hook_template_id in options.chosen_template_ids
            else 0
        )
        selected = st.selectbox("选择一个模板（高亮显示该链）", options.chosen_template_ids, index=default_idx)

        # Pretty interactive rows view (all chains, one per row)
        st.markdown("### 逻辑链路（交互卡片视图）")
        st.caption("说明：横向可滚动；节点卡片可展开 Details；箭头 hover 可看连接理由（若有）。")

        html_doc = _render_all_chains_html(options, selected_tid=selected)
        # Height heuristic: keep enough room for expanded details.
        components.html(html_doc, height=560, scrolling=True)

        # Focused details below
        chain = options.chains.get(selected)
        if chain:
            st.markdown("### 选中模板的链内细节")
            total_minutes = _try_parse_duration_minutes((st.session_state.requirements or {}).get("duration"))
            if total_minutes:
                st.caption(f"已解析总时长约 **{total_minutes:.1f} min**（来自 requirements.duration）。下面会同时展示每个节点的建议分钟数。")
            else:
                st.caption("未能解析 requirements.duration 为分钟数（可能是非标准字符串）。仍展示 duration_ratio。")

            for n in chain.nodes:
                ratio = getattr(n, "duration_ratio", None)
                mins = None
                if total_minutes and isinstance(ratio, (int, float)):
                    mins = total_minutes * float(ratio)
                title_bits = [f"[{n.index}] {n.role}", f"prov={n.provenance}"]
                if isinstance(ratio, (int, float)):
                    title_bits.append(f"ratio={ratio:.2f}")
                if mins is not None:
                    title_bits.append(f"~{mins:.1f} min")
                title = "  •  ".join(title_bits)

                with st.expander(title, expanded=False):
                    st.write(n.text)
                    if n.evidence:
                        st.markdown("**Evidence**")
                        for ev in n.evidence:
                            st.markdown(f"- {ev}")

            with st.expander("Edges（连接理由）", expanded=False):
                for e in chain.edges:
                    st.markdown(f"- `{e.from_index} → {e.to_index}`：{e.reason}")

# -------------------------
# Tab 3) Export / Raw
# -------------------------
with tabs[2]:
    st.markdown("## ③ 导出与明细")

    combined = st.session_state.combined
    if not combined:
        st.info("生成逻辑链后，这里会提供导出按钮与原始 JSON。")
    else:
        options = combined.logic_options
        out_dict = {
            "requirements": combined.ppt_requirements,
            "chosen_template_ids": options.chosen_template_ids,
            "hook_template_id": options.hook_template_id,
            "reasons": options.reasons,
            "chains": {
                tid: {
                    "nodes": [
                        {
                            "index": n.index,
                            "role": n.role,
                            "provenance": n.provenance,
                            "text": n.text,
                            "evidence": n.evidence,
                            "duration_ratio": n.duration_ratio,
                        }
                        for n in ch.nodes
                    ],
                    "edges": [
                        {"from_index": e.from_index, "to_index": e.to_index, "reason": e.reason}
                        for e in ch.edges
                    ],
                }
                for tid, ch in options.chains.items()
            },
        }

        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.download_button(
                "下载输出 JSON",
                data=json.dumps(out_dict, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="combine124_output.json",
                mime="application/json",
            )
        with col_b:
            st.download_button(
                "下载 requirements.json（当前）",
                data=json.dumps(st.session_state.requirements or {}, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="requirements.json",
                mime="application/json",
            )

        st.markdown("### 原始输出预览")
        st.json(out_dict)
