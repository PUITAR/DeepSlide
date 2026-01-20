import streamlit as st
import os
from core import _init_state, ROOT
from audio import ensure_asr_model_ready
from sidebar import render_sidebar_logs
from requirements import render_page_requirements
from logic_chain import render_page_logic_chain
from editor import render_page_ppt_editor
from preview import render_page_ppt_preview

def main():
    st.set_page_config(page_title="DeepSlide", layout="wide")
    _init_state()
    ensure_asr_model_ready()
    render_sidebar_logs()
    
    tmp_base = os.path.join(ROOT, "tmp_uploads")
    os.makedirs(tmp_base, exist_ok=True)
    
    if "generated_files" in st.session_state:
        # Determine which page to render based on phase
        current_phase = st.session_state.get("workflow_phase", "EDITING")
        if current_phase == "PREVIEW":
             render_page_ppt_preview(tmp_base)
        else:
             render_page_ppt_editor(tmp_base)
    elif st.session_state.app_state == "CONFIRMATION":
        render_page_logic_chain(tmp_base)
    else:
        render_page_requirements(tmp_base)

if __name__ == "__main__":
    main()
