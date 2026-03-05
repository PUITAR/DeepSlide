import os
import re
import zipfile
from typing import Dict, List


def _zip_dir(src_dir: str, zip_path: str):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    zip_abs = os.path.abspath(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(src_dir):
            for fn in files:
                abs_path = os.path.join(root, fn)
                if os.path.abspath(abs_path) == zip_abs:
                    continue
                if fn.endswith(".pyc"):
                    continue
                if "__pycache__" in root:
                    continue
                rel_path = os.path.relpath(abs_path, src_dir)
                z.write(abs_path, rel_path)


def _zip_paths(items: List[Dict[str, str]], zip_path: str):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for it in items:
            src = it.get("src")
            arc = it.get("arc")
            if not src or not arc:
                continue
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for fn in files:
                        if fn.endswith(".pyc"):
                            continue
                        if "__pycache__" in root:
                            continue
                        abs_path = os.path.join(root, fn)
                        rel = os.path.relpath(abs_path, src)
                        z.write(abs_path, os.path.join(arc, rel))
            elif os.path.isfile(src):
                z.write(src, arc)


def _safe_int_from_filename(fn: str) -> int:
    m = re.search(r"(\d+)", fn)
    return int(m.group(1)) if m else 10**9
