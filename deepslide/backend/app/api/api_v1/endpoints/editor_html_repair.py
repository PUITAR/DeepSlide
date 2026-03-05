import html
import os
import re
import urllib.parse


def _safe_placeholder_data_uri(label: str = "Missing image") -> str:
    txt = html.escape(str(label or "Missing image"))[:40]
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='675' viewBox='0 0 1200 675'>"
        "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0' stop-color='#0ea5e9' stop-opacity='.18'/>"
        "<stop offset='1' stop-color='#a855f7' stop-opacity='.16'/></linearGradient></defs>"
        "<rect x='0' y='0' width='1200' height='675' fill='url(#g)'/>"
        "<rect x='48' y='48' width='1104' height='579' rx='34' fill='rgba(255,255,255,.42)' stroke='rgba(15,23,42,.14)'/>"
        "<g fill='rgba(15,23,42,.66)' font-family='ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial'>"
        f"<text x='96' y='130' font-size='26' font-weight='800'>{txt}</text>"
        "<text x='96' y='170' font-size='16' font-weight='600'>Source image unavailable (placeholder)</text>"
        "</g></svg>"
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def _is_probably_placeholder_png(abs_path: str) -> bool:
    try:
        if not abs_path:
            return False
        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            return False
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            return False
        if os.path.getsize(abs_path) > 50_000:
            return False
        from PIL import Image

        with Image.open(abs_path) as im:
            im = im.convert("RGB")
            im = im.resize((32, 32))
            px = list(im.getdata())
        if not px:
            return False
        base = (226, 232, 240)
        max_dev = 0
        max_span = 0
        for c in range(3):
            vals = [p[c] for p in px]
            max_span = max(max_span, max(vals) - min(vals))
            max_dev = max(max_dev, max(abs(v - base[c]) for v in vals))
        return max_span <= 6 and max_dev <= 10
    except Exception:
        return False


def patch_html_doc_for_repair(doc: str, project_id: str, project_path: str) -> str:
    out = str(doc or "")

    out = re.sub(r"<img[^>]*src=(['\"])[^'\"]*/preview/[^'\"]*\1[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"url\((['\"])?[^)\"']*/preview/[^)\"']*\1\)", "none", out, flags=re.IGNORECASE)
    out = out.replace("assets/page_image_path", "")
    out = out.replace("assets.page_image_path", "")

    out = re.sub(
        r"<div(?![^>]*\bstyle=)([^>]*\bclass=(['\"])[^'\"]*\bimage-placeholder\b[^'\"]*\2[^>]*)>",
        lambda m: (
            f"<div{m.group(1)} style=\"background:linear-gradient(135deg, rgba(14,165,233,.14), rgba(168,85,247,.12));"
            "border:1px solid rgba(148,163,184,.25);\">"
        ),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"<div(?![^>]*\bstyle=)([^>]*\bclass=(['\"])[^'\"]*\bfx-image-focus-placeholder\b[^'\"]*\2[^>]*)>",
        lambda m: (
            f"<div{m.group(1)} style=\"background:linear-gradient(135deg, rgba(14,165,233,.14), rgba(168,85,247,.12));"
            "border:1px solid rgba(148,163,184,.25);\">"
        ),
        out,
        flags=re.IGNORECASE,
    )

    def _replace_placeholder_asset_img(m: re.Match) -> str:
        prefix = m.group(1)
        quote = m.group(2)
        qp = m.group(3)
        rel = urllib.parse.unquote(str(qp or ""))
        rel = rel.lstrip("/")
        abs_path = os.path.abspath(os.path.join(project_path, rel))
        if _is_probably_placeholder_png(abs_path):
            ph = _safe_placeholder_data_uri("Missing image")
            return f"{prefix}{quote}{ph}{quote}"
        return m.group(0)

    out = re.sub(
        rf'(<img[^>]*\ssrc=)(["\'])/api/v1/projects/{re.escape(project_id)}/asset\?path=([^"\']+)\2',
        _replace_placeholder_asset_img,
        out,
        flags=re.IGNORECASE,
    )
    return out

