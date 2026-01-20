import os
import re
import json
import fitz
import streamlit as st
from compiler import Compiler
from core import _log
from ppt_core import extract_frame_by_index, replace_frame_in_content, parse_resp_for_editor

def _requirements_json() -> dict:
    override = st.session_state.get("requirements_override")
    if override: return override
    req = st.session_state.collector.get_requirements()
    return req.get("conversation_requirements") or {}

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
    is_added = "<add>" in current_speech
    
    # 1. Determine Allowed Actions based on permissions
    allowed_actions = []
    
    # Title Page
    if page_idx == 0:
        allowed_actions = ["MODIFY_TITLE_CONTENT", "MODIFY_SPEECH"]
    # Added (non-Title)
    elif is_added:
        allowed_actions = ["MODIFY_SPEECH"]
    # Content Page
    else:
        allowed_actions = ["MODIFY_SLIDE_CONTENT", "MODIFY_SPEECH"]
        
    _log(f"Page {page_idx} (Added={is_added}) Allowed: {allowed_actions}")

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
