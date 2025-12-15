import os
import uuid
import zipfile
import tarfile
import re
from typing import Optional, Tuple
from latex_merger import merge_latex_file

def save_uploaded_file(uploaded_file, base_dir: str) -> str:
    os.makedirs(base_dir, exist_ok=True)
    fname = getattr(uploaded_file, "name", None) or "upload"
    ext = os.path.splitext(fname)[1]
    uid = uuid.uuid4().hex
    out_path = os.path.join(base_dir, f"{uid}{ext}")
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path

def extract_archive(archive_path: str, extract_dir: str) -> str:
    os.makedirs(extract_dir, exist_ok=True)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
        return extract_dir
    try:
        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as t:
                t.extractall(extract_dir)
            return extract_dir
    except tarfile.TarError:
        pass
    return extract_dir

def _contains_documentclass(tex_path: str) -> bool:
    try:
        with open(tex_path, "r", encoding="utf-8") as f:
            content = f.read()
        return "\\documentclass" in content
    except Exception:
        return False

def find_main_tex(root_dir: str) -> Optional[str]:
    candidates = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".tex"):
                full = os.path.join(dirpath, fn)
                if _contains_documentclass(full):
                    candidates.append(full)
    if not candidates:
        return None
    for p in candidates:
        n = os.path.basename(p).lower()
        if n in ("main.tex", "paper.tex", "root.tex"):
            return p
    return sorted(candidates)[0]

def merge_project_to_main(base_dir: str, main_tex_path: str, output_name: str = "merged_main.tex") -> str:
    rel = os.path.relpath(main_tex_path, base_dir)
    merged = merge_latex_file(rel, base_dir)
    out_path = os.path.join(base_dir, output_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(merged)
    return out_path

def extract_abstract_from_text(text: str) -> Optional[str]:
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\\section\*\{\s*Abstract\s*\}(.*?)(?:\\section|\\subsection|\\end\{document\})", text, re.DOTALL | re.IGNORECASE)
    if m2:
        return m2.group(1).strip()
    m3 = re.search(r"\\begin\{摘要\}(.*?)\\end\{摘要\}", text, re.DOTALL)
    if m3:
        return m3.group(1).strip()
    return None

def extract_abstract_from_dir(root_dir: str) -> Optional[str]:
    main = find_main_tex(root_dir)
    targets = []
    if main:
        targets.append(main)
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".tex"):
                full = os.path.join(dirpath, fn)
                targets.append(full)
    seen = set()
    for p in targets:
        if p in seen:
            continue
        seen.add(p)
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            abs_text = extract_abstract_from_text(content)
            if abs_text:
                return abs_text
        except Exception:
            continue
    return None

