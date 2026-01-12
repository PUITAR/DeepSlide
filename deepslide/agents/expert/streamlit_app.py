from __future__ import annotations

import json
import tempfile
from typing import Any, Dict, Optional

import streamlit as st

from deepslide.agents.combine124.backend import Combine124Backend, CombinedOutput

# Quick-start sample requirements (you can upload your own JSON to override).
_SAMPLE_REQUIREMENTS = {
    "paper_info": {
        "file_name": "demo.tex",
        "project_dir": "",
        "main_tex": "",
        "merged_main": "",
        "abstract": "A short abstract for demo.",
    },
    "conversation_requirements": {
        "audience": "Technical audience with ML background",
        "duration": "15 minutes",
        "focus_sections": ["method", "results"],
        "style": "Concise, evidence-first",
        "special_notes": "Avoid heavy math; highlight contributions",
    },
    "conversation_history": [],
}

st.set_page_config(page_title="DeepSlide Combine 1+2+4", layout="wide")
st.title("DeepSlide Combine 1+2+4 (text-based Streamlit demo)")
st.caption("Upload a merged .tex/plain-text file and PPT requirements JSON, then generate 4 narrative logic chains.")


def _load_requirements(upload, fallback_text: str) -> Dict[str, Any]:
    if upload is not None:
        try:
            return json.load(upload)
        except Exception as exc:  # pragma: no cover
            st.error(f"Failed to parse uploaded requirements JSON: {exc}")
            raise
    try:
        return json.loads(fallback_text)
    except Exception as exc:
        st.error(f"Fallback requirements JSON is invalid: {exc}")
        raise


def _save_uploaded_text(upload) -> str:
    """Persist the uploaded text to a temp file for backend consumption."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    content = upload.getvalue().decode("utf-8", errors="ignore")
    tmp.write(content.encode("utf-8"))
    tmp.flush()
    return tmp.name


def _build_dot(chain) -> str:
    """Render a simple graphviz DOT string for the logic chain."""
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        "  node [shape=box, style=\"rounded,filled\", fillcolor=\"#f8f9fa\", color=\"#555\"];",
    ]

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")

    for node in chain.nodes:
        ratio = f" t={node.duration_ratio:.2f}" if getattr(node, "duration_ratio", None) is not None else ""
        snippet = node.text[:140] + ("…" if len(node.text) > 140 else "")
        label = f"[{node.index}] {node.role} | {node.provenance}{ratio}\\n{snippet}"
        lines.append(f"  n{node.index} [label=\"{esc(label)}\"];\n")

    for edge in chain.edges:
        reason = esc(edge.reason or "")
        lines.append(f"  n{edge.from_index} -> n{edge.to_index} [label=\"{reason}\"];\n")

    lines.append("}")
    return "\n".join(lines)


with st.sidebar:
    st.subheader("Inputs")
    tex_file = st.file_uploader("Upload merged .tex / plain text", type=["tex", "txt", "md", "text"])
    req_file = st.file_uploader("Upload ppt_requirements.json", type=["json"], accept_multiple_files=False)
    req_text = st.text_area(
        "Or paste requirements JSON",
        value=json.dumps(_SAMPLE_REQUIREMENTS, ensure_ascii=False, indent=2),
        height=220,
    )
    run_clicked = st.button("Run pipeline", type="primary", disabled=tex_file is None)
    st.markdown("""
    **Notes**
    - Model keys are read from `deepslide/config/env/.env` (DEFAULT_MODEL_API_KEY, etc.).
    - Text is read as UTF-8; provide the merged main `.tex` or any plain-text source.
    - Requirements schema matches `PPTRequirementsCollector.get_requirements()`.
    """)

status_placeholder = st.empty()

if run_clicked:
    if tex_file is None:
        st.warning("Please upload a .tex/plain-text file.")
        st.stop()

    try:
        requirements = _load_requirements(req_file, req_text)
    except Exception:
        st.stop()

    tmp_text_path = _save_uploaded_text(tex_file)

    with st.spinner("Running Combine124 backend..."):
        backend = Combine124Backend()
        combined: Optional[CombinedOutput] = None
        try:
            combined = backend.generate_logic_from_text(tmp_text_path, requirements)
        except Exception as exc:  # pragma: no cover
            status_placeholder.error(f"Pipeline failed: {exc}")
            st.stop()

    status_placeholder.success("Pipeline completed.")

    options = combined.logic_options
    st.subheader("Template selection")
    st.write("Chosen IDs:", options.chosen_template_ids)
    st.write("Hook:", options.hook_template_id)
    st.write("Reasons:")
    for tid, reason in options.reasons.items():
        st.write(f"- {tid}: {reason}")

    selected_template = st.selectbox(
        "Select a template to visualize",
        options.chosen_template_ids,
        index=options.chosen_template_ids.index(options.hook_template_id)
        if options.hook_template_id in options.chosen_template_ids
        else 0,
    )

    chain = options.chains.get(selected_template)
    if not chain:
        st.error("Selected template has no chain output.")
        st.stop()

    st.markdown("**Logic chain graph**")
    dot_src = _build_dot(chain)
    st.graphviz_chart(dot_src, use_container_width=True)

    st.markdown("**Nodes**")
    node_rows = []
    for n in chain.nodes:
        node_rows.append(
            {
                "index": n.index,
                "role": n.role,
                "provenance": n.provenance,
                "duration_ratio": getattr(n, "duration_ratio", None),
                "text": n.text,
                "evidence": "; ".join(n.evidence or []),
            }
        )
    st.dataframe(node_rows, use_container_width=True, hide_index=True)

    st.markdown("**Edges**")
    edge_rows = []
    for e in chain.edges:
        edge_rows.append(
            {
                "from": e.from_index,
                "to": e.to_index,
                "reason": e.reason,
            }
        )
    st.dataframe(edge_rows, use_container_width=True, hide_index=True)

else:
    st.info("Upload a merged .tex/plain-text file and requirements JSON, then click Run pipeline.")
