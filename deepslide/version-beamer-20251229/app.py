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
import requests
import io
from PIL import Image

# global tool logs
TOOL_LOGS: list[str] = []

# --- Helper Functions ---

def extract_frame_by_index(tex_content, frame_index):
    """Extract the N-th frame from the LaTeX content."""
    matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', tex_content, re.DOTALL))
    if 0 <= frame_index < len(matches):
        return matches[frame_index].group(1), matches[frame_index].span()
    return None, None

def replace_frame_in_content(tex_content, frame_index, new_frame_content):
    """Replace the N-th frame with new content."""
    match, span = extract_frame_by_index(tex_content, frame_index)
    if match and span:
        start, end = span
        return tex_content[:start] + new_frame_content + tex_content[end:]
    return tex_content

def parse_resp_frame(response_text):
    """Extract LaTeX code from LLM response."""
    match = re.search(r'```latex(.*?)```', response_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r'```(.*?)```', response_text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        if "\\begin{frame}" in content or "\\item" in content:
            return content
    if "\\begin{frame}" in response_text:
        return response_text.strip()
    return None

# --- Path Setup ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from ppt_requirements_collector import PPTRequirementsCollector
from project_analyzer import (
    save_uploaded_file, extract_archive, find_main_tex,
    merge_project_to_main, extract_abstract_from_dir, extract_title_from_dir
)
from divider import Divider
from compiler import Compiler

try:
    from compressor import Compressor
    from data_types import LogicFlow, LogicNode
except ImportError:
    pass

# --- State Init ---

def _init_state() -> None:
    if "collector" not in st.session_state:
        from ppt_requirements_collector import PPTRequirementsCollector
        st.session_state.collector = PPTRequirementsCollector()
    if "uploaded" not in st.session_state:
        st.session_state.uploaded = False
    if "app_state" not in st.session_state:
        st.session_state.app_state = "UPLOAD"
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
    if "workflow_phase" not in st.session_state:
        st.session_state.workflow_phase = "EDITING"

def _wrap_tools(tools):
    wrapped = []
    import datetime
    import json
    import functools
    
    cache: dict[tuple, str] = {}
    per_tool_counts: dict[str, int] = {}
    total_count: int = 0
    PER_TOOL_LIMIT = 5
    TOTAL_LIMIT = 20
    
    def make_wrapper(fn):
        name = getattr(fn, "__name__", "tool")
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                TOOL_LOGS.append(f"[{ts}] call {name} args={args} kwargs={kwargs}")
                nonlocal total_count
                k = (name, json.dumps(args, ensure_ascii=False, default=str), json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str))
                cnt = per_tool_counts.get(name, 0)
                
                if k in cache:
                    out = cache[k]
                    TOOL_LOGS.append(f"[{ts}] ret {name} (cached)")
                    return out
                if cnt >= PER_TOOL_LIMIT or total_count >= TOTAL_LIMIT:
                    out = "Tool budget exhausted"
                    TOOL_LOGS.append(f"[{ts}] ret {name} (budget)")
                    cache[k] = out
                    return out
                
                out = fn(*args, **kwargs)
                TOOL_LOGS.append(f"[{ts}] ret {name} -> {str(out)[:100]}...")
                per_tool_counts[name] = cnt + 1
                total_count += 1
                cache[k] = out if isinstance(out, str) else str(out)
                return out
            except Exception as e:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                TOOL_LOGS.append(f"[{ts}] error {name}: {e}")
                raise
        return wrapper
    for fn in tools:
        wrapped.append(make_wrapper(fn))
    return wrapped

def _log(msg: str) -> None:
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    TOOL_LOGS.append(f"[{ts}] {msg}")

def _requirements_json() -> Dict[str, Any]:
    override = st.session_state.get("requirements_override")
    if override: return override
    req = st.session_state.collector.get_requirements()
    return req.get("conversation_requirements") or {}

def transcribe_audio(audio_path: str) -> str:
    try:
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks
        _log(f"Starting ASR for {audio_path}")
        
        # 1. Check file existence and size
        if not os.path.exists(audio_path):
             _log(f"ASR Error: File not found: {audio_path}")
             return ""
        size = os.path.getsize(audio_path)
        _log(f"Audio file size: {size} bytes")
        if size < 100: # Too small
             _log("ASR Warning: Audio file too small (likely empty recording).")
             return ""

        model_spec = st.session_state.get("asr_model_path", 'damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch')
        inference_pipeline = pipeline(task=Tasks.auto_speech_recognition, model=model_spec)
        
        # 2. Run inference with error catch
        try:
            # Try positional argument first (common for newer funasr/modelscope)
            rec_result = inference_pipeline(audio_path)
        except TypeError as e:
            _log(f"ASR Pipeline Positional Arg Failed: {e}")
            try:
                # Fallback to audio_input kwarg
                rec_result = inference_pipeline(audio_input=audio_path)
            except Exception as e2:
                _log(f"ASR Pipeline audio_input Kwarg Failed: {e2}")
                try:
                    # Fallback to input kwarg
                    rec_result = inference_pipeline(input=audio_path)
                except Exception as e3:
                    _log(f"ASR Pipeline input Kwarg Failed: {e3}")
                    raise e3
        except Exception as pipe_e:
            _log(f"ASR Pipeline Error: {pipe_e}")
            import traceback
            _log(traceback.format_exc())
            return ""
             
        _log(f"ASR Result Raw: {rec_result} (Type: {type(rec_result)})")
        
        # 3. Parse result
        text = ""
        if isinstance(rec_result, dict):
            text = rec_result.get('text', '')
        elif isinstance(rec_result, list) and len(rec_result) > 0:
            # Sometimes it returns a list of dicts
            item = rec_result[0]
            if isinstance(item, dict):
                text = item.get('text', '')
            else:
                text = str(item)
        else:
            text = str(rec_result)
            
        return text.strip()
    except Exception as e:
        _log(f"STT Error: {e}")
        import traceback
        _log(traceback.format_exc())
        return ""

def _stt_available() -> bool:
    try:
        import modelscope
        return True
    except Exception:
        return False

def ensure_asr_model_ready() -> bool:
    try:
        if not _stt_available():
            return False
        from modelscope.hub.snapshot_download import snapshot_download
        model_id = 'damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch'
        cache_dir = os.path.join(ROOT, "local_llm_server", "models")
        target_dir = os.path.join(cache_dir, model_id)
        if os.path.exists(target_dir):
            path = target_dir
            _log(f"ASR model found locally at {path}")
        else:
            os.makedirs(cache_dir, exist_ok=True)
            path = snapshot_download(model_id, cache_dir=cache_dir)
        st.session_state.asr_model_path = path
        _log(f"ASR model ready at {path}")
        return True
    except Exception as e:
        _log(f"ASR model ensure failed: {e}")
        return False
def run_tts(speech_text: str, output_dir: str, voice_prompt: str = 'examples/voice_03.wav'):
    import subprocess
    os.makedirs(output_dir, exist_ok=True)
    sample_file = os.path.join(output_dir, "speech_script.txt")
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write(speech_text)
    index_tts_dir = os.path.join(ROOT, "index-tts/index-tts-main")
    
    python_logic = f"""
import os, sys
try:
    from indextts.infer_v2 import IndexTTS2
    from tqdm import tqdm
except ImportError:
    sys.exit(1)
os.environ['USE_MODELSCOPE'] = '1'
try:
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
except:
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False, device='cpu')

with open('{sample_file}', 'r', encoding='utf-8') as f:
    sample_text = f.read().split('<next>')

for i, text in tqdm(enumerate(sample_text)):
    text = text.strip().replace("<add>", "").strip()
    if not text: continue
    output_path = os.path.join('{output_dir}', f'{{i+1}}.wav')
    try:
        tts.infer(spk_audio_prompt='{voice_prompt}', text=text, output_path=output_path, verbose=True)
    except: pass
"""
    try:
        _log(f"Starting TTS generation in {index_tts_dir}")
        cmd = ["uv", "run", "python", "-c", python_logic]
        subprocess.run(cmd, cwd=index_tts_dir, check=False)
        _log("TTS Generation completed.")
    except Exception as e:
        _log(f"TTS Execution Error: {e}")

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
    if "preview_state" not in st.session_state: return
    state = st.session_state.preview_state
    pages = state.get("pdf_pages", [])
    speeches = state.get("speech_segments", [])
    
    if not pages: return

    st.subheader("Presentation Preview")
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    if "current_page" not in state: state["current_page"] = 0
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
        st.image(pages[state["current_page"]], width=None) # use_column_width deprecated
    with col_disp2:
        speech_idx = state["current_page"]
        if 0 <= speech_idx < len(speeches):
            display_text = speeches[speech_idx].replace("<add>", "").strip()
            
            # Show text area in editing phase if possible, but here we are in preview/common UI.
            # However, user wants "Preview in subsequent stages to be the same".
            # If we are in PREVIEW phase, this is the main view.
            # If we are in EDITING phase, this `render_preview_ui` is NOT used!
            # Wait, `render_page_ppt_editor` implements its OWN preview UI (lines 587-603).
            # And `render_page_ppt_preview` calls `render_preview_ui`.
            
            # User requirement 2: "In subsequent preview phase also have same preview."
            # The user pointed to `render_preview_ui` (L246-285).
            # And wants speech preview.
            # Currently `render_preview_ui` DOES have speech preview (L271-277).
            
            # But maybe the user meant the `render_page_ppt_editor`'s preview is missing speech?
            # Let's check `render_page_ppt_editor` (L587-603).
            # Yes, it only shows `st.image`.
            
            # So I should update `render_page_ppt_editor` to include speech preview like `render_preview_ui`.
            # BUT, `render_page_ppt_editor` already has speech EDITOR on the right side tabs.
            # "In edit mode, there should also be an edit window (already exists)".
            
            # So the user wants the `render_preview_ui` (used in PREVIEW phase) to show speech (it does).
            # And `render_page_ppt_editor` (EDIT phase) to show speech?
            # Actually, `render_page_ppt_editor` has a "Visual Preview" column (L587) and "Editors" column (L605).
            # The "Visual Preview" column currently ONLY shows the image.
            # Maybe the user wants the speech TEXT displayed below the image in the Visual Preview column too?
            # Or maybe just ensuring the "Preview Phase" uses `render_preview_ui` (it does).
            
            # Let's look at the instruction again:
            # "Study ... render_preview_ui ..., add speech preview in ... version-beamer-20251229"
            # "In subsequent preview phase also have same preview."
            # "But in edit mode also have edit window (already exists)."
            
            # It seems `render_preview_ui` is ALREADY correct for Preview Phase.
            # Maybe the user wants `render_page_ppt_editor`'s preview column to ALSO use `render_preview_ui` layout?
            # But `render_page_ppt_editor` needs to fit editors on the right.
            # `render_preview_ui` takes full width and splits 2:1.
            
            # Let's stick to the request: "Add speech preview".
            # I will add the speech text display to `render_preview_ui` (it is already there?).
            # Wait, I am reading the file content.
            # Lines 271-277:
            # with col_disp2:
            #    speech_idx = state["current_page"]
            #    if 0 <= speech_idx < len(speeches):
            #        display_text = ...
            #        st.markdown(f"**Speech Script:**\n\n{display_text}")
            
            # It IS there.
            # Perhaps the user thinks it's missing because they are looking at `render_page_ppt_editor` which DOES NOT use this function.
            # The user selected lines 320-369 in `version-beamer/app.py` (OLD file).
            # And wants to add speech preview in `version-beamer-20251229` (NEW file).
            
            # In `version-beamer/app.py` (the reference), `render_preview_ui` likely had speech.
            # In my NEW file `version-beamer-20251229/app.py`, `render_preview_ui` ALSO has it.
            
            # However, `render_page_ppt_editor` in the NEW file (L587) manually implements the preview:
            # st.image(pages[...])
            # It does NOT show the speech text in the left column.
            # I should add speech text display below the image in `render_page_ppt_editor`.
            
            st.markdown(f"**Speech Script:**\n\n{display_text}")
        else:
            st.info("No speech script available.")
            
    if "generated_files" in st.session_state:
        audio_dir = st.session_state.generated_files.get("audio_dir")
        if audio_dir:
            wav_path = os.path.join(audio_dir, f"{state['current_page']+1}.wav")
            if os.path.exists(wav_path):
                 st.audio(wav_path, format="audio/wav")

def process_slide_modification(instruction):
    """Handle chat-based slide modification."""
    page_idx = st.session_state.preview_state.get("current_page", 0)
    frame_idx = page_idx - 1
    if frame_idx < 0:
        st.warning("Cannot modify Title Page via chat yet.")
        return
    tex_path = st.session_state.generated_files["tex"]
    if not os.path.exists(tex_path):
        st.error("TeX file missing.")
        return
    with open(tex_path, "r") as f: full_tex = f.read()
    target_frame, _ = extract_frame_by_index(full_tex, frame_idx)
    if not target_frame:
        st.error(f"Frame {frame_idx} not found.")
        return

    system_prompt = "You are a LaTeX Beamer expert. Modify the content based on instruction. Return ONLY the modified \\begin{frame}...\\end{frame} block in ```latex```. Avoid using '&' symbol in text, use 'and' instead."
    full_prompt = f"Original LaTeX:\n```latex\n{target_frame}\n```\n\nInstruction: {instruction}"
    
    try:
        resp = st.session_state.collector.camel_client.get_response(full_prompt, system_prompt=system_prompt)
        new_frame = parse_resp_frame(resp)
        if new_frame:
             new_full_tex = replace_frame_in_content(full_tex, frame_idx, new_frame)
             with open(tex_path, "w") as f: f.write(new_full_tex)
             output_dir = os.path.dirname(tex_path)
             compiler = Compiler()
             res = compiler.run(output_dir)
             if res.get("success"):
                 st.success("Slide updated!")
                 pdf_path = st.session_state.generated_files["pdf"]
                 if os.path.exists(pdf_path):
                     doc = fitz.open(pdf_path)
                     new_pages = []
                     for pn in range(doc.page_count):
                         page = doc.load_page(pn)
                         pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                         new_pages.append(pix.tobytes("png"))
                     st.session_state.preview_state["pdf_pages"] = new_pages
                     doc.close()
                 st.rerun()
             else:
                 st.error(f"Compilation failed: {res.get('errors')}")
        else:
             st.error("AI did not return valid LaTeX.")
    except Exception as e:
        st.error(f"Error: {e}")

def render_sidebar_logs():
    with st.sidebar:
        with st.expander("🛠 Tool Calls & Logs", expanded=False):
            st.text("\n".join(TOOL_LOGS[-20:]))
            if st.button("Clear Logs"):
                TOOL_LOGS.clear()
                st.rerun()

# --- Page 1: Requirements ---
def render_page_requirements(tmp_base):
    st.title("Requirements Collection")
    
    if not st.session_state.uploaded:
        st.write("Please upload your paper project archive to begin.")
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
                    
                    from paper_tools import make_paper_tools
                    from content_tree_builder import make_tree_tools
                    tools = make_paper_tools(extract_dir, merged_path or "") + make_tree_tools(nodes)
                    st.session_state.collector.camel_client.set_tools(_wrap_tools(tools))
                    
                    if abstract_text:
                        st.session_state.collector.conversation_history.append({"role": "assistant", "content": f"Abstract detected:\n{abstract_text}"})
                    st.session_state.collector.conversation_history.append({"role": "assistant", "content": "To get started, please tell me the following basic information:\n- Who is the audience?\n- Presentation duration?\n- Which chapters do you want to highlight?\n- Style preference?"})
                    
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
        
        with bottom_box:
            # 1. Audio Input Row with Clone Button
            c_audio, c_transcribe, c_btn = st.columns([4, 1, 1])
            with c_audio:
                audio_value = st.audio_input("Record Voice", key="req_audio")
            with c_transcribe:
                # Manual transcribe button
                if st.button("Transcribe", help="Transcribe to Text", key="btn_transcribe_req"):
                    if "last_req_audio_path" in st.session_state:
                        v_path = st.session_state.last_req_audio_path
                        with st.spinner("Transcribing..."):
                            text = transcribe_audio(v_path)
                            _log(f"Transcribed text: '{text}'")
                        if text:
                            st.session_state.draft_input = text
                            # st.toast(f"Recognized: {text[:5]}...")
                        else:
                            st.warning("No text recognized.")
                    else:
                         st.toast("⚠️ No audio recorded.")
            with c_btn:
                # Small button for saving clone voice, only enabled if audio exists
                # Since st.audio_input triggers rerun, we check session state path
                if st.button("Save Voice", help="Save as Cloned Voice", key="btn_save_clone"):
                    if "last_req_audio_path" in st.session_state:
                         st.session_state.cloned_voice_path = st.session_state.last_req_audio_path
                         st.session_state.selected_voice_path = st.session_state.last_req_audio_path
                         st.toast("✅ Voice saved as Cloned Voice!")
                    else:
                         st.toast("⚠️ No audio recorded to save.")

            # Process Audio (Only save, do not auto transcribe)
            if audio_value:
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
                user_text = st.text_area("Requirements", value=draft_text, height=100, label_visibility="collapsed", placeholder="Enter requirements...")
                c_submit, c_clear = st.columns([1, 6])
                with c_submit:
                    submitted = st.form_submit_button("➤ Send")
            
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

# --- Page 2: Logic Chain ---
def render_page_logic_chain(tmp_base):
    st.title("Logic Chain Design")
    
    if st.session_state.auto_generate_chain and not st.session_state.get("inline_chain_editor"):
        # with st.spinner("Generating logic chain..."):
        req = _requirements_json()
        from content_tree_builder import make_tree_tools
        from chain_ai_generator import generate_chain_via_tools
        tools = make_tree_tools(st.session_state.content_tree_nodes)
        data = generate_chain_via_tools(_wrap_tools(tools), req.get("focus_sections", []), str(req.get("duration", "5min")), st.session_state.collector.paper_abstract or "", conversation_history=st.session_state.collector.conversation_history)
        
        from logic_chain_editor import LogicChainEditor
        editor = LogicChainEditor()
        if data: editor.set_from_chain_json(data)
        else: editor.create_from_requirements(req)
        st.session_state.inline_chain_editor = editor
        st.session_state.auto_generate_chain = False

    editor = st.session_state.get("inline_chain_editor")
    if editor:
        from logic_chain_editor import LogicChainUI
        ui = LogicChainUI(editor)
        ui.render()
        
        # Recommender
        if st.button("Recommend Reference Edges"):
            # with st.spinner("Analyzing..."):
            from edges_recommender import EdgesRecommender
            from content_tree_builder import make_tree_tools
            tools = make_tree_tools(st.session_state.content_tree_nodes)
            edges = st.session_state.edges_rec.recommend([n.name for n in editor.nodes], st.session_state.collector.paper_abstract, _wrap_tools(tools))
            if edges: ui.editor.set_edges(edges)
            st.rerun()

        st.divider()
        st.header("Generation")
        
        c1, c2 = st.columns([1, 4])
        # with c2:
        #     st.info("The PPT will be generated first. You can select voice settings in the next editing phase.")
            
        with c1:
            if st.button("Start PPT Generation", type="primary"):
                st.session_state.generating = True
                st.rerun()

    if st.session_state.get("generating"):
        with st.status("Generating...", expanded=False) as status:
            try:
                # 1. LogicFlow
                logic_nodes = [LogicNode(name=n.name, description=n.description, duration=n.duration) for n in editor.nodes]
                logic_flow = LogicFlow(nodes=logic_nodes)
                
                # 2. Compressor
                compressor = Compressor()
                extract_dir = st.session_state.get("extract_dir", "")
                img_list = []
                if extract_dir:
                    for r, d, f in os.walk(extract_dir):
                        for file in f:
                            if file.lower().endswith(('.png', '.jpg', '.pdf')):
                                img_list.append(os.path.relpath(os.path.join(r, file), extract_dir))
                
                # status.write("Compressing...")
                content, speeches = compressor.compress(logic_flow, st.session_state.get("content_tree_nodes", []), image_list=img_list)
                
                # 3. Output
                output_dir = os.path.join(tmp_base, f"gen_{uuid.uuid4().hex[:8]}")
                os.makedirs(output_dir, exist_ok=True)
                
                # 4. Template
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

                # 5. Title & Content
                with open(os.path.join(output_dir, "title.tex"), "w") as f:
                    f.write(f"\\title{{{st.session_state.collector.paper_file_name}}}\\author{{DeepSlide}}\\date{{\\today}}")
                content.to_file(os.path.join(output_dir, "content.tex"))
                
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
                c = Compiler()
                res = c.run(output_dir)
                if not res.get("success"): st.error(f"Compile Error: {res.get('errors')}")
                
                # 8. Speech Align
                try:
                    from speech_aligner import SpeechAligner
                    aligner = SpeechAligner()
                    pdf = os.path.join(output_dir, "base.pdf")
                    if os.path.exists(pdf):
                        aligned = aligner.align(pdf, [str(s) for s in speeches])
                        if aligned: speeches = aligned
                except: pass
                
                sp_txt = "\n<next>\n".join([str(s).strip() for s in speeches])
                with open(os.path.join(output_dir, "speech.txt"), "w") as f: f.write(sp_txt)
                
                st.session_state.generated_files = {
                    "pdf": os.path.join(output_dir, "base.pdf"),
                    "tex": os.path.join(output_dir, "content.tex"),
                    "speech": os.path.join(output_dir, "speech.txt"),
                    "audio_dir": output_dir
                }
                
                # Load preview
                if os.path.exists(st.session_state.generated_files["pdf"]):
                     doc = fitz.open(st.session_state.generated_files["pdf"])
                     st.session_state.preview_state["pdf_pages"] = [doc.load_page(i).get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png") for i in range(doc.page_count)]
                     doc.close()
                st.session_state.preview_state["speech_segments"] = [str(s) for s in speeches]
                st.session_state.workflow_phase = "EDITING"
                st.rerun()

            except Exception as e:
                st.error(f"Gen Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                st.session_state.generating = False

# --- Page 3: Editor ---
def render_page_ppt_editor(tmp_base):
    st.title("PPT Editor")
    files = st.session_state.generated_files
    
    # Ensure we are in EDITING phase if this function is called
    # st.header("📝 Edit Phase")
    # st.info("Modify slides/speech. Preview is visual only.")
    
    c_l, c_r = st.columns([1, 1])
    with c_l:
        st.subheader("Visual Preview")
        pages = st.session_state.preview_state.get("pdf_pages", [])
        if pages:
            curr = st.session_state.preview_state.get("current_page", 0)
            cn1, cn2, cn3 = st.columns([1,2,1])
            with cn1: 
                if st.button("◀", key="ed_prev"):
                    st.session_state.preview_state["current_page"] = max(0, curr - 1)
                    st.rerun()
            with cn3:
                if st.button("▶", key="ed_next"):
                    st.session_state.preview_state["current_page"] = min(len(pages)-1, curr + 1)
                    st.rerun()
            with cn2: st.caption(f"{curr+1}/{len(pages)}")
            st.image(pages[st.session_state.preview_state["current_page"]], width=None)
            
            # Show speech preview below image
            speeches = st.session_state.preview_state.get("speech_segments", [])
            speech_idx = st.session_state.preview_state["current_page"]
            if 0 <= speech_idx < len(speeches):
                 display_text = speeches[speech_idx].replace("<add>", "").strip()
                 with st.expander("Speech Preview", expanded=True):
                     st.caption(display_text)
    
    with c_r:
        st.subheader("Editors")
        tabs = st.tabs(["Content", "Speech", "Title", "Base", "Audio & Voice"])
        
        # Load extra files
        title_path = os.path.join(os.path.dirname(files["tex"]), "title.tex")
        base_path = os.path.join(os.path.dirname(files["tex"]), "base.tex")
        
        with tabs[0]:
            with open(files["tex"], "r") as f: c_tex = f.read()
            n_tex = st.text_area("content.tex", c_tex, height=400)
        with tabs[1]:
            with open(files["speech"], "r") as f: s_txt = f.read()
            n_sp = st.text_area("speech.txt", s_txt, height=400)
        with tabs[2]:
            if os.path.exists(title_path):
                with open(title_path, "r") as f: t_tex = f.read()
                n_title = st.text_area("title.tex", t_tex, height=400)
            else:
                st.warning("title.tex not found")
                n_title = ""
        with tabs[3]:
            if os.path.exists(base_path):
                with open(base_path, "r") as f: b_tex = f.read()
                n_base = st.text_area("base.tex", b_tex, height=400)
            else:
                st.warning("base.tex not found")
                n_base = ""
        with tabs[4]:
            st.write("**Voice Settings**")
            
            # Voice Selection Logic (Same as Logic Chain page)
            # Filter to only keep voice_03 and cloned voice
            voice_opts = {"Default Voice": "examples/voice_03.wav"}
            if st.session_state.get("cloned_voice_path"):
                voice_opts["🎤 Cloned Voice"] = st.session_state.get("cloned_voice_path")
            
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
            st.write("**Clone Voice**")
            # st.info("Record a short audio clip to clone your voice.")
            clone_audio = st.audio_input("Record for Cloning", key="ed_clone_audio")
            if clone_audio:
                # Save new clone
                c_path = os.path.join(tmp_base, f"cloned_{uuid.uuid4().hex[:6]}.wav")
                with open(c_path, "wb") as f:
                    f.write(clone_audio.read())
                
                if st.button("💾 Save as New Cloned Voice"):
                    st.session_state.cloned_voice_path = c_path
                    st.session_state.selected_voice_path = c_path
                    st.success("Cloned voice updated and selected!")
                    st.rerun()
    
    # st.divider()
    c_a1, c_a2 = st.columns(2)
    with c_a1:
        if st.button("🔄 Save & Update Preview"):
            with open(files["tex"], "w") as f: f.write(n_tex)
            with open(files["speech"], "w") as f: f.write(n_sp)
            if n_title:
                with open(title_path, "w") as f: f.write(n_title)
            if n_base:
                with open(base_path, "w") as f: f.write(n_base)
            
            c = Compiler()
            if c.run(os.path.dirname(files["tex"])).get("success"):
                st.success("Updated")
                doc = fitz.open(files["pdf"])
                st.session_state.preview_state["pdf_pages"] = [doc.load_page(i).get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png") for i in range(doc.page_count)]
                doc.close()
                st.rerun()
    with c_a2:
        if st.button("✅ Finish & Enter Preview"):
            with open(files["tex"], "w") as f: f.write(n_tex)
            with open(files["speech"], "w") as f: f.write(n_sp)
            if n_title:
                with open(title_path, "w") as f: f.write(n_title)
            if n_base:
                with open(base_path, "w") as f: f.write(n_base)
            
            c = Compiler()
            if c.run(os.path.dirname(files["tex"])).get("success"):
                with st.spinner("Generating Audio..."):
                    # Use selected voice or default to examples/voice_03.wav
                    # If user recorded a cloned voice earlier, it should be in selected_voice_path if they selected it
                    voice_p = st.session_state.get("selected_voice_path", "examples/voice_03.wav")
                    run_tts(n_sp, files["audio_dir"], voice_p)
                st.session_state.workflow_phase = "PREVIEW"
                st.rerun()

    # Bottom Input for Edit
    try: bottom_box = st.bottom_container()
    except: bottom_box = st.container()
    with bottom_box:
        audio_value = st.audio_input("Record Command", key="ed_audio")
        if audio_value:
            v_tmp_path = os.path.join(tmp_base, f"voice_{uuid.uuid4().hex[:6]}.wav")
            with open(v_tmp_path, "wb") as f: f.write(audio_value.read())
            text = transcribe_audio(v_tmp_path)
            if text:
                st.session_state.last_ed_voice = text
                st.success("Transcribed!")
        
        chat_val = st.chat_input("Modify slide...")
        final = chat_val
        if not final and "last_ed_voice" in st.session_state:
            if st.button("Exec Voice Cmd"):
                final = st.session_state.last_ed_voice
                del st.session_state["last_ed_voice"]
        
        if final:
            with st.spinner("Modifying..."):
                process_slide_modification(final)

# --- Page 4: Preview ---
def render_page_ppt_preview(tmp_base):
    st.title("PPT Preview")
    files = st.session_state.generated_files
    
    st.header("📺 Preview & Play")
    c_d1, c_d2, c_d3 = st.columns(3)
    with c_d1:
        with open(files["pdf"], "rb") as f: st.download_button("Download PDF", f.read(), "presentation.pdf")
    with c_d3:
        if st.button("🔙 Back to Editing"):
            st.session_state.workflow_phase = "EDITING"
            st.rerun()
    render_preview_ui()

def main():
    st.set_page_config(page_title="DeepSlide", layout="wide")
    _init_state()
    ensure_asr_model_ready()
    render_sidebar_logs()
    
    tmp_base = os.path.join(ROOT, "deepslide/tmp_uploads")
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
