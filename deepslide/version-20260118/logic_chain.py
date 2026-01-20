import streamlit as st
import os
import shutil
import uuid
from ui import render_header
from core import _wrap_tools, ROOT, BASE_TEX_TEMPLATE, _requirements_json
from ppt_agent import _update_pdf_preview
from compressor import Compressor
from compiler import Compiler
from data_types import LogicFlow, LogicNode

def render_page_logic_chain(tmp_base):
    render_header(
        "Logic Chain",
        "Confirm the narrative flow and generate slides.",
        active_step=2,
    )
    
    if st.session_state.auto_generate_chain and not st.session_state.get("inline_chain_editor"):
        # with st.spinner("Generating logic chain..."):
        req = _requirements_json()
        from content_tree_builder import make_tree_tools
        from chain_ai_generator import generate_chain_via_tools
        tools = make_tree_tools(st.session_state.content_tree_nodes)
        data = generate_chain_via_tools(_wrap_tools(tools), req.get("focus_sections", []), str(req.get("duration", "5min")), st.session_state.collector.paper_abstract or "", conversation_history=st.session_state.collector.conversation_history)
        
        from logic_chain_editor import LogicChainEditor
        editor = LogicChainEditor()
        
        # Parse total duration for the editor
        total_min = editor._parse_total_minutes(req.get("duration", "10min"))
        
        if data: editor.set_from_chain_json(data, total_minutes=total_min)
        else: editor.create_from_requirements(req)
        st.session_state.inline_chain_editor = editor
        st.session_state.auto_generate_chain = False

    editor = st.session_state.get("inline_chain_editor")
    if editor:
        from logic_chain_editor import LogicChainUI
        ui = LogicChainUI(editor)
        ui.render()

        # st.divider()
        # st.header("Generation")
        # st.subheader("Continue")
        
        c1, c2 = st.columns([1, 4])
        # with c2:
        #     st.info("The PPT will be generated first. You can select voice settings in the next editing phase.")
            
        with c1:
            if st.button("Start Slide Generation", type="primary"):
                st.session_state.generating = True
                st.rerun()

    if st.session_state.get("generating"):
        with st.status("Generating...", expanded=False) as status:
            try:
                # 1. LogicFlow
                logic_nodes = [LogicNode(name=n.name, description=n.description, duration=n.duration) for n in editor.nodes]
                logic_flow = LogicFlow(nodes=logic_nodes)
                
                # 2. Output & Template (Setup before compression to allow ref.bib access)
                output_dir = os.path.join(tmp_base, f"gen_{uuid.uuid4().hex}")
                os.makedirs(output_dir, exist_ok=True)
                
                # Template
                try: from templater import Templater
                except: Templater = None
                
                if Templater:
                    t = Templater(config_dir=os.path.join(ROOT, "deepslide/config"), embdding_dir=os.path.join(ROOT, "template/rag"), template_dir=os.path.join(ROOT, "template/beamer"))
                    req = _requirements_json()
                    sel = t.select(req.get("style_preference", "academic"))
                    t_path = os.path.join(ROOT, "template/beamer", sel)
                    if os.path.exists(t_path):
                        for item in os.listdir(t_path):
                            s = os.path.join(t_path, item)
                            if os.path.isfile(s): shutil.copy2(s, os.path.join(output_dir, item))
                        pic_src = os.path.join(t_path, "picture")
                        if os.path.exists(pic_src): shutil.copytree(pic_src, os.path.join(output_dir, "picture"), dirs_exist_ok=True)
                    else:
                        with open(os.path.join(output_dir, "base.tex"), "w") as f: f.write(BASE_TEX_TEMPLATE)
                    t.modify(output_dir, req.get("style_preference", "academic"))
                else:
                    with open(os.path.join(output_dir, "base.tex"), "w") as f: f.write(BASE_TEX_TEMPLATE)

                # 3. Compressor
                compressor = Compressor()
                extract_dir = st.session_state.get("extract_dir", "")
                img_list = []
                if extract_dir:
                    for r, d, f in os.walk(extract_dir):
                        for file in f:
                            if file.lower().endswith(('.png', '.jpg', '.pdf')):
                                img_list.append(os.path.relpath(os.path.join(r, file), extract_dir))
                
                # status.write("Compressing...")
                # Pass output_dir to allow adding citations
                content, speeches = compressor.compress(logic_flow, st.session_state.get("content_tree_nodes", []), image_list=img_list, output_dir=output_dir)
                
                # 5. Title & Content
                # Generate a safe title from paper name
                paper_name = st.session_state.collector.paper_file_name or "Presentation"
                # Remove extension and replace underscores with spaces
                safe_title = os.path.splitext(paper_name)[0].replace("_", " ")
                # Escape special LaTeX characters if needed, but basic replacement helps a lot
                
                with open(os.path.join(output_dir, "title.tex"), "w") as f:
                    f.write(f"\\title{{{safe_title}}}\n\\author{{Generated by DeepSlide}}\n\\date{{\\today}}\n")
                
                with open(os.path.join(output_dir, "content.tex"), "w") as f:
                    content.to_file(f)
                
                # 6. Images
                pic_dst = os.path.join(output_dir, "picture")
                os.makedirs(pic_dst, exist_ok=True)
                if extract_dir:
                    for r, d, f in os.walk(extract_dir):
                        for file in f:
                            if file.lower().endswith(('.png', '.jpg')):
                                shutil.copy2(os.path.join(r, file), os.path.join(pic_dst, file))
                
                # 7. Compile
                status.write("Compiling...")
                # MAX_COMPILE_TRIES = 10
                c = Compiler()
                res = c.run(output_dir, source_dir=extract_dir)
                compile_success = res.get("success")

                print(f"Compilation result: {res}")
                
                # 8. Speech Align - Only if compile success
                if compile_success:
                    try:
                        from speech_aligner import SpeechAligner
                        aligner = SpeechAligner()
                        pdf = os.path.join(output_dir, "base.pdf")
                        print(f"PDF path for alignment: {pdf}")
                        if os.path.exists(pdf):
                            print("Start alignment...")
                            aligned = aligner.align(pdf, [str(s) for s in speeches])
                            print(f"Alignment result: {aligned}")
                            if aligned: speeches = aligned
                        else:
                            st.error(f"PDF file not found for alignment: {pdf}")
                    except Exception as e: 
                        st.error(f"Align Error: {e}")

                print(f"Generated speeches: {speeches}")
                
                sp_txt = "\n<next>\n".join([str(s).strip() for s in speeches])
                with open(os.path.join(output_dir, "speech.txt"), "w") as f: f.write(sp_txt)

                print(f"Saved speeches: {speeches}")
                
                st.session_state.generated_files = {
                    "pdf": os.path.join(output_dir, "base.pdf"),
                    "tex": os.path.join(output_dir, "content.tex"),
                    "speech": os.path.join(output_dir, "speech.txt"),
                    "audio_dir": output_dir
                }
                
                # Load preview only if PDF exists
                if compile_success and os.path.exists(st.session_state.generated_files["pdf"]):
                    print(f"Loading PDF preview from: {st.session_state.generated_files['pdf']}")
                    _update_pdf_preview()
                    print("PDF preview images generated.")
                
                # Even if failed, we save speech segments so user can see them
                st.session_state.preview_state["speech_segments"] = [str(s) for s in speeches]
                st.session_state.workflow_phase = "EDITING"
                st.rerun()

            except Exception as e:
                st.error(f"Gen Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                st.session_state.generating = False
