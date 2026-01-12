import os
import shutil
import subprocess
from typing import Optional, List, Dict, Any, Tuple

from content import Content
from frame import Frame
from section import Section

from pprint import pprint

import re

CANDIDATE_ENGINES = ["xelatex", "pdflatex"]

def _detect_engine(base_dir: str, candidate_engines: List[str] = ["xelatex", "pdflatex"]) -> Optional[str]:
    base_tex = os.path.join(base_dir, "base.tex")
    '''
    base.tex may contain the following lines to specify the encoding and engine:
        %!TeX encoding = UTF-8
        %!TeX program = xelatex
    '''
    try:
        with open(base_tex, "r", encoding="utf-8") as f:
            head = f.read(512)
        if "TeX program = xelatex" in head:
            p = shutil.which("xelatex")
            if p:
                return p
    except Exception:
        pass

    for eng in candidate_engines:
        path = shutil.which(eng)
        if path:
            return path
    return None

def _parse_log_for_errors(log_path: str, err_line_ext: int = 10, helper: dict[str, Any] = None) -> List[Dict[str, Any]]:
    if not os.path.isfile(log_path):
        return []
    errors: List[Dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        # Simplified parser: Just grab error messages and line numbers roughly.
        # We rely on the AI Agent (scan_latex_log) for precise file/line context.
        # This function now serves as a quick fail-detector.
        
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("!") or "LaTeX Error" in s:
                # Basic line extraction
                ln = None
                start = max(0, i - err_line_ext)
                end = min(len(lines), i + err_line_ext + 1)
                for j in range(start, end):
                    if j == i:
                        continue  # 跳过已检查过的当前行
                    m_ln = re.search(r"\bl\.(\d+)\b", lines[j])
                    if m_ln:
                        break
                if m_ln: ln = int(m_ln.group(1))
                
                # Heuristic file guessing (optional, mostly for display)
                ff = "unknown"
                
                errors.append({"message": s, "line": ln, "file": ff})
                
                if len(errors) >= 5: break # Limit errors passed to avoid flooding
                
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


def compile_content(base_dir: str, helper: dict[str, Any] = None) -> Dict[str, Any]:
    base_tex_path = os.path.join(base_dir, "base.tex")
    content_tex_path = os.path.join(base_dir, "content.tex")

    try:
        content = Content()
        content.from_file(content_tex_path)
    except Exception:
        return {"success": False, "errors": [{"message": "content.tex not found", "line": None}]}   

    # mapping = _write_content_with_index(content, content_tex_path)
    mapping = content.to_file(content_tex_path)
    if not mapping:
        return {"success": False, "errors": [{"message": "content.tex is empty or not valid", "line": None}]}   

    # engine = _detect_engine(base_dir, CANDIDATE_ENGINES)
    # Always use docker for now as requested
    engine = "docker_xelatex"
    # run_script = "/home/ym/DeepSlide/run_in_docker.sh"
    run_script = os.path.join(os.path.dirname(__file__), "run_in_docker.sh")

    if engine == "docker_xelatex":
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
        
    else:
        if engine is None:
             return {"success": False, "errors": [{"message": "latex engine not found", "line": None}]} 
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", os.path.basename(base_tex_path)]

    try:
        last_proc = None
        # If using docker chain, we only need 1 run (since the chain handles multiple passes)
        run_count = 1 if engine == "docker_xelatex" else 2
        for _ in range(run_count):
            last_proc = subprocess.run(cmd, cwd=base_dir if engine != "docker_xelatex" else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if last_proc.returncode != 0:
                break
        proc = last_proc
    except Exception as e:
        return {"success": False, "errors": {
            "message": str(e), "line": None, "file": None
        }}

    log_path = os.path.join(base_dir, "base.log")
    pdf_path = os.path.join(base_dir, "base.pdf")
    errors = _parse_log_for_errors(log_path, helper=helper)

    if proc.returncode != 0 and not errors:
        # If compilation failed but no errors parsed from log, maybe log was not generated or parsing failed
        # Include stdout in errors for debugging
        output = proc.stdout.decode('utf-8', errors='ignore') if proc.stdout else "No output"
        print(f"Compilation Failed with return code {proc.returncode}. Output:\n{output[:1000]}...")
        # Force an error so AI Agent can look at it
        return {"success": False, "errors": [{"message": f"Compilation failed with code {proc.returncode}. Log parsing found no standard errors. Check base.log.", "line": None, "file": "unknown"}]}

    errors = [
        {"message": e.get("message"), "line": e.get("line"), "file": e.get("file")} for e in errors
    ]

    # Clean up heuristic logic that tried to map lines to content index
    # Now we just return the raw errors and let the Agent handle mapping
    
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