import streamlit as st
import os
import shutil
import uuid
import json
from ui import render_header
from core import _components_html
from audio import run_tts, transcribe_audio
from ppt_agent import process_slide_modification, _update_pdf_preview
from visuals import _render_vis_network, get_slide_card_html
from html_export import generate_html_via_llm_iterative, _batch_beautify_slides
from compiler import Compiler

def render_page_ppt_editor(tmp_base):
    render_header(
        "Editing",
        "Review slides, update content and speech, and run AI enhancements.",
        active_step=3,
    )
    files = st.session_state.generated_files
    
    if "starred_slides" not in st.session_state:
        st.session_state.starred_slides = set()
    
    # Ensure we are in EDITING phase if this function is called
    # st.header("📝 Edit Phase")
    # st.info("Modify slides/speech. Preview is visual only.")
    
    c_l, c_r = st.columns([1, 1])
    with c_l:
        st.subheader("Visual Preview")
        pages = st.session_state.preview_state.get("pdf_pages", [])
        if pages:
            curr = st.session_state.preview_state.get("current_page", 0)
            # Navigation buttons moved to bottom
            pass

            # Enhanced Slide Preview using HTML/CSS
            try:
                current_img_path = pages[st.session_state.preview_state["current_page"]]
                if os.path.exists(current_img_path):
                    # Use components.html to render the card
                    # Height 400px is approximate for 16:9 within column
                    # But component iframe has fixed height. Let's try 400.
                    # Actually visuals.py style sets height 100% of container.
                    # We need to give component enough height. 16:9 of half width...
                    # Let's say column width ~600px -> height ~340px. Safe 400.
                    
                    html_content = get_slide_card_html(current_img_path, 
                                                       page_index=st.session_state.preview_state["current_page"], 
                                                       total_pages=len(pages))
                    _components_html(html_content, height=540, scrolling=False)
                else:
                    st.error("Preview image not found.")
            except Exception as e:
                st.error(f"Preview Error: {e}")
                st.image(pages[st.session_state.preview_state["current_page"]]) # Fallback

            st.markdown(
                """
                <style>
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) {
                    height: 0;
                    margin: 0;
                    padding: 0;
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div {
                    margin-top: -74px;
                    position: relative;
                    z-index: 30;
                    width: fit-content;
                    margin-left: auto;
                    margin-right: auto;
                    padding: 6px 10px;
                    border-radius: 999px;
                    background: rgba(0, 0, 0, 0.55);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    backdrop-filter: blur(8px);
                    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25);
                    opacity: 0.18;
                    transition: opacity 0.18s ease, transform 0.18s ease;
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div:hover {
                    opacity: 0.72;
                    transform: translateY(-1px);
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button {
                    width: 38px;
                    min-height: 38px;
                    padding: 0;
                    border: 0;
                    border-radius: 999px;
                    background: transparent;
                    color: rgba(255, 255, 255, 0.92);
                    font-weight: 600;
                    font-size: 16px;
                    line-height: 1;
                    transition: background 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button:hover {
                    background: rgba(255, 255, 255, 0.12);
                    transform: translateY(-1px);
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button:active {
                    transform: translateY(0);
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button:disabled {
                    opacity: 0.35;
                    cursor: not-allowed;
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button:focus-visible {
                    outline: none;
                    box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.22);
                }
                div[data-testid="stMarkdownContainer"]:has(.ed-controls-marker) + div button[kind="primary"] {
                    background: rgba(255, 215, 0, 0.18);
                    color: rgba(255, 245, 200, 0.98);
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            st.markdown('<div class="ed-controls-marker"></div>', unsafe_allow_html=True)
            
            def _safe_button(*args, **kwargs):
                try:
                    return st.button(*args, **kwargs)
                except TypeError:
                    kwargs.pop("disabled", None)
                    return st.button(*args, **kwargs)

            at_first = curr <= 0
            at_last = curr >= (len(pages) - 1)

            _, nav_prev, _, nav_star, _, nav_next, _ = st.columns([5.0, 0.9, 0.9, 0.9, 0.9, 0.9, 5.0])

            with nav_prev:
                if _safe_button("◀", key="ed_prev", help="Previous Slide", disabled=at_first):
                    st.session_state.preview_state["current_page"] = max(0, curr - 1)
                    st.rerun()

            with nav_star:
                is_starred = curr in st.session_state.starred_slides
                star_icon = "★" if is_starred else "☆"
                help_text = "Remove from collection" if is_starred else "Add to collection"
                btn_type = "primary" if is_starred else "secondary"
                if _safe_button(star_icon, key="ed_star", help=help_text, type=btn_type):
                    if is_starred:
                        st.session_state.starred_slides.remove(curr)
                    else:
                        st.session_state.starred_slides.add(curr)
                    st.rerun()

            with nav_next:
                if _safe_button("▶", key="ed_next", help="Next Slide", disabled=at_last):
                    st.session_state.preview_state["current_page"] = min(len(pages) - 1, curr + 1)
                    st.rerun()

            # Show speech preview below image
            speeches = st.session_state.preview_state.get("speech_segments", [])
            speech_idx = st.session_state.preview_state["current_page"]
            if 0 <= speech_idx < len(speeches):
                 display_text = speeches[speech_idx].replace("<add>", "").strip()
                 with st.expander("Speech Preview", expanded=False):
                     st.caption(display_text)
    
    with c_r:
        st.subheader("Editors")
        tabs = st.tabs(["📕 Basic", "⭐ AI Voice", "⭐ AI Beautify", "⭐ AI Enrich"])
        
        # Load extra files
        title_path = os.path.join(os.path.dirname(files["tex"]), "title.tex")
        base_path = os.path.join(os.path.dirname(files["tex"]), "base.tex")

        n_tex, n_sp, n_title, n_base = "", "", "", ""

        with tabs[0]:
            c1, c2 = st.columns([1, 1])

            with c1:
                with st.expander("Content", expanded=False):
                    with open(files["tex"], "r") as f:
                        c_tex = f.read()
                    n_tex = st.text_area("content.tex", c_tex, height=260)

                with st.expander("Speech", expanded=False):
                    with open(files["speech"], "r") as f:
                        s_txt = f.read()
                    n_sp = st.text_area("speech.txt", s_txt, height=260)

            with c2:
                with st.expander("Title", expanded=False):
                    if os.path.exists(title_path):
                        with open(title_path, "r") as f:
                            t_tex = f.read()
                        n_title = st.text_area("title.tex", t_tex, height=260)
                    else:
                        st.warning("title.tex not found")
                        n_title = ""

                with st.expander("Base", expanded=False):
                    if os.path.exists(base_path):
                        with open(base_path, "r") as f:
                            b_tex = f.read()
                        n_base = st.text_area("base.tex", b_tex, height=260)
                    else:
                        st.warning("base.tex not found")
                        n_base = ""

        with tabs[1]:
            st.write("**Voice Settings**")
            # Voice Selection Logic (Same as Logic Chain page)
            # Filter to only keep voice_03 and cloned voice
            voice_opts = {"Default Voice": "examples/voice_03.wav"}
            if st.session_state.get("cloned_voice_path"):
                voice_opts["Cloned Voice"] = st.session_state.get("cloned_voice_path")
            
            # Determine current selection label
            current_path = st.session_state.get("selected_voice_path", "examples/voice_03.wav")
            current_label = "Default Voice" # Default fallback
            for k, v in voice_opts.items():
                if v == current_path:
                    current_label = k
                    break
            
            # If current path not in options (e.g. lost?), default to Default Voice
            if current_label not in voice_opts:
                current_label = "Default Voice"
                
            v_label = st.selectbox("Select Voice Preference", list(voice_opts.keys()), index=list(voice_opts.keys()).index(current_label))
            st.session_state.selected_voice_path = voice_opts[v_label]
            
            # st.divider()
            st.checkbox("Generate Audio", value=True, key="gen_audio_toggle", help="Uncheck to skip audio generation and go directly to preview.")
            
            # st.divider()
            st.write("**Update Cloned Voice**")
            # st.info("Record a short audio clip to clone your voice.")
            clone_audio = st.audio_input("Record for Cloning", key="ed_clone_audio")
            if clone_audio:
                # Save new clone
                os.makedirs(os.path.join(tmp_base, "cloned_voices"), exist_ok=True)
                c_path = os.path.join(tmp_base, "cloned_voices", f"cloned_{uuid.uuid4().hex}.wav")
                with open(c_path, "wb") as f:
                    f.write(clone_audio.read())
                
                if st.button("💾 Save Cloned Voice"):
                    st.session_state.cloned_voice_path = c_path
                    st.session_state.selected_voice_path = c_path
                    st.success("Cloned voice updated and selected!")
                    st.rerun()
        
        with tabs[2]:
            #  st.header("AI Visual Beautification")
             st.info("Enhance content using VLM.")
            #  st.markdown("The AI will analyze the slide image and LaTeX code, then optimize the layout and styling iteratively.")
             
             rounds = st.number_input("Optimization Rounds", min_value=1, max_value=8, value=3)
             
             if st.button("GO!", type="primary"):
                 _batch_beautify_slides(rounds)
                 st.rerun()
        
        with tabs[3]:
            st.info("Generate reference graph and refine speech.")
            
            # Display existing graph if available
            if "reference_graph_data" in st.session_state:
                # st.subheader("Reference Graph") # Removed header to put in expander
                res = st.session_state.reference_graph_data
                
                # Render using Vis.js via components
                try:
                    pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
                    files = st.session_state.generated_files
                    
                    with st.expander(" Reference Graph ", expanded=True):
                        html_viz, viz_height = _render_vis_network(res, pdf_pages, files)
                        _components_html(html_viz, height=viz_height, scrolling=False)
                        
                        # Raw data nested expander
                        with st.expander("Raw Graph Data"):
                            st.json(res)
                except Exception as e:
                    st.error(f"Viz Error: {e}")

            if st.button("Enrich References", type="primary"):
                with st.spinner("Enrich References..."):
                    try:
                        from slide_graph_generator import SlideGraphGenerator
                        gen = SlideGraphGenerator()
                        
                        files = st.session_state.generated_files
                        with open(files["tex"], "r") as f: content_tex = f.read()
                        with open(files["speech"], "r") as f: speech_txt = f.read()
                        speeches = speech_txt.split("<next>")
                        
                        logic_chain = st.session_state.logic_chain_json
                        if not logic_chain and st.session_state.get("inline_chain_editor"):
                            editor = st.session_state.inline_chain_editor
                            logic_chain = {
                                "nodes": [{"name": n.name, "description": n.description, "duration": n.duration} for n in editor.nodes],
                                "edges": [{"from": e["from"], "to": e["to"], "type": e.get("type", "sequential"), "reason": e.get("reason", "")} for e in editor.edges]
                            }

                        # Call run with pdf_path to allow on-the-fly alignment
                        res = gen.run(content_tex, speeches, logic_chain, pdf_path=files["pdf"], use_llm=True)
                        
                        # Refine Speech based on the generated graph
                        with st.spinner("Refining speech based on slide relationships..."):
                            refined_speeches_map = gen.refine_speech(res)
                            if refined_speeches_map:
                                # Update speeches list
                                updated_count = 0
                                for slide_id, new_text in refined_speeches_map.items():
                                    if 0 <= slide_id < len(speeches):
                                        speeches[slide_id] = new_text
                                        updated_count += 1
                                
                                # Save back to file
                                new_speech_txt = "<next>".join(speeches)
                                with open(files["speech"], "w") as f:
                                    f.write(new_speech_txt)
                                
                                # Force update session state preview if it exists
                                if "preview_state" in st.session_state:
                                    st.session_state.preview_state["speech_segments"] = [str(s) for s in speeches]
                                
                                st.success(f"Updated {updated_count} speech segments with reference logic.")
                            else:
                                st.info("No speech refinement needed (no reference edges found or LLM declined).")
                        
                        out_path = os.path.join(files["audio_dir"], "slide_relationships.json")
                        with open(out_path, "w", encoding="utf-8") as f:
                            json.dump(res, f, indent=2, ensure_ascii=False)
                        
                        st.success(f"Slide Graph generated! Saved to {out_path}")
                        st.session_state.reference_graph_data = res
                        st.json(res)
                        # Rerun to refresh speech editor content
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.text(traceback.format_exc())

            # st.divider()
            # st.write("### HTML Slide Generation")
            st.info("Dynamic Slide Generation.")

            default_effects = st.session_state.get(
                "ai_enrich_effects",
                ["Image Focus", "Table Viz", "Text Keynote"],
            )
            effects = st.multiselect(
                "Enrich Effects",
                ["Image Focus", "Table Viz", "Text Keynote"],
                default=default_effects,
                help="Select one or more enhancement types for collected slides.",
            )
            st.session_state.ai_enrich_effects = effects
            
            # Show collected slides count
            starred = st.session_state.get("starred_slides", set())
            if starred:
                st.caption(f"Collected Slides: {len(starred)} selected.")
            else:
                st.caption("No slides collected. No slides will be enriched.")

            # Per-slide max_regions configuration for collected slides
            per_slide_max_regions = {}
            starred = st.session_state.get("starred_slides", set())
            if starred and ("Image Focus" in effects):
                st.write("**Slide Configurations:**")
                sorted_starred = sorted(list(starred))
                for s_idx in sorted_starred:
                    # Default to 5
                    per_slide_max_regions[s_idx] = st.number_input(
                        f"Max Regions for Slide {s_idx+1}", min_value=1, max_value=8, value=3, key=f"max_regions_{s_idx}")
            else:
                 pass

            # Hardcoded defaults as requested by user
            # st.session_state.html_use_llm_conversion = True
            # st.session_state.html_focus_all_slides = False
            # st.session_state.html_focus_prefer_vlm = True
            # st.session_state.html_focus_zoom_cfg = {
            #     "enabled": True,
            #     "max_regions": 5, # Default, will be overridden by per_slide map
            #     "interval_ms": 2000,
            #     "scale": 1.1,
            #     "cache": True,
            # }

            if st.button("Generate!", type="primary"):
                with st.spinner("Generating HTML via AI Agent..."):
                    try:
                        with open(files["tex"], "r") as f: c_tex = f.read()
                        with open(files["speech"], "r") as f: s_txt = f.read()
                        if isinstance(c_tex, bytes): c_tex = c_tex.decode("utf-8")
                        if isinstance(s_txt, bytes): s_txt = s_txt.decode("utf-8")
                        speeches = s_txt.split("<next>")
                        pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
                        
                        starred = st.session_state.get("starred_slides", set())
                        # Ensure starred is a set of integers
                        if starred:
                            starred = {int(x) for x in starred}

                        print(f"DEBUG UI: Starred slides in session state: {starred}")
                        
                        focus_indices = starred if starred else None
                        
                        # If no slides collected, return empty or handle gracefully
                        if not starred:
                            st.warning("No slides collected. Please star slides in the editor to generate an enriched HTML.")
                            full_html = "" # Or handle as per requirement: skip processing
                        else:
                            # Pass the per-slide config
                            full_html = generate_html_via_llm_iterative(
                                c_tex, 
                                speeches, 
                                pdf_pages, 
                                focus_candidate_indices=focus_indices,
                                per_slide_max_regions=per_slide_max_regions,
                                enrich_effects=effects,
                            )
                        
                        if full_html:
                            # print(f"Generated HTML: {full_html}")
                            st.session_state.html_slides_content = full_html
                            st.success("HTML Slide generated by AI!")
                        elif starred: # Only show error if we attempted generation
                            st.error("AI generation failed.")

                    except Exception as e:
                        st.error(f"Error reading files: {e}")
            
            if "html_slides_content" in st.session_state and st.session_state.html_slides_content:
                starred = st.session_state.get("starred_slides", set())
                label = "Collected Slides Preview" if starred else "HTML Slide Preview"
                
                with st.expander(label, expanded=True):
                    # No sync injection as per user request
                    synced_html = st.session_state.html_slides_content
                    # Ensure the HTML container has enough height and is properly rendered
                    _components_html(synced_html, height=600, scrolling=True, key="html_slide_preview")
                    # Option to download HTML
                    st.download_button("Download HTML", synced_html, "presentation.html", "text/html")
    
    # st.divider()
    c_a1, c_a2 = st.columns([1, 1])
    with c_a1:
        if st.button("🔄 UPDATE"):
            with open(files["tex"], "w") as f: f.write(n_tex)
            with open(files["speech"], "w") as f: f.write(n_sp)
            if n_title:
                with open(title_path, "w") as f: f.write(n_title)
            if n_base:
                with open(base_path, "w") as f: f.write(n_base)
            
            c = Compiler()
            if c.run(os.path.dirname(files["tex"])).get("success"):
                st.success("Updated")
                _update_pdf_preview()
                st.rerun()
    with c_a2:
        if st.button("✅ FINISH"):
            with open(files["tex"], "w") as f: f.write(n_tex)
            with open(files["speech"], "w") as f: f.write(n_sp)
            if n_title:
                with open(title_path, "w") as f: f.write(n_title)
            if n_base:
                with open(base_path, "w") as f: f.write(n_base)
            
            c = Compiler()
            if c.run(os.path.dirname(files["tex"])).get("success"):
                if st.session_state.get("gen_audio_toggle", True):
                    with st.status("Generating Audio...", expanded=True) as status:
                        st.write("Initializing TTS engine...")
                        # Use selected voice or default to examples/voice_03.wav
                        # If user recorded a cloned voice earlier, it should be in selected_voice_path if they selected it
                        voice_p = st.session_state.get("selected_voice_path", "examples/voice_03.wav")
                        
                        st.write(f"Using voice: {voice_p}")

                        with st.spinner("Generating audio..."):
                            success = run_tts(n_sp, files["audio_dir"], voice_p)
                        
                        if success:
                            status.update(label="Audio Generation Completed!", state="complete", expanded=False)
                        else:
                            status.update(label="Audio Generation Failed", state="error", expanded=True)
                            st.session_state.tts_error = "TTS Generation failed. Please check the logs."
                            import time
                            time.sleep(3) # Wait a bit for user to see the status

                        st.session_state.workflow_phase = "PREVIEW"
                        st.rerun()
                else:
                    st.session_state.workflow_phase = "PREVIEW"
                    st.rerun()

    # Bottom Input for Edit
    try: bottom_box = st.bottom_container()
    except: bottom_box = st.container()
    with bottom_box:
        # 1. Audio Input Row (Consistent with Page 1)
        c_audio, c_transcribe, c_btn = st.columns([15, 1, 1])
        with c_audio:
            audio_value = st.audio_input("Record Command", key="ed_audio")
        with c_transcribe:
            st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
            if st.button("📝", help="Transcribe to Text", key="ed_btn_transcribe"):
                if "last_ed_audio_path" in st.session_state:
                    v_path = st.session_state.last_ed_audio_path
                    with st.spinner("..."):
                        text = transcribe_audio(v_path)
                    if text:
                        st.session_state.ed_draft_input = text
                        st.toast(f"Recognized: {text[:min(20, len(text))]}...")
                    else:
                        st.warning("No text recognized.")
                else:
                    st.toast("⚠️ No audio recorded.")
        with c_btn:
            st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
            # Small button for saving clone voice, only enabled if audio exists
            # Since st.audio_input triggers rerun, we check session state path
            if st.button("💾", help="Save as Cloned Voice", key="ed_btn_save_clone"):
                if "last_ed_audio_path" in st.session_state and os.path.exists(st.session_state.last_ed_audio_path):
                        # Create a persistent copy
                        cv_dir = os.path.join(tmp_base, "cloned_voices")
                        os.makedirs(cv_dir, exist_ok=True)
                        cv_path = os.path.join(cv_dir, f"cloned_{uuid.uuid4().hex}.wav")
                        shutil.copy2(st.session_state.last_ed_audio_path, cv_path)

                        st.session_state.cloned_voice_path = cv_path
                        st.session_state.selected_voice_path = cv_path
                        st.toast("✅ Voice saved as Cloned Voice!")
                else:
                        st.toast("⚠️ No audio recorded to save.")

        if audio_value:
            # Clean up previous audio to save space
            if "last_ed_audio_path" in st.session_state and os.path.exists(st.session_state.last_ed_audio_path):
                try: os.remove(st.session_state.last_ed_audio_path)
                except: pass

            v_tmp_path = os.path.join(tmp_base, "cloned_voices", f"voice_{uuid.uuid4().hex}.wav")
            with open(v_tmp_path, "wb") as f: f.write(audio_value.read())
            st.session_state.last_ed_audio_path = v_tmp_path
            st.toast("Audio recorded. Click 📝 to transcribe or 💾 to save voice.")

        # 2. Text Input Row (Consistent with Page 1)
        ed_draft = st.session_state.get("ed_draft_input", "")
        with st.form(key="ed_chat_form", clear_on_submit=True):
            c_input, c_btn = st.columns([8, 1])
            with c_input:
                user_text = st.text_area("Command", value=ed_draft, height=35, label_visibility="collapsed", placeholder="Enter modification command...")
            with c_btn:
                st.markdown('<div style="height: 3px;"></div>', unsafe_allow_html=True)
                submitted = st.form_submit_button("➤ Send")
        
        if submitted and user_text:
            if "ed_draft_input" in st.session_state: del st.session_state["ed_draft_input"]
            with st.spinner("Analyzing and Modifying Slide... Please wait."):
                if process_slide_modification(user_text):
                    st.rerun()
