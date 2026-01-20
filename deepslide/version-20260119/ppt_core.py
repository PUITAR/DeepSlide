import re
import os
import io
import base64
import fitz
from PIL import Image

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
