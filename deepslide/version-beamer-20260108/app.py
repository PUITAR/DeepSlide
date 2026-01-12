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
            "1. Layout: Prevent any element overlap. If elements overlap, simplify or reduce content.\n"
            "2. Images: Check if images are too small or too large. Resize them to fit the slide comfortably.\n"
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
            if st.button("Start PPT Generation", type="primary"):
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
        tabs = st.tabs(["Content", "Speech", "Title", "Base", "Voice", "AI Beautify", "Slide Graph"])
        
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
            
            if st.button("Generate Slide Graph"):
                with st.spinner("Generating Slide Graph..."):
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
                        st.json(res)
                        # Rerun to refresh speech editor content
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.text(traceback.format_exc())
    
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
    
    tmp_base = os.path.join(CURRENT_DIR, "tmp_uploads")
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
