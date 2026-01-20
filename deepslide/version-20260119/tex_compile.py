import os
import subprocess
from typing import Optional, List, Dict, Any

from content import Content
from frame import Frame
from section import Section

import re

def _parse_log_for_errors(log_path: str, err_line_ext: int = 10) -> List[Dict[str, Any]]:
    """
    Enhanced log parser that extracts errors with accurate file context.
    """
    if not os.path.isfile(log_path):
        return []
    
    errors: List[Dict[str, Any]] = []
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        # Regex for file entry: (./filename.tex or (/path/filename.tex
        file_stack = []
        file_entry_pattern = re.compile(r'\((?P<path>[^)\s]+\.tex)')
        
        for i, line in enumerate(lines):
            # 1. Update file stack heuristic
            # Check for file entry
            m = file_entry_pattern.search(line)
            if m:
                fpath = m.group('path')
                fname = os.path.basename(fpath)
                file_stack.append(fname)
            
            # Check for file exit (heuristic)
            if line.strip().startswith(')') or line.strip() == ')':
                if file_stack:
                    file_stack.pop()

            # 2. Check for errors
            s = line.strip()
            if s.startswith("!") or "LaTeX Error" in s:
                # Basic line extraction
                ln = None
                
                # Look ahead/behind for line number (l.123)
                context_start = max(0, i - err_line_ext)
                context_end = min(len(lines), i + err_line_ext + 1)
                
                for j in range(context_start, context_end):
                    # LaTeX log line numbers format: "l.123 <context>"
                    m_ln = re.search(r"\bl\.(\d+)\b", lines[j])
                    if m_ln:
                        ln = int(m_ln.group(1))
                        break
                
                # Determine file from stack
                current_file = file_stack[-1] if file_stack else "unknown"
                
                # Special handling for "content.tex" vs "base.tex" if stack is empty
                # Usually compilation starts with base.tex
                if current_file == "unknown":
                    current_file = "base.tex"

                errors.append({
                    "message": s, 
                    "line": ln, 
                    "file": current_file,
                    "log_line_index": i
                })
                
                if len(errors) >= 10: break
                
    except Exception as e:
        print(f"parse log for errors error: {e}")
        pass
        
    return errors


def _translate_to_docker_path(host_path: str) -> str:
    # host_root = "/home/ym/DeepSlide"
    host_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    container_root = "/app"
    if host_path.startswith(host_root):
        return host_path.replace(host_root, container_root, 1)
    return host_path


def compile_content(base_dir: str) -> Dict[str, Any]:
    base_tex_path = os.path.join(base_dir, "base.tex")
    content_tex_path = os.path.join(base_dir, "content.tex")

    try:
        content = Content()
        content.from_file(content_tex_path)
    except Exception:
        return {"success": False, "errors": [{"message": "content.tex not found", "line": None}]}   

    mapping = content.to_file(content_tex_path)
    if not mapping:
        return {"success": False, "errors": [{"message": "content.tex is empty or not valid", "line": None}]}   

    # Always use docker for now as requested
    engine = "docker_xelatex"
    run_script = os.path.join(os.path.dirname(__file__), "run_in_docker.sh")

    if not os.path.exists(run_script):
            return {"success": False, "errors": [{"message": f"Docker script not found: {run_script}", "line": None}]}
    
    # Command to run inside docker:
    # We use 'bash -c' to handle cd and multiple commands safely
    container_base_dir = _translate_to_docker_path(base_dir)
    base_filename = os.path.basename(base_tex_path)
    base_name_no_ext = os.path.splitext(base_filename)[0]
    
    latex_cmd = f"cd {container_base_dir} && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    
    # Check for ref.bib to enable citations
    if os.path.exists(os.path.join(base_dir, "ref.bib")):
        # Full build sequence: xelatex -> bibtex -> xelatex -> xelatex
        latex_cmd += f" && bibtex {base_name_no_ext} && xelatex -interaction=nonstopmode -halt-on-error {base_filename} && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    else:
        # Simple double pass for TOC/ref resolution
        latex_cmd += f" && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    
    cmd = ["bash", run_script, latex_cmd]
    
    try:
        # If using docker chain, we only need 1 run (since the chain handles multiple passes)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        return {"success": False, "errors": {
            "message": str(e), "line": None
        }}

    log_path = os.path.join(base_dir, "base.log")
    pdf_path = os.path.join(base_dir, "base.pdf")
    errors = _parse_log_for_errors(log_path)

    if proc.returncode != 0 and not errors:
        # If compilation failed but no errors parsed from log, maybe log was not generated or parsing failed
        # Include stdout in errors for debugging

        # TODO fix bug: code 2 but the compile is actually successful
        if proc.returncode == 2 and not errors:
            return {"success": True, "errors": []}

        output = proc.stdout.decode('utf-8', errors='ignore') if proc.stdout else "No output"
        print(f"Compilation Failed with return code {proc.returncode}. Output:\n{output[:1000]}...")
        # Force an error so AI Agent can look at it
        return {"success": False, "errors": [{"message": f"Compilation failed with code {proc.returncode}. Log parsing found no standard errors. Check base.log.", "line": None, "file": "unknown"}]}

    errors = [
        {"message": e.get("message"), "line": e.get("line"), "file": e.get("file")} for e in errors
    ]

    return {"success": (proc.returncode == 0) and os.path.isfile(pdf_path), "errors": errors}

def replace_content(base_dir: str, idx: int, item: Optional[Frame | Section] = None) -> bool:
    content_tex_path = os.path.join(base_dir, "content.tex")

    content = Content()
    content.from_file(content_tex_path)

    try:
        # print(f"Replace content at index {idx} with {item}")
        content[idx] = item
    except Exception as e:
        print(f"Replace content error: {e}")
        return False

    result = content.to_file(content_tex_path)

    if not result:
        return False
    
    return True


def update_title(base_dir: str, title_info: str):
    title_tex_path = os.path.join(base_dir, "title.tex")
    try:
        with open(title_tex_path, "w", encoding="utf-8") as f:
            f.write(title_info)
    except Exception:
        return False

    return True

def update_base(base_dir: str, base_info: str):
    base_tex_path = os.path.join(base_dir, "base.tex")
    try:
        with open(base_tex_path, "w", encoding="utf-8") as f:
            f.write(base_info)
    except Exception:
        return False

    return True
