import os
import logging
import re
import json
import uuid
import tempfile
import io
import base64
import mimetypes
from typing import List, Optional
from urllib.parse import urlparse
import fitz
from PIL import Image, ImageFilter, ImageOps
import dashscope

from app.services.core.ppt_core import parse_resp_for_editor
from app.core.agent_model_env import resolve_vlm_env

logger = logging.getLogger(__name__)
_VLM_CALL_CFG_LOGGED = False


def _vlm_platform() -> str:
    p = str(resolve_vlm_env("VLM_BEAUTIFY").platform_type or "").strip().lower()
    return p or "aliyun"


def _vlm_model() -> str:
    return str(resolve_vlm_env("VLM_BEAUTIFY").model_type or "").strip() or "qwen-vl-max"


def _is_qwen_model(name: str) -> bool:
    t = str(name or "").strip().lower()
    return t.startswith("qwen") or t.startswith("qwen-") or "qwen" in t


def _encode_image_data_url(abs_path: str) -> str:
    p = os.path.abspath(str(abs_path or ""))
    if not p or not os.path.exists(p) or not os.path.isfile(p):
        return ""
    try:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            max_side = max(w, h)
            if max_side > 1280:
                scale = 1280.0 / float(max_side)
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                im = im.resize((nw, nh), Image.LANCZOS)

            bio = io.BytesIO()
            mt = "image/png"
            try:
                im.save(bio, format="PNG", optimize=True)
                b = bio.getvalue()
            except Exception:
                b = b""

            if not b or len(b) > 3_000_000:
                bio = io.BytesIO()
                mt = "image/jpeg"
                im.convert("RGB").save(bio, format="JPEG", quality=85, optimize=True)
                b = bio.getvalue()

            return f"data:{mt};base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        mt = mimetypes.guess_type(p)[0] or "image/png"
        if not mt.startswith("image/"):
            mt = "image/png"
        with open(p, "rb") as f:
            b = f.read()
        return f"data:{mt};base64," + base64.b64encode(b).decode("ascii")


def _call_vlm(image_path: str, prompt_text: str, *, expect_json: bool) -> str:
    global _VLM_CALL_CFG_LOGGED
    cfg = resolve_vlm_env("VLM_BEAUTIFY")
    api_key = cfg.api_key
    if not api_key:
        return ""
    api_url = cfg.api_url or ""
    model_type = str(cfg.model_type or "").strip() or "qwen-vl-max"

    platform = str(cfg.platform_type or "").strip().lower() or "aliyun"
    use_dashscope = platform in {"aliyun", "dashscope"} or _is_qwen_model(model_type)
    if not _VLM_CALL_CFG_LOGGED:
        try:
            host = urlparse(api_url).netloc if api_url else ""
            logger.info(f"VLM call config: platform={platform} model={model_type} transport={'dashscope' if use_dashscope else 'openai_compatible'} base_url_host={host}")
        except Exception:
            logger.info(f"VLM call config: platform={platform} model={model_type} transport={'dashscope' if use_dashscope else 'openai_compatible'}")
        _VLM_CALL_CFG_LOGGED = True
    if use_dashscope:
        if api_url:
            dashscope.base_http_api_url = api_url
        local_file_url = f"file://{os.path.abspath(image_path)}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": local_file_url},
                    {"text": str(prompt_text or "")},
                ],
            }
        ]
        try:
            resp = dashscope.MultiModalConversation.call(
                api_key=api_key,
                model=model_type,
                messages=messages,
                result_format="message",
            )
        except Exception as e:
            logger.warning(f"vlm dashscope call failed: {e}")
            return ""

        try:
            if getattr(resp, "status_code", None) != 200:
                return ""
            content = resp.output.choices[0].message.content
            if isinstance(content, list):
                text = ""
                for it in content:
                    if isinstance(it, dict) and "text" in it:
                        text += str(it["text"])
                return text
            return str(content)
        except Exception:
            return ""

    img_url = _encode_image_data_url(image_path)
    if not img_url:
        return ""

    try:
        from openai import OpenAI
    except Exception as e:
        logger.warning(f"openai package not available for VLM: {e}")
        return ""

    try:
        client = OpenAI(api_key=api_key, base_url=api_url or None)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(prompt_text or "")},
                    {"type": "image_url", "image_url": {"url": img_url}},
                ],
            }
        ]
        create_kwargs = {
            "model": model_type,
            "messages": messages,
        }
        if expect_json:
            create_kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = client.chat.completions.create(**create_kwargs)
        except TypeError:
            create_kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**create_kwargs)
        except Exception:
            if expect_json:
                try:
                    create_kwargs.pop("response_format", None)
                    resp = client.chat.completions.create(**create_kwargs)
                except Exception as e2:
                    logger.warning(f"vlm openai-compatible call failed: {e2}")
                    return ""
            else:
                raise

        return str(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning(f"vlm openai-compatible call failed: {e}")
        return ""


def beautify_frame_from_image(image_path: str, latex_frame: str, base_dir: str = "") -> str:
    prompt = (
        "You are a Presentation Design Expert. "
        "Analyze the slide image and the corresponding LaTeX code. "
        "Your tasks are:\n"
        "1. Layout: Prevent any element overlap. If the content in `latex_code` does not fully appear in the image, it means there is too much content beyond the display range, and simplification or reduction is needed. \n"
        "2. Images: Check if images are too small or too large. Resize them to fit the slide comfortably.\n"
        "3. Content Density: Check if the slide has too much text (cluttered) or too little (empty). Balance the whitespace.\n"
        "4. Safety: DO NOT introduce any placeholder blocks (e.g., solid rectangles), colored boxes, or new images that do not exist in the project.\n"
        "Suggestions:\n"
        "- Do NOT use \\Large or \\textbf manually for slide titles inside the content area. Use \\frametitle{...} or \\framesubtitle{...} instead.\n"
        "- Do NOT add any footers or signatures.\n"
        "Return ONLY the modified \\begin{frame}...\\end{frame} block in ```latex``` code block."
    )

    text = _call_vlm(
        image_path,
        f"{prompt}\n\nCurrent LaTeX:\n```latex\n{latex_frame}\n```",
        expect_json=False,
    )
    if not text:
        return ""

    try:
        parsed = (parse_resp_for_editor(text) or "").strip()

        if "\\begin{frame}" not in parsed or "\\end{frame}" not in parsed:
            return ""

        if re.search(r"\\colorbox\{\s*red\s*\}|\\color\{\s*red\s*\}", parsed, flags=re.IGNORECASE):
            return ""

        if base_dir:
            paths = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", parsed)
            for p in paths:
                p2 = (p or "").strip()
                if not p2:
                    continue
                cand = [
                    p2,
                    os.path.join(base_dir, p2),
                    os.path.join(base_dir, os.path.basename(p2)),
                    os.path.join(base_dir, "picture", os.path.basename(p2)),
                ]
                if not any(c and os.path.exists(c) for c in cand):
                    return ""

        return parsed
    except Exception:
        return ""


# -------------------------------------------------------------------------
# Image Focus Templates (Deterministic Selection)
# -------------------------------------------------------------------------

FOCUS_TEMPLATES = [
    {"id": "LR_50_50", "description": "Two equal vertical columns (left/right).", "regions": [[0.0, 0.0, 0.5, 1.0], [0.5, 0.0, 0.5, 1.0]]},
    {"id": "TB_50_50", "description": "Two equal horizontal rows (top/bottom).", "regions": [[0.0, 0.0, 1.0, 0.5], [0.0, 0.5, 1.0, 0.5]]},

    {"id": "LR_33_67", "description": "Left narrow (1/3) + right wide (2/3).", "regions": [[0.0, 0.0, 0.333, 1.0], [0.333, 0.0, 0.667, 1.0]]},
    {"id": "LR_67_33", "description": "Left wide (2/3) + right narrow (1/3).", "regions": [[0.0, 0.0, 0.667, 1.0], [0.667, 0.0, 0.333, 1.0]]},
    {"id": "TB_33_67", "description": "Top narrow (1/3) + bottom wide (2/3).", "regions": [[0.0, 0.0, 1.0, 0.333], [0.0, 0.333, 1.0, 0.667]]},
    {"id": "TB_67_33", "description": "Top wide (2/3) + bottom narrow (1/3).", "regions": [[0.0, 0.0, 1.0, 0.667], [0.0, 0.667, 1.0, 0.333]]},

    {"id": "COLS_3", "description": "Three equal vertical columns (3 columns, 1 row).", "regions": [[0.0, 0.0, 0.333, 1.0], [0.333, 0.0, 0.333, 1.0], [0.667, 0.0, 0.333, 1.0]]},
    {"id": "ROWS_3", "description": "Three equal horizontal rows (1 column, 3 rows).", "regions": [[0.0, 0.0, 1.0, 0.333], [0.0, 0.333, 1.0, 0.333], [0.0, 0.667, 1.0, 0.333]]},

    {"id": "GRID_2X2", "description": "2X2 grid (four quadrants).", "regions": [[0.0, 0.0, 0.5, 0.5], [0.5, 0.0, 0.5, 0.5], [0.0, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]]},
    {"id": "BENTO_SIDEBAR_L", "description": "Left sidebar (1/4) + right main split (top/bottom).", "regions": [[0.0, 0.0, 0.25, 1.0], [0.25, 0.0, 0.75, 0.5], [0.25, 0.5, 0.75, 0.5]]},
    {"id": "BENTO_SIDEBAR_R", "description": "Right sidebar (1/4) + left main split (top/bottom).", "regions": [[0.0, 0.0, 0.75, 0.5], [0.0, 0.5, 0.75, 0.5], [0.75, 0.0, 0.25, 1.0]]},
]

def get_regions_by_template(template_id: str) -> List[List[float]]:
    """Returns the regions for a given template ID."""
    tid = str(template_id or "").strip().upper()
    if tid:
        norm = []
        prev_us = False
        for ch in tid:
            ok = ("A" <= ch <= "Z") or ("0" <= ch <= "9")
            if ok:
                norm.append(ch)
                prev_us = False
            else:
                if not prev_us:
                    norm.append("_")
                    prev_us = True
        tid = "".join(norm).strip("_")
    for t in FOCUS_TEMPLATES:
        if t["id"] == tid:
            return t["regions"]
    # Fallback to GRID_2X2
    return [[0.0, 0.0, 0.5, 0.5], [0.5, 0.0, 0.5, 0.5], [0.0, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]]

def get_focus_regions(slide_image_path_or_bytes, speech_text: str, max_regions: int = 5, prefer_vlm: bool = True):
    """
    Legacy entry point. Now just returns a default or could be wired to a heuristic.
    But for now, we prefer Agent-based selection.
    """
    return get_regions_by_template("GRID_2X2")
