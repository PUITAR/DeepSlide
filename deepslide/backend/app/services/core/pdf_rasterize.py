import hashlib
import os
from typing import Optional


def pdf_first_page_to_png(abs_pdf_path: str, out_dir: str, *, dpi: int = 180) -> str:
    p = os.path.abspath(str(abs_pdf_path or ""))
    if not p or not os.path.exists(p) or not os.path.isfile(p):
        return ""
    if os.path.splitext(p)[1].lower() != ".pdf":
        return ""

    try:
        st = os.stat(p)
        sig = f"{p}|{int(st.st_mtime)}|{int(st.st_size)}|dpi={int(dpi)}"
    except Exception:
        sig = f"{p}|dpi={int(dpi)}"

    os.makedirs(out_dir, exist_ok=True)
    base = hashlib.sha1(sig.encode("utf-8", errors="ignore")).hexdigest()[:16]
    out = os.path.abspath(os.path.join(out_dir, f"{base}.png"))

    try:
        if os.path.exists(out) and os.path.isfile(out):
            try:
                if os.path.getmtime(out) >= os.path.getmtime(p):
                    return out
            except Exception:
                return out
    except Exception:
        pass

    try:
        import fitz  # type: ignore
    except Exception:
        return ""

    try:
        doc = fitz.open(p)
        try:
            if doc.page_count <= 0:
                return ""
            page = doc.load_page(0)
            mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(out)
            return out if os.path.exists(out) else ""
        finally:
            try:
                doc.close()
            except Exception:
                pass
    except Exception:
        return ""

