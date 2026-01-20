import streamlit as st
from core import TOOL_LOGS

def render_sidebar_logs():
    with st.sidebar:
        with st.expander("🛠 Tool Calls & Logs", expanded=False):
            st.text("\n".join(TOOL_LOGS[-20:]))
            if st.button("Clear Logs"):
                TOOL_LOGS.clear()
                st.rerun()
