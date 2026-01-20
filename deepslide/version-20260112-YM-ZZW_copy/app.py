import streamlit as st
import streamlit.components.v1 as components
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
import tempfile


def _components_html(body: str, height: int | None = None, scrolling: bool = True, key: str | None = None):
    try:
        # If height is None, Streamlit components.html might default to something small or fixed.
        # But if we want auto-height, we usually rely on iframe resizing which is tricky in Streamlit.
        # However, for components.html, height is optional but defaults to 150 if not set.
        # We can try passing None if the API supports it, or handle it.
        # Streamlit's components.html signature: (html, width=None, height=None, scrolling=False)
        # So passing height=None lets Streamlit decide (usually 150).
        
        # To support dynamic height without hardcoding, we can inject a script that posts a message with the height,
        # but Streamlit doesn't support receiving it easily to resize the iframe.
        # So typically we HAVE TO specify a height for the iframe.
        
        # A common workaround is to use a large default or let the caller specify.
        # If the user wants to avoid hardcoding 1200 at the call site, we can use a constant or a calculation?
        # But here we are just wrapping the call.
        
        # The user asked "Can we not use hardcoding?". 
        # In the context of the call site: _components_html(html_viz, height=1200, ...)
        # We can parse the height from the HTML style if possible, or use a JS resizing trick.
        
        # Let's try to make the iframe resize itself using JS (Streamlit Streamlit.setComponentValue equivalent?)
        # components.html creates a sandboxed iframe. It can't easily resize its parent container.
        
        # BEST PRACTICE for Streamlit: Just use a sufficient height. 
        # BUT if we want to avoid "magic number 1200" at the call site, we can define a constant based on the CSS in _render_vis_network.
        
        kwargs = {"scrolling": scrolling}
        if height is not None:
            kwargs["height"] = height
        if key is not None:
            kwargs["key"] = key
            
        return components.html(body, **kwargs)
    except TypeError:
        return components.html(body, height=height, scrolling=scrolling)

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

def parse_resp_for_editor(response_text):
    """Extract LaTeX code from response for editor use."""
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

def _pick_writable_tmp_dir(preferred_dir: str) -> str:
    """Pick a writable directory for uploads.

    Prefer the project-scoped tmp dir, but fall back to system/user tmp if the
    workspace directory is not writable (common when running as a different user).
    """
    import tempfile
    import uuid

    candidates = [
        preferred_dir,
        os.path.join(tempfile.gettempdir(), "deepslide_uploads"),
        os.path.join(os.path.expanduser("~"), ".cache", "deepslide_uploads"),
    ]

    for d in candidates:
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, f".write_probe_{uuid.uuid4().hex}")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            continue

    return preferred_dir

from ppt_requirements_collector import PPTRequirementsCollector
from project_analyzer import (
    save_uploaded_file, extract_archive, find_main_tex,
    merge_project_to_main, extract_abstract_from_dir, extract_title_from_dir,
    find_main_md, convert_md_to_tex, find_main_docx, convert_docx_to_tex
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
                TOOL_LOGS.append(f"[{ts}] ret {name} -> {str(out)[:min(100, len(str(out)))]}...")
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
    log_msg = f"[{ts}] {msg}"
    TOOL_LOGS.append(log_msg)
    print(log_msg)  # Also print to terminal for debugging

def _requirements_json() -> Dict[str, Any]:
    override = st.session_state.get("requirements_override")
    if override: return override
    req = st.session_state.collector.get_requirements()
    return req.get("conversation_requirements") or {}

def transcribe_audio(audio_path: str) -> str:
    try:
        import dashscope
        from dotenv import load_dotenv
        
        # Load env
        env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            
        api_key = os.getenv("DEFAULT_ASR_API_KEY")
        if not api_key:
            _log("ASR Error: DASHSCOPE_API_KEY not found in env.")
            return ""

        _log(f"Starting ASR (API) for {audio_path}")
        
        # 1. Check file
        if not os.path.exists(audio_path):
             _log(f"ASR Error: File not found: {audio_path}")
             return ""
        size = os.path.getsize(audio_path)
        if size < 100:
             _log("ASR Warning: Audio file too small.")
             return ""

        # 2. Call DashScope API
        # dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
        api_url = os.getenv("DEFAULT_ASR_API_URL")
        if not api_url:
            _log("ASR Error: DEFAULT_ASR_API_URL not found in env.")
            return ""
        dashscope.base_http_api_url = api_url
        
        # Use file:// protocol for local files
        local_file_url = f"file://{os.path.abspath(audio_path)}"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"audio": local_file_url}
                ]
            }
        ]
        
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model="qwen3-asr-flash", # As requested
            messages=messages,
            result_format="message",
            asr_options={
                "enable_itn": False
            }
        )
        
        _log(f"ASR API Response: {response}")

        if response.status_code == 200:
            # Parse output
            try:
                # The structure usually is response.output.choices[0].message.content[0]['text'] or similar
                # Or for 'message' format: response.output.choices[0].message.content
                # Let's check the response structure from logs if it fails, but typically:
                if hasattr(response, 'output') and response.output.choices:
                    content = response.output.choices[0].message.content
                    # Content is a list of dicts for multimodal
                    if isinstance(content, list):
                        for item in content:
                            if "text" in item:
                                return item["text"]
                    # Fallback
                    return str(content)
            except Exception as parse_e:
                _log(f"ASR Parse Error: {parse_e}")
                return ""
        else:
            _log(f"ASR API Failed: {response.code} - {response.message}")
            return ""
            
    except Exception as e:
        _log(f"STT Error: {e}")
        import traceback
        _log(traceback.format_exc())
        return ""

def _stt_available() -> bool:
    try:
        import dashscope
        return True
    except ImportError:
        return False

def ensure_asr_model_ready() -> bool:
    # API based, just check if dashscope is installed and key exists
    if not _stt_available():
        _log("ASR Error: dashscope package not installed.")
        return False
    return True

def run_tts(speech_text: str, output_dir: str, voice_prompt: str = 'examples/voice_03.wav') -> bool:
    import subprocess
    from dotenv import load_dotenv

    env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
    load_dotenv(env_path)

    os.makedirs(output_dir, exist_ok=True)
    sample_file = os.path.join(output_dir, "speech_script.txt")
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write(speech_text)
    index_tts_dir = os.path.join(ROOT, "index-tts/index-tts-main")
    
    python_logic = f"""
import os, sys, traceback
try:
    from indextts.infer_v2 import IndexTTS2
    from tqdm import tqdm
except ImportError:
    print("ImportError: Failed to import IndexTTS2 or tqdm")
    sys.exit(1)
os.environ['USE_MODELSCOPE'] = '1'
try:
    print("Initializing IndexTTS2...")
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
except Exception as e:
    print(f"Failed to init GPU IndexTTS2: {{e}}")
    try:
        print("Fallback to CPU IndexTTS2...")
        tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=False, use_cuda_kernel=False, use_deepspeed=False, device='cpu')
    except Exception as e2:
        print(f"Failed to init CPU IndexTTS2: {{e2}}")
        traceback.print_exc()
        sys.exit(1)

try:
    with open('{sample_file}', 'r', encoding='utf-8') as f:
        sample_text = f.read().split('<next>')
    print(f"Loaded {{len(sample_text)}} speech segments.")
except Exception as e:
    print(f"Failed to read sample file: {{e}}")
    sys.exit(1)

for i, text in tqdm(enumerate(sample_text)):
    text = text.strip().replace("<add>", "").strip()
    if not text: continue
    output_path = os.path.join('{output_dir}', f'{{i+1}}.wav')
    print(f"Generating {{output_path}}...")
    try:
        tts.infer(spk_audio_prompt='{voice_prompt}', text=text, output_path=output_path, verbose=True)
    except Exception as e:
        print(f"Error generating {{output_path}}: {{e}}")
        traceback.print_exc()
"""
    try:
        # Locate uv
        uv_path = shutil.which("uv")
        if not uv_path:
            # Fallback for common paths
            possible_paths = ["/home/ym/anaconda3/bin/uv", "/usr/local/bin/uv", "/usr/bin/uv"]
            for p in possible_paths:
                if os.path.exists(p):
                    uv_path = p
                    break
        
        if not uv_path:
            msg = "Error: 'uv' command not found. Please install uv or ensure it's in the PATH."
            _log(msg)
            st.error(msg)
            return False

        _log(f"Starting TTS generation in {index_tts_dir} using {uv_path}")
        st.write("Running TTS inference...")
        cmd = [uv_path, "run", "python", "-c", python_logic]
        
        # Prepare env with PATH
        env = os.environ.copy()
        
        # Add the directory containing 'uv' to PATH if it's not already there
        if uv_path:
            uv_dir = os.path.dirname(uv_path)
            if uv_dir not in env.get("PATH", ""):
                env["PATH"] = f"{uv_dir}:{env.get('PATH', '')}"

        # Stream output to log and UI
        process = subprocess.Popen(
            cmd, 
            cwd=index_tts_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1,
            env=env
        )
        
        # Read output line by line
        for line in process.stdout:
            line = line.strip()
            if line:
                _log(f"TTS: {line}")
                # Optional: update status if needed, but might be too fast/noisy
                # st.write(line) 
        
        process.wait()
        
        if process.returncode == 0:
            _log("TTS Generation completed.")
            st.write("TTS Generation completed.")
            return True
        else:
            _log(f"TTS Generation failed with code {process.returncode}")
            st.error(f"TTS Generation failed with code {process.returncode}")
            return False
            
    except Exception as e:
        _log(f"TTS Execution Error: {e}")
        st.error(f"TTS Execution Error: {e}")
        return False

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

def _plan_modifications(instruction: str, allowed_actions: list, page_idx: int, speeches: list) -> list:
    """Use LLM to plan modification actions based on instruction and allowed actions."""
    
    # 1. Get Context
    current_speech = speeches[page_idx] if page_idx < len(speeches) else ""
    
    # Visual context
    current_latex = ""
    try:
        files = st.session_state.generated_files
        if page_idx == 0:
            title_path = os.path.join(os.path.dirname(files["tex"]), "title.tex")
            if os.path.exists(title_path):
                with open(title_path, "r") as f: current_latex = f.read()
        else:
            frame_idx = 0
            for i in range(page_idx):
                 if "<add>" not in speeches[i]:
                     frame_idx += 1
            if os.path.exists(files["tex"]):
                with open(files["tex"], "r") as f: full_tex = f.read()
                match, _ = extract_frame_by_index(full_tex, frame_idx)
                if match: current_latex = match
    except: pass

    # 2. Construct Prompt
    system_prompt = (
        "You are a Presentation Editor Planner. Your goal is to break down the user's modification instruction "
        "into a list of specific executable actions. "
        f"You can ONLY use the following allowed actions: {json.dumps(allowed_actions)}. "
        "Return the plan as a strictly valid JSON list of objects, where each object has:\n"
        "- 'action': One of the allowed actions.\n"
        "- 'instruction': The specific sub-instruction for that action.\n"
        "\n"
        "Example Output:\n"
        "[\n"
        "  {\"action\": \"MODIFY_SLIDE_CONTENT\", \"instruction\": \"Change the bullet point about accuracy to 99%\"},\n"
        "  {\"action\": \"MODIFY_SPEECH\", \"instruction\": \"Mention that our accuracy reached 99%\"}\n"
        "]\n"
        "If the user instruction cannot be fulfilled by allowed actions, ignore that part or return empty list."
    )
    
    user_prompt = f"""
    User Instruction: "{instruction}"
    
    Context - Current Speech:
    "{current_speech}"
    
    Context - Current Slide Content:
    ```latex
    {current_latex}
    ```
    
    Plan the modifications (JSON format only):
    """
    
    try:
        _log(f"Planning modifications for: {instruction}")
        resp = st.session_state.collector.camel_client.get_response(user_prompt, system_prompt=system_prompt)
        
        # Extract JSON from response
        match = re.search(r'\[.*\]', resp, re.DOTALL)
        if match:
            json_str = match.group(0)
            plan = json.loads(json_str)
            _log(f"Plan generated: {plan}")
            return plan
        else:
            # Fallback for simple single-intent if JSON parsing fails but text looks like intent
            _log("Plan generation failed to parse JSON. Fallback.")
            return []
    except Exception as e:
        _log(f"Planning error: {e}")
        return []

def process_slide_modification(instruction):
    """Handle chat-based slide modification with Agent Planner."""
    print(f"DEBUG: process_slide_modification instruction='{instruction}'")
    page_idx = st.session_state.preview_state.get("current_page", 0)
    
    speeches = st.session_state.preview_state.get("speech_segments", [])
    if not speeches:
        st.warning("Speech segments not available.")
        return False

    if page_idx >= len(speeches):
        st.warning("Current page index out of range.")
        return False

    current_speech = speeches[page_idx]
    is_structural = "<add>" in current_speech
    
    # 1. Determine Allowed Actions based on permissions
    allowed_actions = []
    
    # Title Page
    if page_idx == 0:
        allowed_actions = ["MODIFY_TITLE_CONTENT", "MODIFY_SPEECH"]
    # Structural (non-Title)
    elif is_structural:
        allowed_actions = ["MODIFY_SPEECH"]
    # Content Page
    else:
        allowed_actions = ["MODIFY_SLIDE_CONTENT", "MODIFY_SPEECH"]
        
    _log(f"Page {page_idx} (Structural={is_structural}) Allowed: {allowed_actions}")

    # 2. Plan Modifications
    plan = _plan_modifications(instruction, allowed_actions, page_idx, speeches)
    
    if not plan:
        st.warning("Could not understand modification instruction or no allowed actions found.")
        return False
        
    # 3. Execute Plan
    success_any = False
    for step in plan:
        action = step.get("action")
        sub_instruction = step.get("instruction")
        
        if action not in allowed_actions:
            _log(f"Skipping forbidden action: {action}")
            continue
            
        if action == "MODIFY_TITLE_CONTENT":
            if _modify_title_page(sub_instruction): success_any = True
        elif action == "MODIFY_SLIDE_CONTENT":
            if _modify_content_page(page_idx, sub_instruction, speeches): success_any = True
        elif action == "MODIFY_SPEECH":
            if _modify_speech(page_idx, sub_instruction, speeches): success_any = True
            
    if success_any:
        return True
    else:
        st.error("Modification failed or no valid actions executed.")
        return False
def _update_pdf_preview():
    pdf_path = st.session_state.generated_files["pdf"]
    if os.path.exists(pdf_path):
        try:
            output_dir = os.path.dirname(pdf_path)
            preview_dir = os.path.join(output_dir, "preview_cache")
            os.makedirs(preview_dir, exist_ok=True)
            
            import time
            timestamp = int(time.time() * 1000)
            
            doc = fitz.open(pdf_path)
            new_pages = []
            for pn in range(doc.page_count):
                page = doc.load_page(pn)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                
                img_filename = f"page_{pn}_{timestamp}.png"
                img_path = os.path.join(preview_dir, img_filename)
                pix.save(img_path)
                new_pages.append(img_path)
                
            st.session_state.preview_state["pdf_pages"] = new_pages
            doc.close()
            
            # Clean up old cache
            for f in os.listdir(preview_dir):
                if f.endswith(".png") and str(timestamp) not in f:
                    try: os.remove(os.path.join(preview_dir, f))
                    except: pass
                    
        except Exception as e:
            print(f"Preview update error: {e}")

def _modify_title_page(instruction):
    _log("Modifying Title Page Content")
    tex_path = st.session_state.generated_files["tex"]
    output_dir = os.path.dirname(tex_path)
    title_path = os.path.join(output_dir, "title.tex")
    
    if not os.path.exists(title_path):
        st.error("Title file missing.")
        return False
        
    with open(title_path, "r") as f: current_title_tex = f.read()
    
    system_prompt = "You are a LaTeX Beamer expert. Modify the title/author/date information based on instruction. Return ONLY the modified content (e.g. \\title{...}\\author{...}) in ```latex```."
    full_prompt = f"Original title.tex:\n```latex\n{current_title_tex}\n```\n\nInstruction: {instruction}"
    
    try:
        resp = st.session_state.collector.camel_client.get_response(full_prompt, system_prompt=system_prompt)
        new_title_content = parse_resp_for_editor(resp)
        if new_title_content:
             with open(title_path, "w") as f: f.write(new_title_content)
             compiler = Compiler()
             res = compiler.run(output_dir)
             if res.get("success"):
                 st.success("Title updated!")
                 _update_pdf_preview()
                 return True
             else:
                 st.error(f"Compilation failed: {res.get('errors')}")
                 return False
        else:
             st.error("AI did not return valid LaTeX for title.")
             return False
    except Exception as e:
        st.error(f"Error modifying title: {e}")
        return False

def _modify_speech(page_idx, instruction, speeches):
    _log(f"Modifying Speech (Page {page_idx+1})")
    current_speech = speeches[page_idx]
    
    system_prompt = "You are a speech editor. Modify the speech script based on instruction. Return ONLY the modified speech text."
    full_prompt = f"Original Speech:\n{current_speech}\n\nInstruction: {instruction}"
    
    try:
        resp = st.session_state.collector.camel_client.get_response(full_prompt, system_prompt=system_prompt)
        new_speech = resp.strip()
        if new_speech:
            if "<add>" in current_speech and "<add>" not in new_speech:
                new_speech = "<add> " + new_speech
            
            speeches[page_idx] = new_speech
            st.session_state.preview_state["speech_segments"] = speeches
            
            files = st.session_state.generated_files
            if "speech" in files:
                sp_txt = "\n<next>\n".join([str(s).strip() for s in speeches])
                with open(files["speech"], "w") as f: f.write(sp_txt)
            
            st.success("Speech updated!")
            return True
        else:
            st.error("AI returned empty speech.")
            return False
    except Exception as e:
        st.error(f"Error modifying speech: {e}")
        return False

def _modify_content_page(page_idx, instruction, speeches):
    frame_idx = 0
    for i in range(page_idx):
        if "<add>" not in speeches[i]:
            frame_idx += 1
            
    _log(f"Modifying Content Page {page_idx+1} -> Frame Index {frame_idx}")

    tex_path = st.session_state.generated_files["tex"]
    if not os.path.exists(tex_path):
        st.error("TeX file missing.")
        return False
    with open(tex_path, "r") as f: full_tex = f.read()
    target_frame, _ = extract_frame_by_index(full_tex, frame_idx)
    if not target_frame:
        st.error(f"Frame {frame_idx} not found.")
        return False

    system_prompt = "You are a LaTeX Beamer expert. Modify the content based on instruction. Return ONLY the modified \\begin{frame}...\\end{frame} block in ```latex```. Avoid using '&' symbol in text, use 'and' instead."
    full_prompt = f"Original LaTeX:\n```latex\n{target_frame}\n```\n\nInstruction: {instruction}"
    
    try:
        resp = st.session_state.collector.camel_client.get_response(full_prompt, system_prompt=system_prompt)
        new_frame = parse_resp_for_editor(resp)
        if new_frame:
             new_full_tex = replace_frame_in_content(full_tex, frame_idx, new_frame)
             with open(tex_path, "w") as f: f.write(new_full_tex)
             output_dir = os.path.dirname(tex_path)
             compiler = Compiler()
             res = compiler.run(output_dir)
             if res.get("success"):
                 st.success("Slide updated!")
                 _update_pdf_preview()
                 return True
             else:
                 st.error(f"Compilation failed: {res.get('errors')}")
                 return False
        else:
             st.error("AI did not return valid LaTeX.")
             return False
    except Exception as e:
        st.error(f"Error: {e}")
        return False



def _call_vlm_beautify(image_path: str, latex_code: str) -> str:
    try:
        import dashscope
        from dotenv import load_dotenv
        
        # Load env
        env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            env_path = "/home/ym/DeepSlide/deepslide/config/env/.env"
            load_dotenv(env_path)
            pass
            
        api_key = os.getenv("DEFAULT_VLM_API_KEY")
        if not api_key:
            _log("VLM Error: DEFAULT_VLM_API_KEY not found.")
            return ""
            
        api_url = os.getenv("DEFAULT_VLM_API_URL")
        if api_url:
            dashscope.base_http_api_url = api_url
            
        model_type = os.getenv("DEFAULT_VLM_TYPE", "qwen-vl-max")
            
        local_file_url = f"file://{os.path.abspath(image_path)}"
        
        prompt = (
            "You are a Presentation Design Expert. "
            "Analyze the slide image and the corresponding LaTeX code. "
            "Your tasks are:\n"
            "1. Layout: Prevent any element overlap. If the content in `latex_code` does not fully appear in the image, it means there is too much content beyond the display range, and simplification or reduction is needed. \n"
            "2. Images: Check if images are too small or too large. Resize them to fit the slide comfortably (Recommend center-align images, and try not to use too much text in image pages).\n"
            "3. Content Density: Check if the slide has too much text (cluttered) or too little (empty). Balance the whitespace.\n"
            "Suggestions:\n"
            "- Do NOT use \\Large or \\textbf manually for slide titles inside the content area. Use \\frametitle{...} or \\framesubtitle{...} instead.\n"
            "- Do NOT add any footers, signatures, e.g., 'Generated by DeepSlide' text."
            "Return ONLY the modified \\begin{frame}...\\end{frame} block in ```latex``` code block."
        )
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": local_file_url},
                    {"text": f"{prompt}\n\nCurrent LaTeX:\n```latex\n{latex_code}\n```"}
                ]
            }
        ]
        
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model=model_type,
            messages=messages,
            result_format="message"
        )
        
        if response.status_code == 200:
             if hasattr(response, 'output') and response.output.choices:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    text = ""
                    for item in content:
                        if "text" in item: text += item["text"]
                    return parse_resp_for_editor(text)
                return parse_resp_for_editor(str(content))
        else:
             _log(f"VLM Failed: {response.code} - {response.message}")
             return ""
    except Exception as e:
        _log(f"VLM Error: {e}")
        return ""
    return ""

def _ensure_local_image_path(image_path_or_bytes, tmp_dir: str) -> str:
    if isinstance(image_path_or_bytes, str) and os.path.exists(image_path_or_bytes):
        return image_path_or_bytes
    if isinstance(image_path_or_bytes, (bytes, bytearray)):
        os.makedirs(tmp_dir, exist_ok=True)
        out_path = os.path.join(tmp_dir, f"vlm_{uuid.uuid4().hex}.png")
        with open(out_path, "wb") as f:
            f.write(bytes(image_path_or_bytes))
        return out_path
    return ""

def _prepare_vlm_image_local_path(image_path_or_bytes, tmp_dir: str) -> str:
    os.makedirs(tmp_dir, exist_ok=True)
    if isinstance(image_path_or_bytes, (bytes, bytearray)):
        out_path = os.path.join(tmp_dir, f"vlm_{uuid.uuid4().hex}.png")
        with open(out_path, "wb") as f:
            f.write(bytes(image_path_or_bytes))
        return out_path

    if not isinstance(image_path_or_bytes, str):
        return ""

    src_path = image_path_or_bytes
    if not os.path.exists(src_path):
        return ""

    ext = os.path.splitext(src_path)[1].lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return src_path

    if ext == ".pdf":
        try:
            doc = fitz.open(src_path)
            if doc.page_count <= 0:
                return ""
            page = doc.load_page(0)
            pix = page.get_pixmap(alpha=False)
            out_path = os.path.join(tmp_dir, f"vlm_{uuid.uuid4().hex}.png")
            pix.save(out_path)
            return out_path
        except Exception:
            return ""

    try:
        img = Image.open(src_path)
        out_path = os.path.join(tmp_dir, f"vlm_{uuid.uuid4().hex}.png")
        img.save(out_path, format="PNG")
        return out_path
    except Exception:
        return ""

def _extract_first_json_object(text: str):
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None

def _normalize_focus_regions(regions, max_regions: int):
    if not isinstance(regions, list):
        return []
    out = []
    for r in regions:
        if not isinstance(r, dict):
            continue
        try:
            x = float(r.get("x"))
            y = float(r.get("y"))
            w = float(r.get("w"))
            h = float(r.get("h"))
        except Exception:
            continue
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.01, min(1.0, w))
        h = max(0.01, min(1.0, h))
        if x + w > 1.0:
            w = max(0.01, 1.0 - x)
        if y + h > 1.0:
            h = max(0.01, 1.0 - y)
        out.append({
            "x": round(x, 6),
            "y": round(y, 6),
            "w": round(w, 6),
            "h": round(h, 6),
            "label": str(r.get("label", ""))[:80]
        })
        if len(out) >= max_regions:
            break
    return out

def _call_vlm_focus_regions(slide_image_path_or_bytes, speech_text: str, max_regions: int = 5):
    try:
        import dashscope
        from dotenv import load_dotenv

        env_path = os.path.join(os.path.dirname(__file__), '../config/env/.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            env_path = "/home/ym/DeepSlide/deepslide/config/env/.env"
            load_dotenv(env_path)

        api_key = os.getenv("DEFAULT_VLM_API_KEY")
        if not api_key:
            _log("VLM Error: DEFAULT_VLM_API_KEY not found.")
            return []

        api_url = os.getenv("DEFAULT_VLM_API_URL")
        if api_url:
            dashscope.base_http_api_url = api_url

        model_type = os.getenv("DEFAULT_VLM_TYPE", "qwen-vl-max")
        tmp_dir = os.path.join(tempfile.gettempdir(), "deepslide_vlm")
        local_path = _prepare_vlm_image_local_path(slide_image_path_or_bytes, tmp_dir)
        if not local_path:
            return []
        local_file_url = f"file://{os.path.abspath(local_path)}"

        speech_text = (speech_text or "").strip()
        if len(speech_text) > 1200:
            speech_text = speech_text[:1200]

        prompt = (
            "You are a vision-language model producing focus-zoom regions for a presentation image. "
            "Given an image and its narration, output an ordered list of rectangular regions to highlight. "
            "Prefer rectangles that correspond to salient blocks/figures/boxed areas already visible in the image (common in slides). "
            "If the most important target is unclear, choose a larger region that safely covers the plausible focus area rather than a tiny box. "
            "Return ONLY valid JSON with schema: {\"regions\": [{\"x\":0.0,\"y\":0.0,\"w\":0.2,\"h\":0.2,\"label\":\"...\"}, ...]}. "
            "Coordinates are normalized to the image (x,y,w,h in [0,1]). "
            f"Choose 3 to {max_regions} regions, avoid heavy overlap, and keep each region reasonably sized."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": local_file_url},
                    {"text": f"{prompt}\n\nNarration:\n{speech_text}"}
                ]
            }
        ]

        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model=model_type,
            messages=messages,
            result_format="message"
        )

        if response.status_code != 200:
            _log(f"VLM Failed: {response.code} - {response.message}")
            return []

        if not (hasattr(response, 'output') and response.output.choices):
            return []

        content = response.output.choices[0].message.content
        if isinstance(content, list):
            text = ""
            for item in content:
                if "text" in item:
                    text += item["text"]
        else:
            text = str(content)

        json_text = _extract_first_json_object(text)
        if not json_text:
            return []
        data = json.loads(json_text)
        regions = data.get("regions") if isinstance(data, dict) else None
        return _normalize_focus_regions(regions, max_regions=max_regions)
    except Exception as e:
        _log(f"VLM Focus Regions Error: {e}")
        return []

def _encode_png_data_uri(image_path_or_bytes):
    try:
        if isinstance(image_path_or_bytes, str):
            if not os.path.exists(image_path_or_bytes):
                return ""
            with open(image_path_or_bytes, "rb") as f:
                img_bytes = f.read()
        else:
            img_bytes = bytes(image_path_or_bytes)
        if not img_bytes:
            return ""
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""

def _resolve_image_file(image_path: str, base_dir: str) -> str:
    if not image_path:
        return ""
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, image_path))
        candidates.append(os.path.join(base_dir, "picture", os.path.basename(image_path)))
        candidates.append(os.path.join(base_dir, os.path.basename(image_path)))
    candidates.append(image_path)
    for p in candidates:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue
    return ""

def _encode_image_data_uri_from_path(full_path: str) -> str:
    try:
        if not full_path or not os.path.exists(full_path):
            return ""
        ext = os.path.splitext(full_path)[1].lower()

        if ext == ".pdf":
            try:
                doc = fitz.open(full_path)
                if doc.page_count <= 0:
                    return ""
                page = doc.load_page(0)
                pix = page.get_pixmap(alpha=False)
                b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                return f"data:image/png;base64,{b64}"
            except Exception:
                return ""

        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            with open(full_path, "rb") as f:
                img_bytes = f.read()
            if not img_bytes:
                return ""
            mime = ext.replace(".", "")
            if mime == "jpg":
                mime = "jpeg"
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            return f"data:image/{mime};base64,{b64}"

        try:
            img = Image.open(full_path)
            bio = io.BytesIO()
            img.save(bio, format="PNG")
            b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64}"
        except Exception:
            return ""
    except Exception:
        return ""

def _extract_includegraphics_paths(latex_frame: str):
    if not latex_frame:
        return []
    paths = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", latex_frame)
    out = []
    for p in paths:
        p2 = (p or "").strip()
        if p2:
            out.append(p2)
    return out

def _select_best_image_path(paths, base_dir: str) -> str:
    best = ""
    best_score = -1
    for p in paths or []:
        full = _resolve_image_file(p, base_dir)
        if not full:
            continue
        score = 0
        try:
            img = Image.open(full)
            w, h = img.size
            score = int(w) * int(h)
        except Exception:
            try:
                score = int(os.path.getsize(full))
            except Exception:
                score = 0
        if score > best_score:
            best_score = score
            best = full
    return best

def _build_focus_zoom_widget(slide_img_src: str, regions, interval_ms: int, scale: float):
    safe_regions = json.dumps(regions, ensure_ascii=False)
    safe_scale = float(scale) if scale else 1.4
    safe_interval = int(interval_ms) if interval_ms else 2000
    return (
        f"<div class=\"focus-zoom\" data-regions='{safe_regions}' data-interval=\"{safe_interval}\" data-scale=\"{safe_scale}\">"
        f"<img class=\"focus-zoom-base\" src=\"{slide_img_src}\" alt=\"\">"
        f"<div class=\"focus-zoom-layer\"></div>"
        f"</div>"
    )

def _build_split_slide_section(left_img_src: str, right_html: str, speech_text: str):
    left = f"<img class=\"split-left-img\" src=\"{left_img_src}\" alt=\"\">" if left_img_src else ""
    return (
        "<section>"
        "<div class=\"split-slide\">"
        f"<div class=\"split-left\">{left}</div>"
        f"<div class=\"split-right\">{right_html}</div>"
        "</div>"
        f"<aside class='notes'>{speech_text}</aside>"
        "</section>"
    )

def _build_beamer_bg_section(bg_src: str, overlay_html: str, speech_text: str, bg_opacity: float = 0.1):
    overlay = f"<div class=\"overlay-panel\">{overlay_html}</div>" if overlay_html else ""
    if bg_src:
        opacity = max(0.0, min(1.0, float(bg_opacity)))
        return (
            f"<section data-background-image=\"{bg_src}\" data-background-size=\"100% 100%\" data-background-opacity=\"{opacity}\" data-background-repeat=\"no-repeat\" data-background-position=\"center\">"
            f"{overlay}"
            f"<aside class='notes'>{speech_text}</aside>"
            f"</section>"
        )
    return (
        "<section>"
        f"{overlay}"
        f"<aside class='notes'>{speech_text}</aside>"
        "</section>"
    )

def _build_focus_zoom_section(slide_img_src: str, regions, speech_text: str, interval_ms: int, scale: float):
    return (
        f"<section>"
        f"{_build_focus_zoom_widget(slide_img_src, regions, interval_ms, scale)}"
        f"<aside class='notes'>{speech_text}</aside>"
        f"</section>"
    )

def _tool_generate_data_visualization(latex_table_code):
    """Tool: Generate a data visualization (Chart or Table) from LaTeX code."""
    # Generate a unique ID for the potential chart
    unique_id = f"chart_{uuid.uuid4().hex[:8]}"
    
    prompt = f"""
    You are a Data Visualization Expert.
    Analyze the following LaTeX table data and decide on the best frontend visualization.
    
    **Input Data (LaTeX):**
    {latex_table_code}
    
    **Instructions:**
    1.  **Analyze**: Does the data represent a numerical trend (time series), comparison (categories), or distribution (percentages)?
    2.  **Decision**:
        -   If YES (e.g., "Year vs Sales", "Model vs Accuracy"), generate a **Chart.js** visualization.
        -   If NO (text-heavy, complex headers, or just structured list), generate a **Styled HTML Table**.
    
    **Output Format:**
    
    **Option A: Chart (Preferred for numbers)**
    Return valid HTML containing:
    -   A `<div class="chart-container" style="position: relative; height:40vh; width:80vw; margin: 0 auto;">` wrapper.
    -   A `<canvas id="{unique_id}"></canvas>` inside.
    -   A `<script>` tag that:
        -   Gets the context: `const ctx = document.getElementById('{unique_id}').getContext('2d');`
        -   Initializes `new Chart(ctx, {{ type: '...', data: {{...}}, options: {{...}} }});`
        -   Use modern Chart.js syntax. Make it look professional (colors, fonts).
        -   Ensure `responsive: true` and `maintainAspectRatio: false` in options.
    
    **Option B: Table (Fallback)**
    Return valid HTML containing:
    -   A standard HTML `<table>` with `class="interactive-table"`.
    -   (Same requirements as before: thead, tbody, etc.)
    
    **Return ONLY the HTML code (no markdown backticks).**
    """
    def _fallback_viz() -> str:
        matrix = _parse_first_tabular_to_matrix(latex_table_code)
        if not matrix:
            return "<div class='error'>Visualization Failed</div>"
        return _matrix_to_interactive_viz_html(matrix)

    try:
        resp = st.session_state.collector.camel_client.get_response(prompt)
        clean = (resp or "").strip()
        if clean.startswith("```html"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        if "<canvas" in clean and "data-chart=" not in clean and "auto-chart" not in clean:
            return _fallback_viz()
        if "<table" in clean or "<canvas" in clean:
            return clean
        return _fallback_viz()
    except Exception as e:
        _log(f"Viz Tool Error: {e}")
        return _fallback_viz()

def _strip_latex_inline(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\\textbf\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\textit\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\emph\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\mathbf\{(.*?)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{(.*?)\}", r"\1", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^\}]*\})?", "", text)
    text = text.replace("\\&", "&")
    return " ".join(text.split()).strip()

def _parse_first_tabular_to_matrix(latex_table_code: str):
    if not latex_table_code:
        return []
    m = re.search(r"\\begin\{tabular\}.*?\\end\{tabular\}", latex_table_code, flags=re.DOTALL)
    if not m:
        return []
    tab = m.group(0)
    inner_m = re.search(r"\\begin\{tabular\}\{[^\}]*\}(.*?)\\end\{tabular\}", tab, flags=re.DOTALL)
    inner = inner_m.group(1) if inner_m else tab
    inner = re.sub(r"\\(toprule|midrule|bottomrule)", r"\\hline", inner)
    inner = inner.replace("\\\\", "\n")
    lines = [ln.strip() for ln in inner.splitlines()]
    rows = []
    for ln in lines:
        if not ln:
            continue
        ln = ln.strip()
        if ln in {"\\hline", "\\cline", "\\cmidrule"} or ln.startswith("\\hline"):
            continue
        if "&" not in ln:
            continue
        parts = [p.strip() for p in ln.split("&")]
        parts = [_strip_latex_inline(p) for p in parts]
        if any(parts):
            rows.append(parts)
    if not rows:
        return []
    max_len = max(len(r) for r in rows)
    norm = [r + [""] * (max_len - len(r)) for r in rows]
    return norm

def _try_float(s: str):
    try:
        s2 = (s or "").replace(",", "").strip()
        return float(s2)
    except Exception:
        return None

def _html_attr_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def _matrix_to_interactive_viz_html(matrix):
    if not matrix or not isinstance(matrix, list) or not isinstance(matrix[0], list):
        return "<div class='error'>Visualization Failed</div>"

    header = matrix[0]
    body = matrix[1:] if len(matrix) > 1 else []

    def looks_like_header(row, rest):
        if not row or not rest:
            return False
        numeric_counts = 0
        for r in rest[:5]:
            if len(r) >= 2 and _try_float(r[1]) is not None:
                numeric_counts += 1
        return numeric_counts >= max(1, min(3, len(rest)))

    has_header = looks_like_header(header, body)
    if not has_header:
        header = [f"Col {i+1}" for i in range(len(matrix[0]))]
        body = matrix

    chart_html = ""
    chart_cfg = None
    labels = []
    if len(body) >= 2 and len(header) >= 2:
        labels = [str(r[0]) for r in body if len(r) >= 1]

    def build_dataset(col_idx: int, label: str, color_idx: int):
        vals = []
        ok = 0
        for r in body:
            if len(r) <= col_idx:
                vals.append(None)
                continue
            v = _try_float(r[col_idx])
            if v is None:
                vals.append(None)
            else:
                ok += 1
                vals.append(v)
        if ok < 2:
            return None
        palette = [
            ("rgba(0,152,121,0.55)", "rgba(0,152,121,1)"),
            ("rgba(54,162,235,0.55)", "rgba(54,162,235,1)"),
            ("rgba(255,99,132,0.55)", "rgba(255,99,132,1)"),
            ("rgba(255,159,64,0.55)", "rgba(255,159,64,1)"),
            ("rgba(153,102,255,0.55)", "rgba(153,102,255,1)"),
        ]
        bg, bd = palette[color_idx % len(palette)]
        return {
            "label": label,
            "data": vals,
            "backgroundColor": bg,
            "borderColor": bd,
            "borderWidth": 1,
            "spanGaps": True,
        }

    datasets = []
    for j in range(1, len(header)):
        ds = build_dataset(j, _strip_latex_inline(header[j]), j - 1)
        if ds:
            datasets.append(ds)

    if labels and datasets:
        chart_type = "bar" if len(datasets) == 1 else "line"
        if chart_type == "line":
            for ds in datasets:
                ds["fill"] = False
                ds["tension"] = 0.25

        chart_cfg = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {"legend": {"display": True}},
                "scales": {"y": {"beginAtZero": True}},
                "animation": False,
            },
        }

    if chart_cfg:
        chart_json = _html_attr_escape(json.dumps(chart_cfg, ensure_ascii=False))
        chart_html = (
            "<div class=\"chart-container\" style=\"position: relative; height:45vh; width:92%; margin: 0 auto;\">"
            f"<canvas class=\"auto-chart\" data-chart='{chart_json}'></canvas>"
            "</div>"
        )

    thead = "".join([f"<th>{_strip_latex_inline(h)}</th>" for h in header])
    tbody_rows = []
    for r in body:
        tds = "".join([f"<td>{_strip_latex_inline(c)}</td>" for c in r])
        tbody_rows.append(f"<tr>{tds}</tr>")
    table_html = (
        "<table class=\"interactive-table\">"
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(tbody_rows)}</tbody>"
        "</table>"
    )

    if chart_html:
        return chart_html + table_html
    return table_html

def _tool_generate_zoomable_image(image_path, base_dir):
    """Tool: Generate a zoomable image tag."""
    # Resolve path
    full_path = None
    candidates = [
        os.path.join(base_dir, image_path),
        os.path.join(base_dir, "picture", os.path.basename(image_path)),
        os.path.join(base_dir, os.path.basename(image_path))
    ]
    for p in candidates:
        if os.path.exists(p):
            full_path = p
            break
            
    if full_path:
        try:
            with open(full_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                ext = os.path.splitext(full_path)[1].lower().replace(".", "")
                if ext == "jpg": ext = "jpeg"
                src = f"data:image/{ext};base64,{b64}"
                # Add zoomable class and simple style
                return f'<img src="{src}" class="zoomable-image fragment" alt="Zoomable Image" style="cursor: zoom-in; transition: transform 0.3s;">'
        except:
            pass
    return f'<img src="{image_path}" alt="Image Not Found">'

def _process_html_placeholders(html_content, base_dir):
    """Process placeholders and call tools."""
    
    # 1. Process Tables: <div class="complex-table-placeholder">LATEX</div>
    def table_replacer(match):
        latex_code = match.group(1)
        return _tool_generate_data_visualization(latex_code)
    
    html_content = re.sub(
        r'<div class="complex-table-placeholder">(.*?)</div>', 
        table_replacer, 
        html_content, 
        flags=re.DOTALL
    )
    
    # 2. Process Images: <div class="complex-image-placeholder">PATH</div>
    def image_replacer(match):
        path = match.group(1)
        return _tool_generate_zoomable_image(path, base_dir)
        
    html_content = re.sub(
        r'<div class="complex-image-placeholder">(.*?)</div>', 
        image_replacer, 
        html_content, 
        flags=re.DOTALL
    )
    
    return html_content

def _convert_single_slide_to_html(latex_frame, speech_text):
    """Use Agent to convert a SINGLE slide frame to HTML <section>."""
    prompt = f"""
You are an expert Web Developer.
Convert the following SINGLE LaTeX Beamer frame into a SINGLE Reveal.js HTML `<section>`.

**Requirements:**
1.  **Tag Mapping**:
    -   `\\frametitle{{...}}` -> `<h3>...</h3>`
    -   `\\framesubtitle{{...}}` -> `<h4>...</h4>`
    -   `\\itemize` / `\\enumerate` -> `<ul>` / `<ol>`
    -   `\\item` -> `<li class="fragment">` (Add 'fragment' class for animation)
    -   `\\textbf{{...}}` -> `<strong>...</strong>`
    -   `\\textit{{...}}` -> `<em>...</em>`
    -   `\\begin{{column}}` -> `<div style="flex: 1;">` (Use flexbox for columns)

2.  **Special Element Handling (Tool Calling)**:
    -   If you encounter a **Table** (`tabular`, `table` environment), do NOT convert it manually. 
        Instead, output: `<div class="complex-table-placeholder">...FULL_LATEX_TABLE_CODE...</div>`
    -   If you encounter an **Image** (`includegraphics`), do NOT convert it manually.
        Instead, output: `<div class="complex-image-placeholder">IMAGE_PATH</div>` (Extract only the path)

3.  **Animations**:
    -   Add `class="fragment"` to all `<li>`, `<p>` tags.

4.  **Speaker Notes**:
    -   Add `<aside class="notes">{speech_text}</aside>` inside the section.

5.  **Output**:
    -   Return ONLY the HTML code for this `<section>...</section>`.
    -   Do NOT wrap in `<html>` or `<body>`.

**LaTeX Frame:**
{latex_frame}

**Generate HTML <section>:**
"""
    try:
        response = st.session_state.collector.camel_client.get_response(prompt)
        # Clean up
        clean_html = response.strip()
        if clean_html.startswith("```html"): clean_html = clean_html[7:]
        if clean_html.startswith("```"): clean_html = clean_html[3:]
        if clean_html.endswith("```"): clean_html = clean_html[:-3]
        return clean_html.strip()
    except:
        return "<section><h3>Conversion Error</h3></section>"

def _resolve_image_paths_in_html(html_content, base_dir):
    """Find <img> tags with local paths and replace with Base64."""
    def replacer(match):
        full_tag = match.group(0)
        src = match.group(1)
        
        # Skip if already data URI or http
        if src.startswith("data:") or src.startswith("http"):
            return full_tag
            
        # Try to find file
        # Check direct path
        candidates = [
            os.path.join(base_dir, src),
            os.path.join(base_dir, "picture", os.path.basename(src)), # Common beamer pattern
            os.path.join(base_dir, os.path.basename(src))
        ]
        
        found_path = None
        for p in candidates:
            if os.path.exists(p):
                found_path = p
                break
        
        if found_path:
            try:
                with open(found_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                    ext = os.path.splitext(found_path)[1].lower().replace(".", "")
                    if ext == "jpg": ext = "jpeg"
                    new_src = f"data:image/{ext};base64,{b64}"
                    return full_tag.replace(src, new_src)
            except Exception as e:
                print(f"Error encoding image {found_path}: {e}")
                return full_tag
        else:
            print(f"Image not found: {src}")
            return full_tag

    # Regex for src="..."
    # Note: simple regex, assumes src is double or single quoted
    import re
    # Pattern to capture src value. 
    # match group 1 is the src content
    pattern = r'<img[^>]+src=["\'](.*?)["\']'
    return re.sub(pattern, replacer, html_content)

def generate_html_via_llm_iterative(tex_content, speeches, pdf_pages):
    """Generate HTML slides by converting one frame at a time."""
    
    # 1. Split LaTeX into frames
    frames = []
    # We can use the existing extract_frame_by_index logic or regex split
    # Since we need sequential frames, let's just find all matches
    matches = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', tex_content, re.DOTALL))
    
    # Align frames with speeches
    # Note: speeches might include <add> tags for structural pages that might NOT have a standard frame in content.tex
    # But usually content.tex has frames for content.
    # The Title page is separate.
    
    # Let's try to map: 
    # The Title page is typically Page 0 in speeches/pdf_pages, but it is in title.tex, not content.tex
    # So we need to handle Title separately.
    
    full_html_sections = []
    
    # Base directory for resolving images
    base_dir = os.path.dirname(st.session_state.generated_files["tex"]) if "generated_files" in st.session_state else ""

    focus_cfg = st.session_state.get("html_focus_zoom_cfg", None)
    focus_enabled = bool(focus_cfg.get("enabled", True)) if isinstance(focus_cfg, dict) else True
    focus_max_regions = int(focus_cfg.get("max_regions", 5)) if isinstance(focus_cfg, dict) else 5
    focus_interval_ms = int(focus_cfg.get("interval_ms", 2000)) if isinstance(focus_cfg, dict) else 2000
    focus_scale = float(focus_cfg.get("scale", 1.4)) if isinstance(focus_cfg, dict) else 1.4
    focus_use_cache = bool(focus_cfg.get("cache", True)) if isinstance(focus_cfg, dict) else True
    focus_cache_dir = os.path.join(base_dir, "focus_regions") if base_dir else ""
    if focus_enabled and focus_use_cache and focus_cache_dir:
        os.makedirs(focus_cache_dir, exist_ok=True)

    reveal_width, reveal_height = 1280, 720
    for p in (pdf_pages or [])[:3]:
        try:
            if isinstance(p, str) and os.path.exists(p):
                with open(p, "rb") as f:
                    img_bytes = f.read()
            else:
                img_bytes = bytes(p)
            im = Image.open(io.BytesIO(img_bytes))
            reveal_width, reveal_height = im.size
            break
        except Exception:
            continue
    
    # --- Title Page (Page 0) ---
    if len(speeches) > 0:
        title_speech = speeches[0].replace("<add>", "").strip()
        bg_src = _encode_png_data_uri(pdf_pages[0]) if (pdf_pages and len(pdf_pages) > 0) else ""
        full_html_sections.append(_build_beamer_bg_section(bg_src, "", title_speech, bg_opacity=1.0))

    # --- Content Pages ---
    # We iterate through speeches starting from index 1 (since 0 is Title)
    # We need to map speech index to LaTeX frame index
    # Logic: Structural pages might be separate?
    # In this app, content.tex contains the frames. 
    # extract_frame_by_index uses 0-based index on content.tex
    
    current_frame_idx = 0
    
    # Progress bar
    progress_bar = st.progress(0.0)
    
    # Start from 1 to skip Title
    for i in range(1, len(speeches)):
        speech = speeches[i]
        is_structural = "<add>" in speech
        
        # Determine if this page corresponds to a frame in content.tex
        # In current logic:
        # Structural pages (Transition/TOC) might NOT be in content.tex explicitly if generated by \section{}?
        # Actually, Divider generates \begin{frame} for everything usually?
        # Let's look at Divider... 
        # Usually content.tex has ALL frames.
        
        # If is_structural, it might correspond to a frame?
        # Let's assume sequential mapping to matches in content.tex
        
        if current_frame_idx < len(matches):
            target_frame_latex = matches[current_frame_idx].group(1)
            speech_text = speech.replace("<add>", "").strip()
            bg_src = _encode_png_data_uri(pdf_pages[i]) if (pdf_pages and i < len(pdf_pages)) else ""

            has_tabular = any(s in target_frame_latex for s in ["\\begin{tabular}", "\\begin{table}", "\\begin{tabularx}", "\\begin{longtable}"])
            has_image = "\\includegraphics" in target_frame_latex

            if has_tabular:
                tab_m = re.search(r"\\begin\{(tabular|tabularx|longtable)\}.*?\\end\{\1\}", target_frame_latex, flags=re.DOTALL)
                tab_code = tab_m.group(0) if tab_m else target_frame_latex
                viz_html = _tool_generate_data_visualization(tab_code)
                html_sec = _build_beamer_bg_section(bg_src, viz_html, speech_text, bg_opacity=1.0)
            elif focus_enabled and has_image:
                img_paths = _extract_includegraphics_paths(target_frame_latex)
                best_img_path = _select_best_image_path(img_paths, base_dir)
                focus_img_src = _encode_image_data_uri_from_path(best_img_path) if best_img_path else ""
                if not focus_img_src:
                    focus_img_src = bg_src
                cached_regions = None
                cache_path = os.path.join(focus_cache_dir, f"slide_{i:03d}.json") if (focus_use_cache and focus_cache_dir) else ""
                if cache_path and os.path.exists(cache_path):
                    try:
                        with open(cache_path, "r", encoding="utf-8") as f:
                            cached_regions = json.load(f)
                    except Exception:
                        cached_regions = None
                regions = _normalize_focus_regions(cached_regions, max_regions=focus_max_regions) if cached_regions is not None else None
                if regions is None or len(regions) == 0:
                    regions = _call_vlm_focus_regions(best_img_path or (pdf_pages[i] if (pdf_pages and i < len(pdf_pages)) else ""), speech_text, max_regions=focus_max_regions)
                    if not regions:
                        regions = [
                            {"x": 0.08, "y": 0.12, "w": 0.84, "h": 0.42, "label": ""},
                            {"x": 0.08, "y": 0.46, "w": 0.84, "h": 0.42, "label": ""},
                            {"x": 0.12, "y": 0.16, "w": 0.76, "h": 0.76, "label": ""},
                        ]
                    if cache_path:
                        try:
                            with open(cache_path, "w", encoding="utf-8") as f:
                                json.dump(regions, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                overlay = _build_focus_zoom_widget(focus_img_src, regions, focus_interval_ms, focus_scale) if focus_img_src else ""
                html_sec = _build_beamer_bg_section(bg_src, overlay, speech_text, bg_opacity=1.0) if bg_src else _build_focus_zoom_section(focus_img_src, regions, speech_text, focus_interval_ms, focus_scale)
            else:
                if bg_src:
                    html_sec = _build_beamer_bg_section(bg_src, "", speech_text, bg_opacity=1.0)
                else:
                    html_sec = _convert_single_slide_to_html(target_frame_latex, speech_text)
                    html_sec = _process_html_placeholders(html_sec, base_dir)
                    html_sec = _resolve_image_paths_in_html(html_sec, base_dir)

            full_html_sections.append(html_sec)
            current_frame_idx += 1
        else:
            # No more frames in LaTeX but we have speech? 
            # Maybe structural page without frame?
            speech_text = speech.replace("<add>", "").strip()
            bg_src = _encode_png_data_uri(pdf_pages[i]) if (pdf_pages and i < len(pdf_pages)) else ""
            full_html_sections.append(_build_beamer_bg_section(bg_src, "", speech_text, bg_opacity=1.0))
            
        progress_bar.progress(i / len(speeches))
        
    progress_bar.progress(1.0)

    focus_zoom_js = """
			const FocusZoom = (() => {
				function parseRegions(el) {
					const raw = el.getAttribute('data-regions') || '[]';
					try {
						const regions = JSON.parse(raw);
						return Array.isArray(regions) ? regions : [];
					} catch (e) {
						return [];
					}
				}

				function build(el) {
					const baseImg = el.querySelector('.focus-zoom-base');
					const layer = el.querySelector('.focus-zoom-layer');
					const regions = parseRegions(el);
					const interval = Number(el.getAttribute('data-interval') || '2000');
					const scale = Number(el.getAttribute('data-scale') || '1.4');
					let boxes = [];
					let idx = 0;
					let timer = null;

					function clear() {
						boxes.forEach(b => b.remove());
						boxes = [];
						idx = 0;
					}

					function layout() {
						clear();
						const w = baseImg.clientWidth;
						const h = baseImg.clientHeight;
						if (!w || !h) return;
						el.style.setProperty('--focus-scale', String(scale));
						regions.forEach(r => {
							const x = Math.max(0, Math.min(1, Number(r.x)));
							const y = Math.max(0, Math.min(1, Number(r.y)));
							const rw = Math.max(0.01, Math.min(1, Number(r.w)));
							const rh = Math.max(0.01, Math.min(1, Number(r.h)));
							const box = document.createElement('div');
							box.className = 'focus-zoom-box';
							box.style.left = (x * w) + 'px';
							box.style.top = (y * h) + 'px';
							box.style.width = (rw * w) + 'px';
							box.style.height = (rh * h) + 'px';
							const img = document.createElement('img');
							img.src = baseImg.src;
							img.style.width = w + 'px';
							img.style.height = h + 'px';
							img.style.left = (-x * w) + 'px';
							img.style.top = (-y * h) + 'px';
							box.appendChild(img);
							layer.appendChild(box);
							boxes.push(box);
						});
						if (boxes.length) boxes[0].classList.add('is-active');
					}

					function step() {
						if (!boxes.length) return;
						boxes.forEach(b => b.classList.remove('is-active'));
						boxes[idx].classList.add('is-active');
						idx = (idx + 1) % boxes.length;
					}

					function start() {
						stop();
						layout();
						step();
						timer = window.setInterval(step, Math.max(500, interval));
					}

					function stop() {
						if (timer) window.clearInterval(timer);
						timer = null;
						boxes.forEach(b => b.classList.remove('is-active'));
					}

					function ensureLoaded() {
						if (baseImg.complete) return Promise.resolve();
						return new Promise(resolve => {
							baseImg.addEventListener('load', resolve, { once: true });
						});
					}

					return {
						start: () => ensureLoaded().then(start),
						stop,
						layout: () => ensureLoaded().then(layout)
					};
				}

				function initAll() {
					const widgets = Array.from(document.querySelectorAll('.focus-zoom'));
					const controllers = new Map();
					widgets.forEach(w => controllers.set(w, build(w)));
					function updateActive() {
						if (typeof Reveal === 'undefined') return;
						const cur = Reveal.getCurrentSlide();
						controllers.forEach((ctl, el) => {
							if (cur && cur.contains(el)) {
								ctl.start();
							} else {
								ctl.stop();
							}
						});
					}
					if (typeof Reveal !== 'undefined') {
						Reveal.on('slidechanged', updateActive);
						Reveal.on('ready', updateActive);
					}
					window.addEventListener('resize', () => {
						controllers.forEach((ctl) => ctl.layout());
					});
					updateActive();
				}

				return { initAll };
			})();
"""

    auto_charts_js = """
			const AutoCharts = (() => {
				function parseConfig(canvas) {
					const raw = canvas.getAttribute('data-chart') || '';
					if (!raw) return null;
					try {
						return JSON.parse(raw);
					} catch (e) {
						return null;
					}
				}

				function renderIn(slide) {
					if (!slide || typeof Chart === 'undefined') return;
					slide.querySelectorAll('canvas.auto-chart').forEach((canvas) => {
						if (canvas.__chart) return;
						const cfg = parseConfig(canvas);
						if (!cfg) return;
						const ctx = canvas.getContext('2d');
						if (!ctx) return;
						canvas.__chart = new Chart(ctx, cfg);
					});
				}

				function resizeIn(slide) {
					if (!slide) return;
					slide.querySelectorAll('canvas.auto-chart').forEach((canvas) => {
						if (canvas.__chart) canvas.__chart.resize();
					});
				}

				function init() {
					if (typeof Reveal === 'undefined') return;
					function onActive() {
						const slide = Reveal.getCurrentSlide();
						renderIn(slide);
						resizeIn(slide);
					}
					Reveal.on('ready', onActive);
					Reveal.on('slidechanged', onActive);
					window.addEventListener('resize', onActive);
					onActive();
				}

				return { init };
			})();
"""
    
    # Wrap in Reveal.js
    final_html = f"""
<!doctype html>
<html>
	<head>
		<meta charset="utf-8">
		<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
		<title>Presentation</title>
		<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reset.min.css">
		<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.css">
		<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/theme/white.min.css">
        <style>
            html, body, .reveal, .reveal .slides, .reveal .slides section {{
                height: 100%;
                width: 100%;
                overflow: hidden; /* Prevent scrolling if content overflows */
            }}
            .reveal .slides section {{ 
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center; 
                padding: 0; /* Remove padding to maximize space */
                position: relative;
            }}
            /* Scale content to fit if too large */
            .reveal .slides {{
                transform-origin: center center; 
            }}
            .reveal h1, .reveal h2, .reveal h3, .reveal h4 {{ text-transform: none; margin: 0.5em 0; }}
            .reveal section img {{ border: none; box-shadow: none; max-height: 80vh; max-width: 90vw; }}
            .reveal .slides section {{ text-align: left; }}
            
            /* Ensure content fits */
            .reveal p, .reveal li {{ font-size: 0.9em; }}

            /* Interactive Table Styles */
            .interactive-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 0.8em;
                font-family: sans-serif;
                box-shadow: 0 0 20px rgba(0, 0, 0, 0.15);
            }}
            .interactive-table thead tr {{
                background-color: #009879;
                color: #ffffff;
                text-align: left;
            }}
            .interactive-table th, .interactive-table td {{
                padding: 12px 15px;
            }}
            .interactive-table tbody tr {{
                border-bottom: 1px solid #dddddd;
            }}
            .interactive-table tbody tr:nth-of-type(even) {{
                background-color: #f3f3f3;
            }}
            .interactive-table tbody tr:last-of-type {{
                border-bottom: 2px solid #009879;
            }}
            .interactive-table tbody tr:hover {{
                color: #009879;
                cursor: pointer;
                font-weight: bold;
            }}

            .focus-zoom {{
                position: relative;
                display: inline-block;
                max-width: 90vw;
                max-height: 80vh;
            }}
            .focus-zoom-base {{
                display: block;
                width: 100%;
                height: auto;
                max-height: 80vh;
                object-fit: contain;
                filter: none;
            }}
            .focus-zoom-layer {{
                position: absolute;
                left: 0;
                top: 0;
                right: 0;
                bottom: 0;
                pointer-events: none;
            }}
            .focus-zoom-box {{
                position: absolute;
                border: 3px solid #ff3b30;
                overflow: hidden;
                box-shadow: 0 0 20px rgba(255, 59, 48, 0.6);
                opacity: 0;
                transform-origin: center center;
                transition: transform 600ms ease, opacity 600ms ease;
                will-change: transform, opacity;
            }}
            .focus-zoom-box.is-active {{
                opacity: 1;
                transform: scale(var(--focus-scale, 1.4));
            }}
            .focus-zoom-box img {{
                position: absolute;
                display: block;
            }}

            .overlay-panel {{
                position: absolute;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                width: min(92vw, 1100px);
                max-height: 84vh;
                overflow: auto;
                padding: 18px 22px;
                background: rgba(255, 255, 255, 0.92);
                border-radius: 14px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
                pointer-events: auto;
            }}
        </style>
	</head>
	<body>
		<div class="reveal">
			<div class="slides">
                {chr(10).join(full_html_sections)}
			</div>
		</div>
		<script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.js"></script>
		<script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/plugin/notes/notes.min.js"></script>
        <!-- Medium Zoom for Zoomable Images -->
        <script src="https://unpkg.com/medium-zoom@1.0.6/dist/medium-zoom.min.js"></script>
        <!-- Chart.js -->
		<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
		<script>
			{focus_zoom_js}
			{auto_charts_js}
			Reveal.initialize({{
				hash: false, controls: true, progress: true, center: true, slideNumber: 'c/t', embedded: true,
				width: {reveal_width}, height: {reveal_height}, margin: 0.1, minScale: 0.2, maxScale: 2.0,
				plugins: [ RevealNotes ]
			}}).then(() => {{
                // Initialize Medium Zoom
                mediumZoom('.zoomable-image', {{
                    margin: 24,
                    background: '#BADA55',
                }});
				FocusZoom.initAll();
				AutoCharts.init();
            }});
            
            // Simple Table Sorter
            document.addEventListener('DOMContentLoaded', () => {{
                const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;
                const comparer = (idx, asc) => (a, b) => ((v1, v2) => 
                    v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2) ? v1 - v2 : v1.toString().localeCompare(v2)
                )(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

                document.querySelectorAll('.interactive-table th').forEach(th => th.addEventListener('click', (() => {{
                    const table = th.closest('table');
                    const tbody = table.querySelector('tbody');
                    Array.from(tbody.querySelectorAll('tr'))
                        .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
                        .forEach(tr => tbody.appendChild(tr));
                }})));
            }});
		</script>
	</body>
</html>
    """
    return final_html

def inject_reveal_slide_control(html_content, page_idx):
    """Inject JavaScript to jump to specific slide index."""
    # We look for the Reveal.initialize call or end of body to inject the slide command
    # A simple robust way is to append a script at the end of body
    
    injection = f"""
    <script>
        // Wait for Reveal to be ready or just try to call it
        // Check if Reveal is defined
        if (typeof Reveal !== 'undefined') {{
            if (Reveal.isReady()) {{
                Reveal.slide({page_idx});
            }} else {{
                Reveal.addEventListener('ready', event => {{
                    Reveal.slide({page_idx});
                }});
            }}
        }}
    </script>
    </body>
    """
    
    if "</body>" in html_content:
        return html_content.replace("</body>", injection)
    else:
        return html_content + injection

def _render_vis_network(res, pdf_pages, files, show_sequential=True):
    """
    Render a horizontal Panel Sequence with Reference Graph edges (Arc Diagram).
    Matches the 'Case Study' panel style but adds explicit graph edges.
    """
    import json
    import base64
    from PIL import Image
    import io
    import glob

    # 1. Prepare Images Map
    images_map = {}
    if pdf_pages:
        for i, p in enumerate(pdf_pages):
            if os.path.exists(p):
                try:
                    with Image.open(p) as img:
                        img.thumbnail((320, 240))
                        bio = io.BytesIO()
                        img.save(bio, format="PNG")
                        b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
                        images_map[i] = f"data:image/png;base64,{b64}"
                except: pass

    if not images_map and "pdf" in files:
        try:
            output_dir = os.path.dirname(files["pdf"])
            preview_dir = os.path.join(output_dir, "preview_cache")
            if os.path.exists(preview_dir):
                found_files = glob.glob(os.path.join(preview_dir, "page_*.png"))
                def extract_pn(fname):
                    base = os.path.basename(fname)
                    parts = base.split("_")
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
                    return 9999
                found_files.sort(key=extract_pn)
                for fpath in found_files:
                    pn = extract_pn(fpath)
                    if pn not in images_map:
                        try:
                            with Image.open(fpath) as img:
                                img.thumbnail((320, 240))
                                bio = io.BytesIO()
                                img.save(bio, format="PNG")
                                b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
                                images_map[pn] = f"data:image/png;base64,{b64}"
                        except: pass
        except Exception as e:
            print(f"Error loading from preview_cache: {e}")

    # 2. Build Nodes and Edges Data for JS
    max_res_id = max([int(n['id']) for n in res.get('nodes', [])]) if res.get('nodes') else -1
    total_slides = max(len(images_map), max_res_id + 1)
    
    nodes_data = []
    graph_node_info = {int(n['id']): n for n in res.get('nodes', [])}
    
    for i in range(total_slides):
        node_data = graph_node_info.get(i, {})
        nodes_data.append({
            "id": i,
            "label": f"SLIDE {i+1}",
            "section": node_data.get('section', 'Slide Content'),
            "img": images_map.get(i, "")
        })
        
    edges_data = res.get("edges", [])
    clean_edges = []
    
    # 1. Add implicit sequential edges for visual continuity
    # Check if implicit sequential edges exist; if not, add them
    existing_pairs = set()
    for e in edges_data:
        try:
            existing_pairs.add((int(e["from"]), int(e["to"])))
        except: pass
        
    for i in range(total_slides - 1):
        if show_sequential:
            clean_edges.append({"from": i, "to": i+1, "label": "", "type": "sequential"})
            
    # 2. Add explicit edges from data
    for e in edges_data:
        try:
            # Explicit edges are references
            src = int(e["from"])
            dst = int(e["to"])
            # Ensure src/dst are valid slide indices
            if 0 <= src < total_slides and 0 <= dst < total_slides:
                 clean_edges.append({"from": src, "to": dst, "label": e.get("label", ""), "type": "reference"})
        except: pass

    # 3. HTML Structure
    cards_html = ""
    for node in nodes_data:
        img_html = f'<img src="{node["img"]}" class="panel-thumb" alt="{node["label"]}">' if node["img"] else '<div class="panel-no-preview">No Preview</div>'
        card = f"""
        <div class="panel-card" id="card-{node['id']}">
            <div class="panel-header">
                <span>{node['label']}</span>
            </div>
            <div class="panel-sub">{node['section']}</div>
            <div class="panel-body">
                {img_html}
            </div>
        </div>
        """
        cards_html += card

    json_nodes = json.dumps(nodes_data)
    json_edges = json.dumps(clean_edges)

    VIZ_HEIGHT = 600
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #ffffff; overflow: hidden; }}
        
        .scroll-wrapper {{
            position: relative;
            width: 100%;
            height: {VIZ_HEIGHT}px; /* Increased height for arcs */
            display: flex;
            align-items: center;
            background: #f8fafc;
        }}

        .viz-container {{
            position: relative;
            display: flex;
            flex-direction: row;
            gap: 60px;
            overflow-x: auto;
            overflow-y: visible; /* Allow arcs to extend */
            padding: 200px 60px 200px; /* Huge top AND bottom padding for arcs */
            align-items: center;
            height: 100%;
            width: 100%;
            scroll-behavior: smooth;
        }}
        
        #arrow-layer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 1px;
            height: 100%;
            pointer-events: none;
            z-index: 0;
        }}
        
        .scroll-btn {{
            position: fixed;
            z-index: 200;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #cbd5e1;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            color: #334155;
            font-size: 1.2rem;
            top: 50%; /* Adjusted position */
            transform: translateY(-50%);
            transition: all 0.2s;
        }}
        .scroll-btn:hover {{ background: #fff; transform: translateY(-50%) scale(1.1); color: #0f172a; }}
        .scroll-btn.left {{ left: 10px; }}
        .scroll-btn.right {{ right: 10px; }}

        .panel-card {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            min-width: 220px;
            max-width: 220px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            position: relative;
            z-index: 10;
            transition: transform 0.2s;
        }}
        .panel-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            border-color: #94a3b8;
        }}
        
        .panel-header {{
            background-color: #0f172a;
            color: white;
            padding: 10px 14px;
            font-size: 0.85rem;
            font-weight: 700;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            display: flex; justify-content: space-between;
        }}
        .panel-sub {{
            color: #64748b;
            font-size: 0.7rem;
            text-transform: uppercase;
            font-weight: 600;
            padding: 10px 14px 4px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .panel-body {{
            padding: 10px 14px 14px;
            display: flex; flex-direction: column; align-items: center;
        }}
        .panel-thumb {{
            width: 100%; height: auto;
            border: 1px solid #cbd5e1; border-radius: 4px;
        }}
        .panel-no-preview {{
            width: 100%; height: 100px; background: #f1f5f9; color: #94a3b8;
            display: flex; align-items: center; justify-content: center; font-size: 0.75rem;
        }}
        
        .viz-container::-webkit-scrollbar {{ height: 8px; }}
        .viz-container::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
      </style>
    </head>
    <body>
        <div class="scroll-wrapper">
            <div class="scroll-btn left" onclick="scrollViz(-1)">❮</div>
            <div class="viz-container" id="scroller">
                <svg id="arrow-layer"></svg>
                {cards_html}
            </div>
            <div class="scroll-btn right" onclick="scrollViz(1)">❯</div>
        </div>

        <script>
            const nodes = {json_nodes};
            const edges = {json_edges};
            
            function scrollViz(dir) {{
                const el = document.getElementById('scroller');
                el.scrollBy({{ left: dir * 300, behavior: 'smooth' }});
            }}
            
            function drawArrows() {{
                const container = document.getElementById('scroller');
                const svg = document.getElementById('arrow-layer');
                svg.style.width = container.scrollWidth + 'px';
                
                while (svg.lastChild) {{ svg.removeChild(svg.lastChild); }}
                
                function getCardPos(id) {{
                    const card = document.getElementById('card-' + id);
                    if (!card) return null;
                    return {{
                        x: card.offsetLeft + card.offsetWidth / 2,
                        y: card.offsetTop,
                        h: card.offsetHeight,
                        w: card.offsetWidth
                    }};
                }}
                
                // Add Markers (Blue and Red)
                const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                
                // Blue Arrowhead (Forward)
                const markerBlue = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerBlue.setAttribute("id", "arrowhead-blue");
                markerBlue.setAttribute("markerWidth", "10");
                markerBlue.setAttribute("markerHeight", "7");
                markerBlue.setAttribute("refX", "9");
                markerBlue.setAttribute("refY", "3.5");
                markerBlue.setAttribute("orient", "auto");
                const polyBlue = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                polyBlue.setAttribute("points", "0 0, 10 3.5, 0 7");
                polyBlue.setAttribute("fill", "#3b82f6");
                markerBlue.appendChild(polyBlue);
                defs.appendChild(markerBlue);

                // Red Arrowhead (Back)
                const markerRed = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerRed.setAttribute("id", "arrowhead-red");
                markerRed.setAttribute("markerWidth", "10");
                markerRed.setAttribute("markerHeight", "7");
                markerRed.setAttribute("refX", "9");
                markerRed.setAttribute("refY", "3.5");
                markerRed.setAttribute("orient", "auto");
                const polyRed = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                polyRed.setAttribute("points", "0 0, 10 3.5, 0 7");
                polyRed.setAttribute("fill", "#ef4444");
                markerRed.appendChild(polyRed);
                defs.appendChild(markerRed);
                
                // Gray Arrowhead (Sequential)
                const markerGray = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                markerGray.setAttribute("id", "arrowhead-gray");
                markerGray.setAttribute("markerWidth", "10");
                markerGray.setAttribute("markerHeight", "7");
                markerGray.setAttribute("refX", "9");
                markerGray.setAttribute("refY", "3.5");
                markerGray.setAttribute("orient", "auto");
                const polyGray = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                polyGray.setAttribute("points", "0 0, 10 3.5, 0 7");
                polyGray.setAttribute("fill", "#94a3b8");
                markerGray.appendChild(polyGray);
                defs.appendChild(markerGray);

                svg.appendChild(defs);

                edges.forEach(e => {{
                    const src = getCardPos(e.from);
                    const dst = getCardPos(e.to);
                    if (!src || !dst) return;
                    
                    const isNext = (e.to === e.from + 1);
                    const isBack = e.to < e.from;
                    
                    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                    path.setAttribute("fill", "none");
                    path.setAttribute("stroke-width", "2");
                    
                    let d = "";
                    if (e.type === 'sequential') {{
                        // Standard sequential edge (Gray)
                        const x1 = src.x + src.w/2;
                        const y1 = src.y + src.h/2;
                        const x2 = dst.x - dst.w/2;
                        const y2 = dst.y + dst.h/2;
                        d = `M ${{x1}} ${{y1}} C ${{x1+30}} ${{y1}}, ${{x2-30}} ${{y2}}, ${{x2}} ${{y2}}`;
                        path.setAttribute("stroke", "#94a3b8");
                        path.setAttribute("stroke-width", "1.5");
                        path.setAttribute("marker-end", "url(#arrowhead-gray)");
                    }} else {{
                        // Reference Edge (Color, Curved)
                        const offset = 40; // Shift anchors from center to separate start/end
                        
                        if (isBack) {{
                            // Back Reference: Curve UP (Above cards)
                            // Source (Right) -> Dest (Left)
                            // Start from Source's Left side (Top), End at Dest's Right side (Top)
                            const x1 = src.x - offset; 
                            const y1 = src.y;
                            const x2 = dst.x + offset;
                            const y2 = dst.y;
                            
                            const dist = Math.abs(x2 - x1);
                            const h = 30 + Math.log(dist + 1) * 20;
                            d = `M ${{x1}} ${{y1}} C ${{x1}} ${{y1-h}}, ${{x2}} ${{y2-h}}, ${{x2}} ${{y2}}`;
                            
                            path.setAttribute("stroke", "#ef4444"); // Red for Back Ref
                            path.setAttribute("stroke-dasharray", "4");
                            path.setAttribute("marker-end", "url(#arrowhead-red)");
                        }} else {{
                            // Forward Reference: Curve DOWN (Below cards)
                            // Source (Left) -> Dest (Right)
                            // Start from Source's Right side (Bottom), End at Dest's Left side (Bottom)
                            const x1 = src.x + offset;
                            const y1_b = src.y + src.h;
                            const x2 = dst.x - offset;
                            const y2_b = dst.y + dst.h;
                            
                            const dist = Math.abs(x2 - x1);
                            const h = 30 + Math.log(dist + 1) * 20;
                            d = `M ${{x1}} ${{y1_b}} C ${{x1}} ${{y1_b+h}}, ${{x2}} ${{y2_b+h}}, ${{x2}} ${{y2_b}}`;
                            
                            path.setAttribute("stroke", "#3b82f6"); // Blue for Forward Ref
                            path.setAttribute("marker-end", "url(#arrowhead-blue)");
                        }}
                        path.setAttribute("stroke-width", "3");
                        path.setAttribute("stroke-opacity", "0.8");
                    }}
                    path.setAttribute("d", d);
                    svg.appendChild(path);
                }});
            }}
            
            window.onload = drawArrows;
            window.onresize = drawArrows;
            setTimeout(drawArrows, 500);
            setTimeout(drawArrows, 1500);
        </script>
    </body>
    </html>
    """
    return html_code, VIZ_HEIGHT

def _batch_beautify_slides(rounds: int):
    st.info(f"Starting batch beautification ({rounds} rounds)...")
    files = st.session_state.generated_files
    tex_path = files["tex"]
    
    if not os.path.exists(tex_path):
        st.error("Content file not found.")
        return

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    
    for r in range(rounds):
        status_text.write(f"**Round {r+1}/{rounds}**")
        
        # Refresh state
        speeches = st.session_state.preview_state.get("speech_segments", [])
        pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
        
        if not speeches or not pdf_pages:
            st.error("Preview state missing. Please compile first.")
            return

        with open(tex_path, "r") as f: full_tex = f.read()
        
        tasks = [] # (page_idx, frame_idx, image_path)
        
        # Logic to map page_idx to frame_idx matching _modify_content_page
        current_frame_count = 0
        
        for p_idx, speech in enumerate(speeches):
            is_structural = "<add>" in speech
            
            frame_idx_for_this_page = current_frame_count
            
            if not is_structural:
                current_frame_count += 1
            
            # Skip Title (p_idx 0) and Structural
            if p_idx == 0: continue
            if is_structural: continue
            
            # It is a content page
            if p_idx < len(pdf_pages):
                tasks.append({
                    "page_idx": p_idx,
                    "frame_idx": frame_idx_for_this_page,
                    "image_path": pdf_pages[p_idx]
                })
        
        # Perform VLM calls
        updates = {} # frame_idx -> new_content
        
        for i, task in enumerate(tasks):
            status_text.write(f"Round {r+1}: Processing Slide {task['page_idx']+1}...")
            
            target_frame, _ = extract_frame_by_index(full_tex, task['frame_idx'])
            
            if target_frame:
                new_frame = _call_vlm_beautify(task['image_path'], target_frame)
                if new_frame:
                    updates[task['frame_idx']] = new_frame
            
            progress_bar.progress((r + (i+1)/len(tasks)) / rounds)
            
        # Apply updates
        if updates:
            for f_idx, content in updates.items():
                full_tex = replace_frame_in_content(full_tex, f_idx, content)
            
            with open(tex_path, "w") as f: f.write(full_tex)
            
            # Compile
            status_text.write(f"Round {r+1}: Compiling...")
            c = Compiler()
            res = c.run(os.path.dirname(tex_path))
            if res.get("success"):
                _update_pdf_preview()
            else:
                st.error(f"Compilation failed in Round {r+1}")
                break
        else:
            st.warning("No updates generated in this round.")
            
    status_text.write("Done!")
    progress_bar.progress(1.0)
    st.success("All rounds completed.")

def render_sidebar_logs():
    with st.sidebar:
        with st.expander("🛠 Tool Calls & Logs", expanded=False):
            st.text("\n".join(TOOL_LOGS[-20:]))
            if st.button("Clear Logs"):
                TOOL_LOGS.clear()
                st.rerun()

# --- Page 1: Requirements ---
def render_page_requirements(tmp_base):
    st.title("Requirements")
    
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
                    
                    if not main_tex:
                         main_md = find_main_md(extract_dir)
                         if main_md:
                             try:
                                 with open(main_md, "r", encoding="utf-8") as f:
                                     md_content = f.read()
                                 tex_content = convert_md_to_tex(md_content)
                                 # Save to a new tex file
                                 generated_tex_path = os.path.join(extract_dir, "generated_main.tex")
                                 with open(generated_tex_path, "w", encoding="utf-8") as f:
                                     f.write(tex_content)
                                 main_tex = generated_tex_path
                                 st.info(f"Detected Markdown file: {os.path.basename(main_md)}. Converted to LaTeX.")
                             except Exception as e:
                                 st.warning(f"Failed to convert Markdown: {e}")
                    
                    if not main_tex:
                         main_docx = find_main_docx(extract_dir)
                         if main_docx:
                             try:
                                 with st.spinner("Converting Word document to LaTeX..."):
                                     # Pass extract_dir as media_path to store extracted images
                                     tex_content = convert_docx_to_tex(main_docx, media_path=extract_dir)
                                     generated_tex_path = os.path.join(extract_dir, "generated_main.tex")
                                     with open(generated_tex_path, "w", encoding="utf-8") as f:
                                         f.write(tex_content)
                                     main_tex = generated_tex_path
                                     st.info(f"Detected Word document: {os.path.basename(main_docx)}. Converted to LaTeX.")
                             except Exception as e:
                                 st.warning(f"Failed to convert Word document: {e}")

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
        
        with bottom_box:
            # 1. Audio Input Row with Clone Button
            c_audio, c_transcribe, c_btn = st.columns([15, 1, 1])
            with c_audio:
                audio_value = st.audio_input("Record Voice", key="req_audio")
            with c_transcribe:
                st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
                # Manual transcribe button
                if st.button("📝", help="Transcribe to Text", key="btn_transcribe_req"):
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
                st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
                # Small button for saving clone voice, only enabled if audio exists
                # Since st.audio_input triggers rerun, we check session state path
                if st.button("💾", help="Save as Cloned Voice", key="btn_save_clone"):
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
                c_input, c_btn = st.columns([8, 1])
                with c_input:
                    user_text = st.text_area("Requirements", value=draft_text, height=35, label_visibility="collapsed", placeholder="Tell DeepSlide your requirements...")
                with c_btn:
                    st.markdown('<div style="height: 3px;"></div>', unsafe_allow_html=True)
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
    st.title("Logic Chain")
    
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
        
        # Recommender
        if st.button("Recommend Reference Edges"):
            with st.spinner("Analyzing..."):
                from edges_recommender import EdgesRecommender
                from content_tree_builder import make_tree_tools
                tools = make_tree_tools(st.session_state.content_tree_nodes)
                edges = st.session_state.edges_rec.recommend(
                    [n.name for n in editor.nodes], 
                    st.session_state.collector.paper_abstract, 
                    _wrap_tools(tools)
                )
                if edges: ui.editor.set_edges(edges)
                st.rerun()

        # st.divider()
        # st.header("Generation")
        st.subheader("Continue")
        
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
            cn1, cn2, cn3, _ = st.columns([1,1,1, 12])
            with cn1: 
                if st.button("◀", key="ed_prev"):
                    st.session_state.preview_state["current_page"] = max(0, curr - 1)
                    st.rerun()
            with cn3:
                if st.button("▶", key="ed_next"):
                    st.session_state.preview_state["current_page"] = min(len(pages)-1, curr + 1)
                    st.rerun()
            with cn2: st.caption(f"{curr+1}/{len(pages)}")
            st.image(pages[st.session_state.preview_state["current_page"]])
            
            # Show speech preview below image
            speeches = st.session_state.preview_state.get("speech_segments", [])
            speech_idx = st.session_state.preview_state["current_page"]
            if 0 <= speech_idx < len(speeches):
                 display_text = speeches[speech_idx].replace("<add>", "").strip()
                 with st.expander("Speech Preview", expanded=True):
                     st.caption(display_text)
    
    with c_r:
        st.subheader("Editors")
        tabs = st.tabs(["Content", "Speech", "Title", "Base", "⭐ AI Voice", "⭐ AI Beautify", "⭐ AI Enrich"])
        
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
        
        with tabs[5]:
            #  st.header("AI Visual Beautification")
             st.info("Enhance content using VLM.")
            #  st.markdown("The AI will analyze the slide image and LaTeX code, then optimize the layout and styling iteratively.")
             
             rounds = st.number_input("Optimization Rounds", min_value=1, max_value=5, value=3)
             
             if st.button("GO!", type="primary"):
                 _batch_beautify_slides(rounds)
                 st.rerun()
        
        with tabs[6]:
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

            if st.button("Enrich References"):
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

                        # Ensure logic_chain is a dict and deep copy it to avoid modifying session state
                        if logic_chain is None:
                            logic_chain = {"nodes": [], "edges": []}
                        else:
                            import copy
                            logic_chain = copy.deepcopy(logic_chain)

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
                        
                        st.session_state.reference_graph_data = res
                        st.success(f"Slide Graph generated! Saved to {out_path}")
                        
                        # Rerun to refresh speech editor content and show graph
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.text(traceback.format_exc())

            # st.divider()
            # st.write("### HTML Slide Generation")
            st.info("Dynamic Slide Generation.")
            
            # st.write("**Focus Zoom (Image Slides)**")
            fz_enabled = st.checkbox("Enable VLM focus zoom", value=True, key="html_focus_zoom_enabled")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                fz_max_regions = st.number_input("Max Regions", min_value=2, max_value=8, value=5, key="html_focus_zoom_max_regions")
            with c2:
                fz_interval_ms = st.number_input("Interval (ms)", min_value=800, max_value=8000, value=2000, step=200, key="html_focus_zoom_interval")
            with c3:
                fz_scale = st.number_input("Scale", min_value=1.05, max_value=2.50, value=1.40, step=0.05, key="html_focus_zoom_scale")
            with c4:
                fz_cache = st.checkbox("Cache Regions", value=True, key="html_focus_zoom_cache")

            st.session_state.html_focus_zoom_cfg = {
                "enabled": bool(fz_enabled),
                "max_regions": int(fz_max_regions),
                "interval_ms": int(fz_interval_ms),
                "scale": float(fz_scale),
                "cache": bool(fz_cache),
            }
            if st.button("Generate!"):
                 with st.spinner("Generating HTML via AI Agent..."):
                     try:
                         with open(files["tex"], "r") as f: c_tex = f.read()
                         with open(files["speech"], "r") as f: s_txt = f.read()
                         if isinstance(c_tex, bytes): c_tex = c_tex.decode("utf-8")
                         if isinstance(s_txt, bytes): s_txt = s_txt.decode("utf-8")
                         speeches = s_txt.split("<next>")
                         pdf_pages = st.session_state.preview_state.get("pdf_pages", [])
                         
                         full_html = generate_html_via_llm_iterative(c_tex, speeches, pdf_pages)
                         
                         if full_html:
                             st.session_state.html_slides_content = full_html
                             st.success("HTML Slide generated by AI!")
                         else:
                             st.error("AI generation failed.")
                     except Exception as e:
                         st.error(f"Error reading files: {e}")
            
            if "html_slides_content" in st.session_state:
                with st.expander("HTML Slide Preview", expanded=True):
                    # Inject sync script
                    curr = st.session_state.preview_state.get("current_page", 0)
                    synced_html = inject_reveal_slide_control(st.session_state.html_slides_content, curr)
                    
                    # Ensure the HTML container has enough height and is properly rendered
                    _components_html(synced_html, height=600, scrolling=True, key="html_slide_preview")
                    
                    # Option to download HTML
                    st.download_button("Download HTML", synced_html, "presentation.html", "text/html")
    
    # st.divider()
    c_a1, c_a2 = st.columns([1, 1])
    with c_a1:
        if st.button("🔄 Update"):
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
        if st.button("✅ Finish"):
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

# --- Page 4: Preview ---
def render_page_ppt_preview(tmp_base):
    st.title("PPT Preview")
    
    if "tts_error" in st.session_state:
        st.error(st.session_state.tts_error)
        del st.session_state["tts_error"]
        
    files = st.session_state.generated_files

    render_preview_ui()
    
    c_d1, c_d2, c_d3 = st.columns(3)
    with c_d1:
        with open(files["pdf"], "rb") as f: st.download_button("Download PDF", f.read(), "presentation.pdf")
    with c_d2:
        if "speech" in files and os.path.exists(files["speech"]):
            with open(files["speech"], "r", encoding="utf-8") as f:
                st.download_button("Download Speech Script", f.read(), "speech.txt")
    with c_d3:
        if st.button("🔙 Back to Editing"):
            st.session_state.workflow_phase = "EDITING"
            st.rerun()

def main():
    st.set_page_config(page_title="DeepSlide", layout="wide")
    _init_state()
    ensure_asr_model_ready()
    render_sidebar_logs()
    
    preferred_tmp_base = os.path.join(CURRENT_DIR, "tmp_uploads")
    tmp_base = _pick_writable_tmp_dir(preferred_tmp_base)
    if tmp_base != preferred_tmp_base:
        _log(f"Uploads dir not writable: {preferred_tmp_base} -> fallback to {tmp_base}")
    
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
