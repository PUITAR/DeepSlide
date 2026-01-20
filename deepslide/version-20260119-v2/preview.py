import streamlit as st
import os
from core import _components_html
from visuals import inject_reveal_slide_control
from html_export import generate_and_save_html_export
from ppt_agent import _update_pdf_preview
from ui import render_header

def render_preview_ui():
    if "preview_state" not in st.session_state: return
    state = st.session_state.preview_state
    pages = state.get("pdf_pages", [])
    speeches = state.get("speech_segments", [])
    
    if not pages: return

    # st.subheader("Presentation Preview")
    col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 1, 1, 17])
    if "current_page" not in state: state["current_page"] = 0
    with col_nav1:
        if st.button("◀", key="prev_slide"):
            state["current_page"] = max(0, state["current_page"] - 1)
            st.rerun()
    with col_nav3:
        if st.button("▶", key="next_slide"):
            state["current_page"] = min(len(pages) - 1, state["current_page"] + 1)
            st.rerun()
    with col_nav2:
        st.markdown(
            f"<div style='text-align: left'>{state['current_page'] + 1} / {len(pages)}</div>", 
            unsafe_allow_html=True)
    
    col_disp1, col_disp2 = st.columns([2, 1])
    with col_disp1:
        st.image(pages[state["current_page"]]) # use_column_width deprecated
    with col_disp2:
        speech_idx = state["current_page"]
        if 0 <= speech_idx < len(speeches):
            display_text = speeches[speech_idx].replace("<add>", "").strip()
            
            # Use expander for speech preview, similar to editing phase
            with st.expander("Speech Script", expanded=True):
                st.write(display_text)
                
                # Audio player inside the speech column for better context
                if "generated_files" in st.session_state:
                    audio_dir = st.session_state.generated_files.get("audio_dir")
                    if audio_dir:
                        wav_path = os.path.join(audio_dir, f"{state['current_page']+1}.wav")
                        if os.path.exists(wav_path):
                             st.audio(wav_path, format="audio/wav")
        else:
            st.info("No speech script available.")

def render_page_ppt_preview(tmp_base):
    render_header(
        "Preview",
        "Play the deck, export artifacts, and validate results.",
        active_step=4,
    )
    
    if "tts_error" in st.session_state:
        st.error(st.session_state.tts_error)
        del st.session_state["tts_error"]
        
    files = st.session_state.generated_files

    render_preview_ui()

    with st.expander("HTML Export", expanded=False):
        # Allow user to tune max regions
        c_cfg1, c_cfg2 = st.columns([1, 1])
        with c_cfg1:
             max_regions = st.number_input("Max Zoom Regions", min_value=1, max_value=8, value=5, key="preview_max_regions_slider")

        # Hardcoded defaults as requested by user
        st.session_state.html_use_llm_conversion = True
        st.session_state.html_focus_all_slides = False
        st.session_state.html_focus_prefer_vlm = True

        st.session_state.html_focus_zoom_cfg = {
            "enabled": True,
            "max_regions": int(max_regions),
            "interval_ms": 2000,
            "scale": 1.1,
            "cache": True,
        }

        if st.button("Generate HTML", type="primary", key="preview_generate_html"):
            with st.spinner("Generating HTML..."):
                pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
                if not pdf_pages and os.path.exists(files.get("pdf", "")):
                    _update_pdf_preview()
                    pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
                html = generate_and_save_html_export(files, pdf_pages)
                if html:
                    st.success("HTML generated")
                else:
                    st.error("HTML generation failed")

        if "html_slides_content" in st.session_state:
            curr = st.session_state.preview_state.get("current_page", 0)
            synced_html = inject_reveal_slide_control(st.session_state.html_slides_content, curr)
            _components_html(synced_html, height=600, scrolling=True, key="html_slide_preview_in_preview")
            st.download_button("Download HTML", synced_html, "presentation.html", "text/html")
    
    c_d1, c_d2, c_d3, c_d4 = st.columns(4)
    with c_d1:
        with open(files["pdf"], "rb") as f: st.download_button("Download PDF", f.read(), "presentation.pdf")
    with c_d2:
        if "speech" in files and os.path.exists(files["speech"]):
            with open(files["speech"], "r", encoding="utf-8") as f:
                st.download_button("Download Speech Script", f.read(), "speech.txt")
    with c_d3:
        if "html" in files and os.path.exists(files["html"]):
            with open(files["html"], "r", encoding="utf-8") as f:
                st.download_button("Download HTML", f.read(), "presentation.html", "text/html")
        if "slides_zip" in files and os.path.exists(files["slides_zip"]):
            with open(files["slides_zip"], "rb") as f:
                st.download_button("Download Slides (ZIP)", f.read(), "slides_html.zip", "application/zip")
    with c_d4:
        if st.button("🔙 Back to Editing"):
            st.session_state.workflow_phase = "EDITING"
            st.rerun()
