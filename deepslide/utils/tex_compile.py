import os
import shutil
import subprocess
from typing import Optional, List, Dict, Any, Tuple

from deepslide.utils.content import Content
from deepslide.utils.frame import Frame
from deepslide.utils.section import Section

from pprint import pprint

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
        n = len(lines)
        import re
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("!") or "LaTeX Error" in s:
                ln = None
                ff = None
                for j in range(max(0, i - err_line_ext), min(i + err_line_ext, n)):
                    # 文件
                    m_fi = re.search(r"\b([a-zA-Z0-9_./\\-]+)\.tex\b", lines[j])
                    m_ln = re.search(r"\bl\.(\d+)\b", lines[j])
                    if m_fi:
                        ff = str(m_fi.group(1))
                    if m_ln:
                        ln = int(m_ln.group(1))

                # print(f"helper: {helper}")
                file_helper = helper.get('file', None) if helper is not None else None
                # print(f"file_helper: {file_helper}")
                # print(f"ff: {ff}")

                if ff is None:
                    if file_helper is not None:
                        ff = str(file_helper)
                    else:
                        # 如果没有找到错误文件匹配，默认是 content.tex
                        print(f"WARNING: no file match for error: {s}")
                        ff = "content"
                        
                errors.append({"message": s, "line": ln, "file": ff})
    except Exception as e:
        print(f"parse log for errors error: {e}")
        pass
    return errors


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

    engine = _detect_engine(base_dir, CANDIDATE_ENGINES)

    if engine is None:
        return {"success": False, "errors": [{"message": "latex engine not found", "line": None}]} 

    cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", os.path.basename(base_tex_path)]

    try:
        last_proc = None
        for _ in range(2):
            last_proc = subprocess.run(cmd, cwd=base_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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

    errors = [
        {"message": e.get("message"), "line": e.get("line"), "file": e.get("file")} for e in errors
    ]

    for e in errors:
        error_file = e.get("file")
        # print(f"error_file: {error_file}")
        # title.tex 错误
        if error_file == "title":
            break
        elif error_file == "content": 
            # content.tex 错误
            ln = e.get("line")
            if ln is None:
                continue
            for idx, (start, end, typ) in enumerate(mapping):
                # print(f"line {ln} in {typ} [{start}, {end}]")
                if start <= ln <= end:
                    e["idx"] = idx
                    # print(f"line {ln} in {typ} [{start}, {end}] -> idx {idx}")
                    break
        
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