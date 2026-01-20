import streamlit as st
import os
import shutil
import uuid
from ui import render_header
from project_analyzer import (
    save_uploaded_file, extract_archive, find_main_tex,
    merge_project_to_main, extract_abstract_from_dir
)
from divider import Divider
from core import _wrap_tools, _log
from audio import transcribe_audio

def render_page_requirements(tmp_base):
    render_header(
        "Requirements",
        "Upload your paper project and describe audience, duration, focus, and style.",
        active_step=1,
    )
    
    if not st.session_state.uploaded:
        # st.write("Please upload your paper project archive to begin.")
        uploaded_file = st.file_uploader("Upload Paper Project Archive", type=["zip", "tar", "gz", "bz2", "xz"])
        if uploaded_file:
            try:
                # Use cached processing
                with st.spinner("Analyzing project structure..."):
                    # 1. Save file
                    os.makedirs(tmp_base, exist_ok=True)
                    archive_path = save_uploaded_file(uploaded_file, tmp_base)
                    
                    # 2. Extract
                    extract_dir = os.path.join(tmp_base, os.path.splitext(os.path.basename(archive_path))[0])
                    st.session_state.extract_dir = extract_dir
                    extract_archive(archive_path, extract_dir)
                    
                    # 3. Find main and merge
                    main_tex = find_main_tex(extract_dir)
                    merged_path = ""
                    if main_tex:
                        merged_path = merge_project_to_main(os.path.dirname(main_tex), main_tex, "merged_main.tex")
                    
                    # 4. Divide
                    divider = Divider()
                    target_tex = merged_path if merged_path and os.path.exists(merged_path) else (main_tex or "")
                    nodes = divider.divide(target_tex) if target_tex else []
                    
                    # 5. Abstract
                    abstract_text = extract_abstract_from_dir(extract_dir) or ""

                    st.session_state.content_tree_nodes = nodes
                    
                    st.session_state.collector.set_paper_file(uploaded_file.name)
                    st.session_state.collector.set_paper_project(extract_dir, main_tex, merged_path)
                    st.session_state.collector.set_paper_abstract(abstract_text)
                    st.session_state.collector.prime_context()
                    
                    from content_tree_builder import make_tree_tools
                    tools = make_tree_tools(nodes)
                    st.session_state.collector.camel_client.set_tools(_wrap_tools(tools))
                    
                    if abstract_text:
                        st.session_state.collector.conversation_history.append(
                            {"role": "assistant", "content": f"Abstract detected:\n{abstract_text}"})
                    st.session_state.collector.conversation_history.append(
                        {"role": "assistant", "content": "To get started, please tell me the following basic information:\n- Who is the audience?\n- Presentation duration?\n- Which chapters do you want to highlight?\n- Style preference?"})
                    
                    st.session_state.uploaded = True
                    st.session_state.app_state = "CONVERSATION"
                    st.rerun()
            except Exception as e:
                st.error(f"Upload Error: {e}")
                import traceback
                traceback.print_exc()
    else:
        st.info(f"Project: {st.session_state.collector.paper_file_name}")
        
        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state.collector.conversation_history:
                with st.chat_message(msg.get("role", "assistant")):
                    st.write(msg.get("content", ""))

        # Bottom Input
        try:
            bottom_box = st.bottom_container()
        except AttributeError:
            bottom_box = st.container()
        
        # Inject custom CSS for this page's bottom section
        st.markdown("""
            <style>
            /* Compact Audio Input - Full Width */
            div[data-testid="stAudioInput"] {
                padding: 0 !important;
                height: 40px !important;
                min-height: 40px !important;
                width: 100% !important;
                display: flex;
                align-items: center;
                border: none !important;
                background: transparent !important;
            }
            div[data-testid="stAudioInput"] > div {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
                width: 100% !important;
            }
            /* Remove internal spacing in the audio widget */
            div[data-testid="stAudioInput"] button {
                margin: 0 !important;
            }
            
            /* Adjust button alignment in the row */
            div[data-testid="stColumn"] button {
                margin-top: 0px !important;
            }
            
            /* Tech-style Light Blue Gradient Send Button */
            div[data-testid="stForm"] button,
            div[data-testid="stForm"] button[kind="primary"],
            div[data-testid="stForm"] button:active,
            div[data-testid="stForm"] button:focus,
            div[data-testid="stForm"] button:hover {
                background: linear-gradient(135deg, #3B82F6 0%, #06B6D4 100%) !important;
                border: none !important;
                color: white !important;
                font-weight: 800 !important;
                box-shadow: 0 0 20px rgba(59, 130, 246, 0.4) !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                letter-spacing: 0.5px !important;
                outline: none !important;
            }
            div[data-testid="stForm"] button:hover {
                box-shadow: 0 0 30px rgba(6, 182, 212, 0.6) !important;
                transform: translateY(-2px) !important;
                background: linear-gradient(135deg, #2563EB 0%, #0891B2 100%) !important;
            }

            /* Slimmer Text Area to match button height */
            div[data-testid="stForm"] textarea {
                min-height: 42px !important; /* Force match button height */
                height: 42px !important;
                padding-top: 8px !important;
                padding-bottom: 8px !important;
                line-height: 1.4 !important;
                overflow: hidden !important; /* Hide scrollbar for single line look */
                resize: none !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        with bottom_box:
            # 1. Audio Input Row with Clone Button
            # Use gap="small" to bring buttons closer
            # Adjust weights: Audio takes most space, buttons take minimal space
            c_audio, c_transcribe, c_btn = st.columns([12, 0.5, 0.5], gap="small", vertical_alignment="center")
            with c_audio:
                audio_value = st.audio_input("Record Voice", key="req_audio", label_visibility="collapsed")
            with c_transcribe:
                # Manual transcribe button
                # Using icon parameter and empty label for icon-only button
                if st.button("", icon=":material/description:", help="Transcribe to Text", key="btn_transcribe_req"):
                    if "last_req_audio_path" in st.session_state:
                        v_path = st.session_state.last_req_audio_path
                        with st.spinner("..."):
                            text = transcribe_audio(v_path)
                            _log(f"Transcribed text: '{text}'")
                        if text:
                            st.session_state.draft_input = text
                            # st.toast(f"Recognized: {text[:min(20, len(text))]}...")
                        else:
                            st.warning("No text recognized.")
                    else:
                         st.toast("⚠️ No audio recorded.")
            with c_btn:
                # Small button for saving clone voice, only enabled if audio exists
                # Since st.audio_input triggers rerun, we check session state path
                if st.button("", icon=":material/save:", help="Save as Cloned Voice", key="btn_save_clone"):
                    if "last_req_audio_path" in st.session_state and os.path.exists(st.session_state.last_req_audio_path):
                         # Create a persistent copy
                         cv_dir = os.path.join(tmp_base, "cloned_voices")
                         os.makedirs(cv_dir, exist_ok=True)
                         cv_path = os.path.join(cv_dir, f"cloned_{uuid.uuid4().hex}.wav")
                         shutil.copy2(st.session_state.last_req_audio_path, cv_path)
                         
                         st.session_state.cloned_voice_path = cv_path
                         st.session_state.selected_voice_path = cv_path
                         st.toast("✅ Voice saved as Cloned Voice!")
                    else:
                         st.toast("⚠️ No audio recorded to save.")

            # Process Audio (Only save, do not auto transcribe)
            if audio_value:
                # Clean up previous audio to save space
                if "last_req_audio_path" in st.session_state and os.path.exists(st.session_state.last_req_audio_path):
                    try: os.remove(st.session_state.last_req_audio_path)
                    except: pass

                # Save new audio
                v_tmp_path = os.path.join(tmp_base, f"voice_{uuid.uuid4().hex[:6]}.wav")
                with open(v_tmp_path, "wb") as f: f.write(audio_value.read())
                _log(f"Audio saved to {v_tmp_path}, size={os.path.getsize(v_tmp_path)}")
                
                st.session_state.last_req_audio_path = v_tmp_path
                st.toast("Audio recorded. Click 📝 to transcribe or 💾 to save voice.")
            
            # 2. Input Area
            # If we have a voice draft, show an editable text area instead of chat_input?
            # Or always use text area + send button for maximum control?
            # Let's try: If draft exists, show text_area. If not, show chat_input?
            # Mixing them might be jarring.
            # Let's use a unified input box (text_area) that looks like chat.
            
            draft_text = st.session_state.get("draft_input", "")
            
            # Using a form to make it feel like chat input
            with st.form(key="chat_form", clear_on_submit=True):
                c_input, c_btn = st.columns([8, 1], vertical_alignment="bottom")
                with c_input:
                    user_text = st.text_area("Requirements", value=draft_text, height=35, label_visibility="collapsed", placeholder="Tell DeepSlide your requirements...")
                with c_btn:
                    submitted = st.form_submit_button("Send", icon=":material/send:", type="primary", use_container_width=True)
            
            if submitted and user_text:
                final_input = user_text
                # Clear draft
                if "draft_input" in st.session_state: del st.session_state["draft_input"]
                
                with st.spinner("Analyzing..."):
                    st.session_state.collector.process_user_input(final_input)
                if st.session_state.collector.is_confirmed:
                    st.session_state.app_state = "CONFIRMATION"
                    st.session_state.auto_generate_chain = True
                st.rerun()
