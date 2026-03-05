from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgentModelEnv:
    platform_type: str
    model_type: str
    api_url: str
    api_key: str


def _norm_agent_key(agent: str) -> str:
    a = str(agent or "").strip().upper()
    a = re.sub(r"[^A-Z0-9]+", "_", a).strip("_")
    return a or "DEFAULT"


def _get_agent_override(agent: str, field: str) -> Optional[str]:
    k = f"AGENT_{_norm_agent_key(agent)}_{str(field or '').strip().upper()}"
    v = os.getenv(k)
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _pick_env(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v is None:
            continue
        v = str(v).strip()
        if v:
            return v
    return None


def resolve_text_llm_env(agent: str) -> AgentModelEnv:
    platform_type = (
        _get_agent_override(agent, "MODEL_PLATFORM_TYPE")
        or _pick_env("DEFAULT_MODEL_PLATFORM_TYPE")
        or "deepseek"
    )
    model_type = (
        _get_agent_override(agent, "MODEL_TYPE")
        or _pick_env("DEFAULT_MODEL_TYPE")
        or "deepseek-chat"
    )
    api_url = (
        _get_agent_override(agent, "MODEL_API_URL")
        or os.getenv("DEFAULT_MODEL_API_URL")
        or ""
    ).strip()
    api_key = (
        _get_agent_override(agent, "MODEL_API_KEY")
        or _pick_env("DEFAULT_MODEL_API_KEY", "LLM_API_KEY")
        or ""
    )
    return AgentModelEnv(
        platform_type=platform_type,
        model_type=model_type,
        api_url=api_url,
        api_key=api_key,
    )


def resolve_vlm_env(agent: str) -> AgentModelEnv:
    platform_type = (
        _get_agent_override(agent, "VLM_PLATFORM_TYPE")
        or _pick_env("DEFAULT_VLM_PLATFORM_TYPE")
        or "aliyun"
    )
    model_type = (
        _get_agent_override(agent, "VLM_TYPE")
        or _pick_env("DEFAULT_VLM_TYPE")
        or "qwen-vl-max"
    )
    api_url = (
        _get_agent_override(agent, "VLM_API_URL")
        or os.getenv("DEFAULT_VLM_API_URL")
        or ""
    ).strip()
    api_key = _get_agent_override(agent, "VLM_API_KEY") or _pick_env("DEFAULT_VLM_API_KEY") or ""
    return AgentModelEnv(
        platform_type=platform_type,
        model_type=model_type,
        api_url=api_url,
        api_key=api_key,
    )


def resolve_asr_env(agent: str) -> AgentModelEnv:
    platform_type = (
        _get_agent_override(agent, "ASR_PLATFORM_TYPE")
        or _pick_env("DEFAULT_ASR_PLATFORM_TYPE")
        or "aliyun"
    )
    model_type = (
        _get_agent_override(agent, "ASR_TYPE")
        or _pick_env("DEFAULT_ASR_TYPE")
        or "qwen3-asr-flash"
    )
    api_url = (
        _get_agent_override(agent, "ASR_API_URL")
        or os.getenv("DEFAULT_ASR_API_URL")
        or ""
    ).strip()
    api_key = _get_agent_override(agent, "ASR_API_KEY") or _pick_env("DEFAULT_ASR_API_KEY") or ""
    return AgentModelEnv(
        platform_type=platform_type,
        model_type=model_type,
        api_url=api_url,
        api_key=api_key,
    )


def resolve_img_env(agent: str) -> AgentModelEnv:
    platform_type = (
        _get_agent_override(agent, "IMG_PLATFORM_TYPE")
        or _pick_env("DEFAULT_IMG_PLATFORM_TYPE")
        or "openai"
    )
    model_type = (
        _get_agent_override(agent, "IMG_TYPE")
        or _pick_env("DEFAULT_IMG_TYPE")
        or "gpt-image-1"
    )
    api_url = (
        _get_agent_override(agent, "IMG_API_URL")
        or os.getenv("DEFAULT_IMG_API_URL")
        or ""
    ).strip()
    api_key = _get_agent_override(agent, "IMG_API_KEY") or _pick_env("DEFAULT_IMG_API_KEY") or ""
    return AgentModelEnv(
        platform_type=platform_type,
        model_type=model_type,
        api_url=api_url,
        api_key=api_key,
    )
