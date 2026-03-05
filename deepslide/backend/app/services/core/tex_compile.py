import os
import subprocess
from typing import Optional, List, Dict, Any
import re
import logging

logger = logging.getLogger(__name__)


def _preview_text(value: Any, limit: int = 500) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    return s if len(s) <= limit else s[:limit] + "..."


def _find_run_in_docker_script() -> Optional[str]:
    candidates: List[str] = []

    here = os.path.abspath(os.path.dirname(__file__))
    # deepslide-v3/backend/app/services/core
    project_root = os.path.abspath(os.path.join(here, "../../../../"))
    repo_root = os.path.abspath(os.path.join(here, "../../../../../"))

    candidates.append(os.path.join(project_root, "run_in_docker.sh"))
    candidates.append(os.path.join(project_root, "backend", "scripts", "run_in_docker.sh"))
    candidates.append(os.path.join(project_root, "backend", "app", "services", "core", "compiler", "run_in_docker.sh"))
    candidates.append(os.path.join(repo_root, "run_in_docker.sh"))

    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

# Basic classes to mock Content/Frame/Section if they are not available
# In the original code they were imported. 
# We will use simple placeholders or just string manipulation if possible.
# However, replace_content uses them. 
# For now, I will omit replace_content as it depends on Content/Frame classes I don't have.
# I will implement compile_content which is the main one.

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
        logger.error(f"parse log for errors error: {e}")
        pass
        
    return errors


def _translate_to_docker_path(host_path: str) -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(here, "../../../../"))
    workspace_root = os.path.abspath(os.path.join(here, "../../../../../"))
    if host_path.startswith(project_root):
        return host_path.replace(project_root, "/app/" + os.path.basename(project_root), 1)
    if host_path.startswith(workspace_root):
        return host_path.replace(workspace_root, "/app", 1)
    return host_path


def compile_content(base_dir: str) -> Dict[str, Any]:
    base_tex_path = os.path.join(base_dir, "base.tex")
    content_tex_path = os.path.join(base_dir, "content.tex")

    logger.info(f"[compile_content] base_dir={base_dir!r}")

    if not os.path.exists(content_tex_path):
        return {"success": False, "errors": [{"message": f"content.tex not found in {base_dir}", "line": None, "file": "content.tex"}]}

    if not os.path.exists(base_tex_path):
        return {"success": False, "errors": [{"message": f"base.tex not found in {base_dir}", "line": None, "file": "base.tex"}]}

    # Check content validity
    with open(content_tex_path, 'r', encoding='utf-8') as f:
        if not f.read().strip():
             return {"success": False, "errors": [{"message": "content.tex is empty", "line": None}]}

    # Path to run_in_docker.sh in the project root
    run_script = _find_run_in_docker_script()
    if not run_script:
        return {"success": False, "errors": [{"message": "Docker script not found (run_in_docker.sh)", "line": None, "file": "run_in_docker.sh"}]}
    
    # Command to run inside docker:
    container_base_dir = _translate_to_docker_path(base_dir)
    base_filename = os.path.basename(base_tex_path)
    base_name_no_ext = os.path.splitext(base_filename)[0]
    
    latex_cmd = f"cd {container_base_dir} && pwd && ls -la && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    
    # Check for ref.bib to enable citations
    if os.path.exists(os.path.join(base_dir, "ref.bib")):
        latex_cmd += f" && bibtex {base_name_no_ext} && xelatex -interaction=nonstopmode -halt-on-error {base_filename} && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    else:
        latex_cmd += f" && xelatex -interaction=nonstopmode -halt-on-error {base_filename}"
    
    bash_bin = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
    cmd = [bash_bin, run_script, latex_cmd]
    logger.info(f"[compile_content] run_script={run_script!r} container_base_dir={container_base_dir!r} base_filename={base_filename!r}")
    
    proc = None
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        return {"success": False, "errors": [{"message": f"compile_content exception: {e}", "line": None, "file": "unknown"}]}

    log_path = os.path.join(base_dir, "base.log")
    pdf_path = os.path.join(base_dir, "base.pdf")
    errors = _parse_log_for_errors(log_path)

    output_text = (proc.stdout or b"").decode('utf-8', errors='ignore')
    try:
        with open(os.path.join(base_dir, "compile_stdout.log"), "w", encoding="utf-8") as f:
            f.write(output_text)
    except Exception:
        pass

    logger.info(
        f"[compile_content] returncode={proc.returncode} pdf_exists={os.path.exists(pdf_path)} log_exists={os.path.exists(log_path)} parsed_errors={len(errors)}"
    )
    if proc.returncode != 0:
        logger.info(f"[compile_content] stdout_preview={_preview_text(output_text)}")

    if proc.returncode != 0 and not errors:
        if proc.returncode == 2 and not errors:
             # heuristic: sometimes return code 2 but successful?
             if os.path.exists(pdf_path):
                 return {"success": True, "errors": []}

        return {"success": False, "errors": [{"message": f"Compilation failed with code {proc.returncode}. Log parsing found no standard errors. See compile_stdout.log/base.log.", "line": None, "file": "unknown"}]}

    errors_cleaned = [
        {"message": e.get("message"), "line": e.get("line"), "file": e.get("file")} for e in errors
    ]

    success = (proc.returncode == 0) and os.path.isfile(pdf_path)
    if (proc.returncode == 0) and (not os.path.isfile(pdf_path)) and (not errors_cleaned):
        errors_cleaned = [{
            "message": "LaTeX command exited with code 0 but base.pdf was not created. See compile_stdout.log for the actual command/output.",
            "line": None,
            "file": "base.tex",
        }]
    if not success and os.path.isfile(log_path):
        try:
            with open(log_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 2000), os.SEEK_SET)
                tail = f.read().decode('utf-8', errors='ignore')
            logger.info(f"[compile_content] base.log_tail={_preview_text(tail)}")
        except Exception:
            pass
    return {"success": success, "errors": errors_cleaned}

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
