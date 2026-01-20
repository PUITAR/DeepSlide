import streamlit as st
from core import TOOL_LOGS
from ui import render_sidebar_pipeline

def render_sidebar_logs():
    with st.sidebar:
        phase = 1
        if "generated_files" in st.session_state:
            phase = 4 if st.session_state.get("workflow_phase") == "PREVIEW" else 3
        else:
            phase = 2 if st.session_state.get("app_state") == "CONFIRMATION" else 1

        render_sidebar_pipeline(phase)

        with st.expander("🛠 Tool Calls & Logs", expanded=False):
            st.text("\n".join(TOOL_LOGS[-20:]))
            if st.button("Clear Logs"):
                TOOL_LOGS.clear()
                st.rerun()
