from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OCRConfig:
    provider: str
    url: str
    mode: str
    timeout_seconds: int
    render_dpi: int
    text_min_chars: int
    vlm_platform: str
    vlm_model: str
    vlm_api_url: str
    vlm_api_key: str
    vlm_prompt: str


def load_ocr_config() -> OCRConfig:
    provider = (os.getenv("EVAL_OCR_PROVIDER") or "").strip().lower()
    url = (os.getenv("EVAL_OCR_URL") or "").strip()
    mode = (os.getenv("EVAL_OCR_MODE") or "auto").strip().lower()
    timeout_seconds = int((os.getenv("EVAL_OCR_TIMEOUT_SECONDS") or "60").strip())
    render_dpi = int((os.getenv("EVAL_RENDER_DPI") or "200").strip())
    text_min_chars = int((os.getenv("EVAL_OCR_TEXT_MIN_CHARS") or "40").strip())

    vlm_platform = (os.getenv("DEFAULT_VLM_PLATFORM_TYPE") or "").strip().lower()
    vlm_model = (os.getenv("DEFAULT_VLM_TYPE") or "").strip()
    vlm_api_url = (os.getenv("DEFAULT_VLM_API_URL") or "").strip()
    vlm_api_key = (os.getenv("DEFAULT_VLM_API_KEY") or "").strip()
    vlm_prompt = (os.getenv("EVAL_OCR_PROMPT") or "").strip()
    if not vlm_prompt:
        vlm_prompt = "请做OCR识别：提取图片中的所有可见文字，按阅读顺序输出纯文本。不要解释、不要总结、不要输出多余内容。"

    if not provider:
        if url:
            provider = "rest"
        elif vlm_platform in {"aliyun", "dashscope"} and vlm_api_key and vlm_model:
            provider = "aliyun_vlm"
        else:
            provider = "none"

    return OCRConfig(
        provider=provider,
        url=url,
        mode=mode,
        timeout_seconds=timeout_seconds,
        render_dpi=render_dpi,
        text_min_chars=text_min_chars,
        vlm_platform=vlm_platform,
        vlm_model=vlm_model,
        vlm_api_url=vlm_api_url,
        vlm_api_key=vlm_api_key,
        vlm_prompt=vlm_prompt,
    )
