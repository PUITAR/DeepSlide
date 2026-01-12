import streamlit as st
import os
import sys
import json
import uuid
from typing import Any, Dict, Optional
import subprocess
import shutil
import re
import fitz  # PyMuPDF
import base64
from pathlib import Path

# global tool logs (thread-safe append in CPython)
TOOL_LOGS: list[str] = []

# ensure project root on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

# ensure current directory on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from ppt_requirements_collector import PPTRequirementsCollector

from project_analyzer import (
    save_uploaded_file,
    extract_archive,
    find_main_tex,
    merge_project_to_main,
    extract_abstract_from_dir,
    extract_title_from_dir,
)
from divider import Divider
from compiler import Compiler

# Import Compressor
try:
    from compressor import Compressor
    from data_types import LogicFlow, LogicNode
except ImportError:
    # Fallback usually not needed in flat structure
    pass

def _init_state() -> None:
    if "collector" not in st.session_state:
        # Assuming PPTRequirementsCollector is in the same dir
        from ppt_requirements_collector import PPTRequirementsCollector
        st.session_state.collector = PPTRequirementsCollector()
    if "uploaded" not in st.session_state:
        st.session_state.uploaded = False
    if "app_state" not in st.session_state:
        st.session_state.app_state = "UPLOAD"  # UPLOAD | CONVERSATION | CONFIRMATION | COMPLETED
    if "logic_chain_json" not in st.session_state:
        st.session_state.logic_chain_json = None
    if "auto_generate_chain" not in st.session_state:
        st.session_state.auto_generate_chain = False
    if "edges_rec" not in st.session_state:
        from edges_recommender import EdgesRecommender
        st.session_state.edges_rec = EdgesRecommender()
    if "preview_state" not in st.session_state:
        st.session_state.preview_state = {
            "pdf_pages": [],
            "current_page": 0,
            "auto_play": False,
            "audio_ended": False
        }
    # tool logs are kept in module-global list to avoid thread context issues

def _wrap_tools(tools):
    wrapped = []
    import datetime
    import json
    import functools  # Import functools
    
    # per-session cache & budget for tool calls
    cache: dict[tuple, str] = {}
    per_tool_counts: dict[str, int] = {}
    total_count: int = 0
    PER_TOOL_LIMIT = 5
    TOTAL_LIMIT = 20
    
    def make_wrapper(fn):
        name = getattr(fn, "__name__", "tool")
        
        @functools.wraps(fn)  # Use wraps to preserve signature and docstring
        def wrapper(*args, **kwargs):
            try:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                # ... rest of the wrapper logic ...
                TOOL_LOGS.append(f"[{ts}] call {name} args={args} kwargs={kwargs}")
                try:
                    print(f"[{ts}] call {name} args={args} kwargs={kwargs}")
                except Exception:
                    pass
                    
                # budget check
                nonlocal total_count
                k = (name, json.dumps(args, ensure_ascii=False, default=str), json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str))
                cnt = per_tool_counts.get(name, 0)
                
                if k in cache:
                    out = cache[k]
                    preview = out[:300].replace("\n", " ")
                    TOOL_LOGS.append(f"[{ts}] ret {name} (cached) -> {preview}")
                    try:
                        print(f"[{ts}] ret {name} (cached) -> {preview}")
                    except Exception:
                        pass
                    return out
                    
                if cnt >= PER_TOOL_LIMIT or total_count >= TOTAL_LIMIT:
                    out = "Tool budget exhausted"
                    preview = out
                    TOOL_LOGS.append(f"[{ts}] ret {name} (budget) -> {preview}")
                    try:
                        print(f"[{ts}] ret {name} (budget) -> {preview}")
                    except Exception:
                        pass
                    cache[k] = out
                    return out
                    
                out = fn(*args, **kwargs)
                
                if isinstance(out, str):
                    preview = out[:300].replace("\n", " ")
                else:
                    preview = str(out)[:300]
                    
                TOOL_LOGS.append(f"[{ts}] ret {name} -> {preview}")
                try:
                    print(f"[{ts}] ret {name} -> {preview}")
                except Exception:
                    pass
                    
                per_tool_counts[name] = cnt + 1
                total_count += 1
                cache[k] = out if isinstance(out, str) else str(out)
                return out
                
            except Exception as e:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                TOOL_LOGS.append(f"[{ts}] error {name}: {e}")
                try:
                    print(f"[{ts}] error {name}: {e}")
                except Exception:
                    pass
                raise
                
        # wrapper.__name__ = name # handled by wraps
        # wrapper.__doc__ = getattr(fn, "__doc__", "") or f"Wrapped tool {name}" # handled by wraps
        return wrapper
        
    for fn in tools:
        wrapped.append(make_wrapper(fn))
    return wrapped

def _log(msg: str) -> None:
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    TOOL_LOGS.append(f"[{ts}] {msg}")
    try:
        print(f"[{ts}] {msg}")
    except Exception:
        pass


def _requirements_json() -> Dict[str, Any]:
    override = st.session_state.get("requirements_override")
    if override:
        return override
    req = st.session_state.collector.get_requirements()
    return req.get("conversation_requirements") or {}

def run_tts(speech_text: str, output_dir: str, voice_prompt: str = 'examples/voice_03.wav'):
    """
    Generate audio files for the speech text.
    Uses the external script logic via subprocess.
    """
    import subprocess
    
    # Ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Save sample text
    sample_file = os.path.join(output_dir, "speech_script.txt")
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write(speech_text)
        
    # We will invoke a python script that calls IndexTTS
    # We assume IndexTTS is available in ROOT/index-tts/index-tts-main
    index_tts_dir = os.path.join(ROOT, "index-tts/index-tts-main")
    
    python_logic = f"""
import os
import sys
try:
    from indextts.infer_v2 import IndexTTS2
    from tqdm import tqdm
except ImportError:
    print("Error: indextts module not found.")
    sys.exit(1)

os.environ['USE_MODELSCOPE'] = '1'

try:
    print("Attempting to initialize TTS on CUDA...")
    tts = IndexTTS2(
        cfg_path='checkpoints/config.yaml', 
        model_dir='checkpoints', 
        use_fp16=False, 
        use_cuda_kernel=False, 
        use_deepspeed=False
    )
except Exception as e:
    print(f"Error initializing TTS on CUDA: {{e}}")
    print("Falling back to CPU (this may be slow)...")
    try:
        tts = IndexTTS2(
            cfg_path='checkpoints/config.yaml', 
            model_dir='checkpoints', 
            use_fp16=False, 
            use_cuda_kernel=False, 
            use_deepspeed=False,
            device='cpu'
        )
    except Exception as e2:
        print(f"Error initializing TTS on CPU: {{e2}}")
        sys.exit(1)

with open('{sample_file}', 'r', encoding='utf-8') as f:
    sample_text = f.read().split('<next>')

for i, text in tqdm(enumerate(sample_text), desc="Generating audios"):
    text = text.strip()
    # Remove <add> tag for TTS generation
    text = text.replace("<add>", "").strip()
    
    if not text: continue
    output_path = os.path.join('{output_dir}', f'{{i+1}}.wav')
    try:
        tts.infer(
            spk_audio_prompt='{voice_prompt}', 
            text=text, 
            output_path=output_path, 
            verbose=True
        )
    except Exception as e:
        print(f"Error generating audio for segment {{i}}: {{e}}")
"""
    
    try:
        _log(f"Starting TTS generation in {index_tts_dir}")
        # Use uv run python -c ...
        # Use full path to uv if possible
        # uv_path = "/home/ym/anaconda3/bin/uv"
        # if not os.path.exists(uv_path):
        #     uv_path = "uv" # fallback
            
        cmd = ["uv", "run", "python", "-c", python_logic]
        
        # Stream output
        process = subprocess.Popen(
            cmd, 
            cwd=index_tts_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            _log(f"TTS Failed: {stderr}")
            st.error(f"TTS Generation failed. Check logs.")
        else:
            _log("TTS Generation completed.")
            
    except Exception as e:
        _log(f"TTS Execution Error: {e}")

# Base TeX Template
BASE_TEX_TEMPLATE = r"""%!TeX encoding = UTF-8
%!TeX program = xelatex
\documentclass[notheorems, aspectratio=169]{beamer}
\usepackage{latexsym}
\usepackage{amsmath,amssymb}
\usepackage{mathtools}
\usepackage{color,xcolor}
\usepackage{graphicx}
\usepackage{algorithm}
\usepackage{amsthm}
\usepackage{lmodern} 
\usepackage{listings}
\usepackage{tikz}

\mode<presentation>{
    \usetheme{Berkeley}
    \usecolortheme{dolphin}
    \useoutertheme{infolines}
    \useinnertheme{circles}
}

\input{title}

\begin{document}

\begin{frame}
    \titlepage
\end{frame}

\input{content.tex}

\end{document}
"""

def render_preview_ui():
    if "preview_state" not in st.session_state:
        return
    state = st.session_state.preview_state
    pages = state.get("pdf_pages", [])
    speeches = state.get("speech_segments", [])
    
    if not pages:
        return

    st.divider()
    st.subheader("Presentation Preview")
    
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    if "current_page" not in state:
        state["current_page"] = 0
        
    with col_nav1:
        if st.button("Previous", key="prev_slide"):
            state["current_page"] = max(0, state["current_page"] - 1)
            st.rerun()
            
    with col_nav3:
        if st.button("Next", key="next_slide"):
            state["current_page"] = min(len(pages) - 1, state["current_page"] + 1)
            st.rerun()
            
    with col_nav2:
        st.markdown(f"<div style='text-align: center'>Slide {state['current_page'] + 1} / {len(pages)}</div>", unsafe_allow_html=True)
        
    col_disp1, col_disp2 = st.columns([2, 1])
    with col_disp1:
        st.image(pages[state["current_page"]], use_column_width=True)
        
    with col_disp2:
        speech_idx = state["current_page"]
        if 0 <= speech_idx < len(speeches):
            # Display speech without <add> tag
            display_text = speeches[speech_idx].replace("<add>", "").strip()
            st.markdown(f"**Speech Script:**\n\n{display_text}")
        else:
            st.info("No speech script available for this slide.")
    
    # Audio player
    if "generated_files" in st.session_state:
        audio_dir = st.session_state.generated_files.get("audio_dir")
        if audio_dir:
            wav_path = os.path.join(audio_dir, f"{state['current_page']+1}.wav")
            if os.path.exists(wav_path):
                 st.audio(wav_path, format="audio/wav")

def main() -> None:
    st.set_page_config(page_title="DeepSlide Pipeline", layout="wide")
    _init_state()
    
    try:
        tmp_base = os.path.join(ROOT, "deepslide/tmp_uploads")
        os.makedirs(tmp_base, exist_ok=True)
        os.chdir(tmp_base)
    except Exception:
        pass
    _log("Application started, entering main interface")

    st.title("DeepSlide Full Pipeline")

    # Sidebar: upload archive
    with st.sidebar:
        uploaded_file = st.file_uploader("Upload Paper Project Archive", type=["zip", "tar", "gz", "bz2", "xz"], accept_multiple_files=False)
        if uploaded_file is not None and not st.session_state.uploaded:
            try:
                tmp_base = os.path.join(ROOT, "deepslide/tmp_uploads")
                _log("Start saving uploaded file")
                archive_path = save_uploaded_file(uploaded_file, tmp_base)
                with st.spinner("Generating content tree..."):
                    prog = st.progress(5)
                    extract_dir = os.path.join(tmp_base, os.path.splitext(os.path.basename(archive_path))[0])
                    st.session_state.extract_dir = extract_dir
                    _log(f"Start extraction: {archive_path}")
                    extract_archive(archive_path, extract_dir)
                    prog.progress(25)
                    _log(f"Extraction completed: {extract_dir}")
                    main_tex = find_main_tex(extract_dir)
                    _log(f"Main file detection: {main_tex or 'Not found'}")
                    merged_path = ""
                    if main_tex:
                        _log("Start merging main file")
                        merged_path = merge_project_to_main(os.path.dirname(main_tex), main_tex, "merged_main.tex")
                        _log(f"Merge completed: {merged_path}")
                    prog.progress(60)
                    
                    # Use Divider to parse content tree
                    _log("Start parsing content tree...")
                    divider = Divider()
                    # Parse either merged_main or main_tex
                    target_tex = merged_path if merged_path and os.path.exists(merged_path) else (main_tex or "")
                    
                    nodes = []
                    if target_tex:
                         nodes = divider.divide(target_tex)
                         _log(f"Content tree parsing completed: {len(nodes)} nodes")
                    
                    # Store nodes in session state
                    st.session_state.content_tree_nodes = nodes
                    
                    abstract_text = extract_abstract_from_dir(extract_dir) or ""
                    _log(f"Abstract length: {len(abstract_text)}")
                    prog.progress(90)
                    
                    # Initialize Collector State
                    st.session_state.collector.set_paper_file(uploaded_file.name)
                    st.session_state.collector.set_paper_project(extract_dir, main_tex, merged_path)
                    st.session_state.collector.set_paper_abstract(abstract_text)
                    st.session_state.collector.prime_context()
                    
                    # Prepare Tools
                    from paper_tools import make_paper_tools
                    tools_paper = make_paper_tools(extract_dir, merged_path or (main_tex or ""))
                    
                    from content_tree_builder import make_tree_tools
                    # Pass pre-parsed nodes to make_tree_tools
                    tools_tree = make_tree_tools(nodes)
                    
                    # Set Tools to Camel Client
                    st.session_state.collector.camel_client.set_tools(_wrap_tools(tools_paper + tools_tree))
                    
                    if abstract_text:
                        st.session_state.collector.conversation_history.append({"role": "assistant", "content": f"Abstract detected:\n{abstract_text}"})
                    
                    st.session_state.collector.conversation_history.append({
                        "role": "assistant",
                        "content": "To get started, please tell me the following basic information:\n- Who is the audience?\n- Presentation duration?\n- Which chapters do you want to highlight?\n- Style preference?\nYou can answer one by one."
                    })
                    
                    # Mark as successfully uploaded ONLY after all setup is done
                    st.session_state.uploaded = True
                    st.session_state.app_state = "CONVERSATION"
                    st.success(f"Uploaded and parsed: {uploaded_file.name}")
                    st.rerun() # Rerun to refresh the UI immediately
            except Exception as e:
                st.session_state.uploaded = False # Reset on failure
                st.error(f"Error processing upload: {e}")
                _log(f"Upload error: {e}")
                import traceback
                traceback.print_exc()

        # st.divider()
        with st.expander("🛠 Tool Calls & Model Summary", expanded=False):
            msgs = [m for m in st.session_state.collector.conversation_history if (m.get("role") or "").lower() == "assistant"]
            show_preview = st.session_state.get("show_last_preview", True)
            if msgs and show_preview:
                last = msgs[-1].get("content") or ""
                st.caption("Latest assistant message (truncated):")
                st.code((last[:600] + ("..." if len(last) > 600 else "")))
            st.caption("Recent tool calls:")
            logs = TOOL_LOGS[-20:]
            if logs:
                st.text("\n".join(logs))
            else:
                st.text("No logs yet")
            st.caption(f"Total {len(TOOL_LOGS)} logs")
            if st.button("Clear Tool Logs", key="clear_tool_logs"):
                TOOL_LOGS.clear()
                st.session_state.show_last_preview = False
                st.rerun()

    # Main area: single chat
    for msg in st.session_state.collector.conversation_history:
        with st.chat_message(msg.get("role", "assistant")):
            st.write(msg.get("content", ""))

    user_input = None
    if st.session_state.app_state != "UPLOAD":
        user_input = st.chat_input("Enter your requirements (Logic chain will be generated automatically after confirmation)")
    else:
        st.info("Please upload a paper project archive on the left to start the conversation")
    if user_input:
        with st.spinner("Analyzing your requirements..."):
            resp = st.session_state.collector.process_user_input(user_input)
            _log(f"AI response length {len(resp)} chars")
        
        if st.session_state.collector.is_confirmed and st.session_state.app_state != "CONFIRMATION":
             st.session_state.app_state = "CONFIRMATION"
             st.session_state.auto_generate_chain = True
        st.rerun()

    if st.session_state.collector.is_confirmed and st.session_state.auto_generate_chain and not st.session_state.get("inline_chain_editor"):
        st.session_state.app_state = "CONFIRMATION" 
        
        _log("Start auto-generating logic chain (no input required)")
        req = _requirements_json()
        focus = req.get("focus_sections") or []
        dur = req.get("duration") or "5min"
        from content_tree_builder import make_tree_tools
        from chain_ai_generator import generate_chain_via_tools
        
        if "content_tree_nodes" in st.session_state:
             tools_tree = make_tree_tools(st.session_state.content_tree_nodes)
        else:
             # Fallback: re-parse if for some reason nodes are missing (e.g. reload)
             _log("Content tree nodes missing, re-parsing...")
             divider = Divider()
             target_tex = st.session_state.collector.merged_main_path or (st.session_state.collector.paper_main_tex or "")
             nodes = divider.divide(target_tex) if target_tex else []
             st.session_state.content_tree_nodes = nodes
             tools_tree = make_tree_tools(nodes)
             
        data = None
        if not data:
            try:
                with st.spinner("Generating logic chain (please wait)..."):
                    data = generate_chain_via_tools(
                        _wrap_tools(tools_tree), focus, str(dur), 
                        st.session_state.collector.paper_abstract or "",
                        conversation_history=st.session_state.collector.conversation_history
                    )
            except Exception as e:
                _log(f"Auto-generation error: {e}")
            
        from logic_chain_editor import LogicChainEditor
        editor = st.session_state.get("inline_chain_editor") or LogicChainEditor()
        if data and isinstance(data, dict):
            total_minutes = 10
            s = str(dur).lower()
            try:
                if "min" in s:
                    total_minutes = int(float(s.replace("min", "").strip()))
                elif "h" in s or "hour" in s:
                    total_minutes = int(float(s.replace("h", "").replace("hour", "").strip()) * 60)
                else:
                    total_minutes = int(float(s))
            except Exception:
                total_minutes = 10
            editor.set_from_chain_json(data, total_minutes=total_minutes)
        else:
            editor.create_from_requirements(req)
        st.session_state.inline_chain_editor = editor
        st.session_state.auto_generate_chain = False

    # Inline logic chain panel
    editor = st.session_state.get("inline_chain_editor")
    if editor and isinstance(editor, object):
        st.divider()
        # st.markdown("**Logic Chain Panel**")
        from logic_chain_editor import LogicChainUI
        
        ui = LogicChainUI(editor)
        ui.render()
        data = editor.to_dict()
        st.download_button("Export Logic Chain JSON", json.dumps(data, ensure_ascii=False, indent=2), file_name="logic_chain.json", key="download_chain_main")

        # Recommending edges button
        if "recommending_edges" not in st.session_state:
             st.session_state.recommending_edges = False
        
        has_ref_edges = any(e.get("type") == "reference" for e in editor.edges)
        
        btn_label = "Recommend Reference Edges"
        btn_disabled = False
        
        if st.session_state.recommending_edges:
             btn_label = "Generating reference edges..."
             btn_disabled = True
        elif has_ref_edges:
             btn_label = "Re-recommend Reference Edges"

        if st.button(btn_label, key="btn_recommend_edges", disabled=btn_disabled):
             st.session_state.recommending_edges = True
             st.rerun()
             
        if st.session_state.recommending_edges:
            try:
                with st.spinner("Analyzing node correlations and generating reference edges (please wait)..."):
                    from edges_recommender import EdgesRecommender
                    req = _requirements_json()
                    print(req)
                    dur = req.get("duration") or "5min"
                    from content_tree_builder import make_tree_tools
                    
                    if "content_tree_nodes" in st.session_state:
                        tools_tree = make_tree_tools(st.session_state.content_tree_nodes)
                    else:
                        tools_tree = make_tree_tools([]) # Should have nodes by now

                    node_names = [n.name for n in editor.nodes]
                    abstract_text = st.session_state.collector.paper_abstract
                    edges = st.session_state.edges_rec.recommend(node_names, abstract_text or "", tools=_wrap_tools(tools_tree))
                    if edges:
                        for e in edges:
                            e["type"] = e.get("type", "reference")
                        ui.editor.set_edges(edges)
                        st.success(f"Added {len(edges)} reference edges")
            except Exception as e:
                st.error(f"Reference edge recommendation error: {e}")
                _log(f"Reference edge recommendation error: {e}")
            finally:
                st.session_state.recommending_edges = False
                st.rerun()
                
        # --- NEW: Generate Presentation Button ---
        st.divider()
        st.header("PPT & Speech Generation")
        
        col_btn, col_set = st.columns([1, 4])
        
        with col_set:
            with st.popover("⚙️ Generation Settings"):
                st.write("Audio Settings")
                enable_tts = st.checkbox("Generate Audio (TTS)", value=True, key="enable_tts_gen")
                
                # Voice selection
                # Assuming voice files are in a known directory or hardcoded list
                # For now hardcoded list based on 'examples/voice_03.wav'
                voice_options = {
                    "Male 1": "examples/voice_03.wav",
                    "Male 2": "examples/voice_04.wav", # Hypothetical
                    "Female 1": "examples/voice_01.wav", # Hypothetical
                    "Female 2": "examples/voice_02.wav"  # Hypothetical
                }
                # Fallback to simple text input or selectbox if files not confirmed
                # Let's use a selectbox with the paths as values
                selected_voice_label = st.selectbox("Select Voice", options=list(voice_options.keys()), index=0)
                selected_voice_path = voice_options[selected_voice_label]
        
        with col_btn:
            if st.button("Start Generation", type="primary"):
                st.session_state.generating = True
                st.session_state.gen_settings = {
                    "enable_tts": enable_tts,
                    "voice_path": selected_voice_path
                }
                st.rerun()

        if st.session_state.get("generating"):
            with st.status("Generating Presentation...", expanded=True) as status:
                try:
                    status.write("Initializing Compressor...")
                    # 1. LogicFlow
                    logic_nodes = []
                    for node in editor.nodes:
                        ln = LogicNode(
                            name=node.name,
                            description=node.description or "",
                            duration=node.duration or "1 min"
                        )
                        logic_nodes.append(ln)
                    logic_flow = LogicFlow(nodes=logic_nodes)
                    
                    # 2. Compressor with Images
                    compressor = Compressor()
                    
                    # Prepare image list
                    extract_dir = st.session_state.get("extract_dir", "")
                    image_list = []
                    if extract_dir:
                        # Find images recursively in extract_dir
                        for root, dirs, files in os.walk(extract_dir):
                            for file in files:
                                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
                                    # Store relative path from extract_dir
                                    rel_path = os.path.relpath(os.path.join(root, file), extract_dir)
                                    image_list.append(rel_path)
                    
                    status.write("Compressing content and generating slides/speech (this takes time)...")
                    content_tree_nodes = st.session_state.get("content_tree_nodes", [])
                    
                    # Pass image list to compressor
                    content, speeches = compressor.compress(logic_flow, content_tree_nodes, image_list=image_list)
                    
                    status.write("Setting up compilation environment...")
                    # output_dir = os.path.join(tmp_base, "output_gen")
                    # Use a unique temporary directory for each generation to avoid conflicts
                    output_dir = os.path.join(tmp_base, f"gen_{uuid.uuid4().hex[:8]}")
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # Select and Copy base.tex using Templater
                    # from deepslide.agents.templater import Templater
                    # Templater is not in version-1 yet, assuming it's still in original place or we need to move it.
                    # User asked to move agents/combine, compiler, transformer. Templater was in agents/templater.
                    # So we should probably use absolute import or move it too?
                    # For now let's keep absolute import if it exists there.
                    try:
                        from templater import Templater
                    except ImportError:
                        # If not found, maybe just skip or use a mock
                        _log("Templater not found, skipping template selection.")
                        Templater = None
                    
                    config_dir = os.path.join(ROOT, "deepslide/config")
                    # Use existing templates and RAG embeddings
                    t_dir = os.path.join(ROOT, "template/beamer")
                    e_dir = os.path.join(ROOT, "template/rag")
                    
                    templater = Templater(
                        config_dir=config_dir,
                        embdding_dir=e_dir,
                        template_dir=t_dir
                    )
                    
                    req = _requirements_json()
                    style_pref = req.get("style_preference", "") or "professional academic"
                    
                    status.write(f"Selecting template for style: {style_pref}...")
                    selected_template = templater.select(style_pref)
                    _log(f"Selected template: {selected_template}")
                    
                    template_path = os.path.join(t_dir, selected_template, "base.tex")
                    if not os.path.exists(template_path):
                        _log(f"Template {selected_template} not found, trying default 'base'.")
                        selected_template = "base"
                        template_path = os.path.join(t_dir, "base", "base.tex")
                    
                    if os.path.exists(template_path):
                        # Copy all files from template directory to output_dir
                        for item in os.listdir(os.path.join(t_dir, selected_template)):
                            s = os.path.join(t_dir, selected_template, item)
                            d = os.path.join(output_dir, item)
                            if os.path.isfile(s):
                                shutil.copy2(s, d)
                        # shutil.copy2(template_path, os.path.join(output_dir, "base.tex"))
                        
                        # Also copy template specific pictures if any
                        tpl_pic_dir = os.path.join(t_dir, selected_template, "picture")
                        if os.path.exists(tpl_pic_dir):
                            dst_pic_dir = os.path.join(output_dir, "picture")
                            os.makedirs(dst_pic_dir, exist_ok=True)
                            for item in os.listdir(tpl_pic_dir):
                                s = os.path.join(tpl_pic_dir, item)
                                d = os.path.join(dst_pic_dir, item)
                                if os.path.isfile(s):
                                    shutil.copy2(s, d)
                    else:
                        _log("Error: Base template not found! Writing fallback.")
                        with open(os.path.join(output_dir, "base.tex"), "w") as f:
                            f.write(BASE_TEX_TEMPLATE)
                    
                    # Modify template using LLM
                    status.write("Refining template style...")
                    templater.modify(output_dir, style_pref)
                    
                    # Write title.tex
                    req = _requirements_json()
                    
                    # 1. Try to get title from extracted source
                    paper_title = extract_title_from_dir(extract_dir)
                    
                    # 2. Fallback to paper file name or default
                    if not paper_title:
                        paper_title = st.session_state.collector.paper_file_name
                        if paper_title:
                            # Remove extension
                            paper_title = os.path.splitext(paper_title)[0]
                    
                    if not paper_title:
                        paper_title = "Presentation"

                    # Sanitize title for LaTeX (escape underscores)
                    paper_title = paper_title.replace("_", r"\_")
                    
                    with open(os.path.join(output_dir, "title.tex"), "w") as f:
                        f.write(f"\\title{{{paper_title}}}\n\\author{{DeepSlide AI}}\n\\institute{{Generated by DeepSlide}}\n\\date{{\\today}}")
                     
                    # Write content.tex
                    content.to_file(os.path.join(output_dir, "content.tex"))
                    
                    # Copy images
                    # Strategy: copy the entire 'picture' folder if it exists in extract_dir
                    # Or copy all found images to a 'picture' folder in output_dir
                    picture_dir_dst = os.path.join(output_dir, "picture")
                    os.makedirs(picture_dir_dst, exist_ok=True)
                     
                    if extract_dir:
                        # Try to find a source picture dir
                        possible_names = ["picture", "figures", "images", "figs", "img"]
                        src_pic_dir = None
                        for root, dirs, files in os.walk(extract_dir):
                            for d in dirs:
                                if d.lower() in possible_names:
                                    src_pic_dir = os.path.join(root, d)
                                    break
                            if src_pic_dir: break
                    
                        if src_pic_dir:
                            # Copy contents
                            _log(f"Copying images from {src_pic_dir}")
                            for item in os.listdir(src_pic_dir):
                                s = os.path.join(src_pic_dir, item)
                                d = os.path.join(picture_dir_dst, item)
                                if os.path.isfile(s):
                                    shutil.copy2(s, d)
                        else:
                            # Fallback: copy all images found in extract_dir to picture folder (flatten)
                            _log("No specific picture folder found, flattening images...")
                            for root, dirs, files in os.walk(extract_dir):
                                for file in files:
                                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                                        shutil.copy2(os.path.join(root, file), os.path.join(picture_dir_dst, file))
                    
                    status.write("Compiling LaTeX (Compiler Agent)...")
                    MAX_COMPILE_TRY = 10
                    compiler = Compiler(max_try=MAX_COMPILE_TRY)
                    res = compiler.run(output_dir)
                    
                    if not res.get("success"):
                        st.error("Compilation failed even after fixes.")
                        _log(f"Compilation errors: {res.get('errors')}")
                        # Debug: print last errors
                        if res.get('errors'):
                            st.code(str(res.get('errors')), language="json")
                    else:
                        _log("Compilation successful.")
                    
                    # --- New Logic: Align speeches with slides (LLM Based) ---
                    try:
                        status.write("Aligning speeches with generated slides...")
                        from speech_aligner import SpeechAligner
                        aligner = SpeechAligner()
                        
                        pdf_path = os.path.join(output_dir, "base.pdf")
                        original_speeches = [str(s) for s in speeches]
                        
                        if os.path.exists(pdf_path):
                             aligned_speeches = aligner.align(pdf_path, original_speeches)
                             if aligned_speeches:
                                 speeches = aligned_speeches
                                 _log(f"Speech alignment completed. Generated {len(speeches)} segments.")
                             else:
                                 _log("Speech alignment returned empty/failed. Using original.")
                        else:
                             _log("PDF not found for alignment. Using original speeches.")
                             
                    except Exception as e:
                        _log(f"Speech alignment failed: {e}")
                        # Fallback to original speeches (or the rule-based ones if we kept that code, 
                        # but we are replacing the previous block)
                        
                    # --- End New Logic ---

                    speech_path = os.path.join(output_dir, "speech.txt")
                    # Ensure speeches are strings and joined by <next>
                    # Verify speeches is a list of strings/Spections
                    if not speeches:
                        _log("Warning: No speeches generated.")
                        speech_text = ""
                    else:
                        # Filter out empty speeches if any?
                        # The sample.txt shows lines separated by <next>
                        # app.py uses: "<next>".join([str(s) for s in speeches])
                        # We should ensure each speech segment is valid.
                        speech_segments = [str(s).strip() for s in speeches]
                        speech_text = "\n<next>\n".join(speech_segments)
                        
                    with open(speech_path, "w", encoding="utf-8") as f:
                        f.write(speech_text)
                    
                    gen_settings = st.session_state.get("gen_settings", {})
                    if gen_settings.get("enable_tts", True):
                        status.write("Generating Audio (TTS)...")
                        voice_path = gen_settings.get("voice_path", "examples/voice_03.wav")
                        run_tts(speech_text, output_dir, voice_prompt=voice_path)
                    else:
                        status.write("Skipping Audio Generation (TTS disabled).")
                    
                    st.session_state.generated_files = {
                        "pdf": os.path.join(output_dir, "base.pdf"),
                        "tex": os.path.join(output_dir, "content.tex"),
                        "speech": speech_path,
                        "audio_dir": output_dir
                    }
                    
                    # Load for preview
                    if os.path.exists(st.session_state.generated_files["pdf"]):
                        doc = fitz.open(st.session_state.generated_files["pdf"])
                        pages = []
                        for page_num in range(doc.page_count):
                            page = doc.load_page(page_num)
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            img_data = pix.tobytes("png")
                            pages.append(img_data)
                        st.session_state.preview_state["pdf_pages"] = pages
                        doc.close()
                        
                    st.session_state.preview_state["speech_segments"] = [str(s) for s in speeches]
                    
                    status.update(label="Generation Completed!", state="complete")
                    
                except Exception as e:
                    st.error(f"Error during generation: {e}")
                    _log(f"Error during generation: {e}")
                    import traceback
                    traceback.print_exc()
                    status.update(label="Generation Failed", state="error")
                finally:
                    st.session_state.generating = False

        if "generated_files" in st.session_state:
             st.divider()
             st.header("Preview & Download")
             
             files = st.session_state.generated_files
             c1, c2 = st.columns(2)
             with c1:
                 if os.path.exists(files["pdf"]):
                     with open(files["pdf"], "rb") as f:
                        st.download_button("Download PDF", f.read(), "presentation.pdf", mime="application/pdf")
                 else:
                     st.warning("PDF not generated.")
                     
             with c2:
                 with open(files["tex"], "r") as f:
                     st.download_button("Download Content TeX", f.read(), "content.tex")

    # Preview UI
    render_preview_ui()

if __name__ == "__main__":
    main()
