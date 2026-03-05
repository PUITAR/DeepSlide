from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests



@dataclass(frozen=True)
class OCRBlock:
    text: str
    conf: Optional[float]
    bbox: Optional[List[float]]


@dataclass(frozen=True)
class OCRResult:
    ok: bool
    full_text: str
    blocks: List[OCRBlock]
    engine_version: str
    elapsed_ms: Optional[int]
    raw: Dict[str, Any]


def call_ocr(url: str, image_path: Path, timeout_seconds: int) -> OCRResult:
    payload = {"image_path": str(image_path)}
    r = requests.post(url, json=payload, timeout=timeout_seconds)
    r.raise_for_status()
    obj = r.json()
    ok = bool(obj.get("ok", True))
    full_text = (obj.get("full_text") or "").strip()
    blocks_raw = obj.get("blocks") or []
    blocks: List[OCRBlock] = []
    for b in blocks_raw:
        if not isinstance(b, dict):
            continue
        blocks.append(OCRBlock(text=(b.get("text") or ""), conf=b.get("conf"), bbox=b.get("bbox")))
    eng_ver = str(obj.get("engine_version") or obj.get("version") or "")
    elapsed = obj.get("elapsed_ms")
    return OCRResult(ok=ok, full_text=full_text, blocks=blocks, engine_version=eng_ver, elapsed_ms=elapsed, raw=obj)


def call_aliyun_vlm_ocr(
    api_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    timeout_seconds: int,
    prompt: str,
) -> OCRResult:
    start = time.time()
    try:
        import dashscope
    except Exception as e:
        raise RuntimeError(f"missing_dashscope: {e}")

    if api_url:
        dashscope.base_http_api_url = api_url

    local_file_url = f"file://{str(image_path.resolve())}"
    messages = [
        {
            "role": "user",
            "content": [
                {"image": local_file_url},
                {"text": prompt},
            ],
        }
    ]
    resp = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=model,
        messages=messages,
        result_format="message",
    )
    elapsed_ms = int((time.time() - start) * 1000)
    raw: Dict[str, Any]
    try:
        raw = resp.to_dict()
    except Exception:
        raw = {"status_code": getattr(resp, "status_code", None)}

    ok = getattr(resp, "status_code", None) == 200
    text = ""
    try:
        content = resp.output.choices[0].message.content
        if isinstance(content, list):
            parts = []
            for it in content:
                if isinstance(it, dict) and "text" in it:
                    parts.append(str(it["text"]))
            text = "".join(parts).strip()
        else:
            text = str(content or "").strip()
    except Exception:
        text = ""

    return OCRResult(
        ok=bool(ok),
        full_text=text,
        blocks=[],
        engine_version=str(getattr(resp, "request_id", "")) or "dashscope",
        elapsed_ms=elapsed_ms,
        raw=raw,
    )


def summarize_blocks(blocks: List[OCRBlock]) -> Tuple[str, Optional[float]]:
    texts = [b.text.strip() for b in blocks if b.text and b.text.strip()]
    full = "\n".join(texts).strip()
    confs = [float(b.conf) for b in blocks if b.conf is not None]
    conf = float(sum(confs) / len(confs)) if confs else None
    return full, conf
