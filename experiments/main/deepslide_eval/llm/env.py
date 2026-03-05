from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMEnv:
    platform_type: str
    model_type: str
    api_url: str
    api_key: str


def load_eval_dotenv(evaluation_root: Path) -> None:
    env_path = evaluation_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _get_env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def resolve_llm_env(agent_name: str) -> LLMEnv:
    key_prefix = "EVAL"
    agent_key = "EVAL_" + "".join([c if c.isalnum() else "_" for c in agent_name.upper()])

    def pick(suffix: str) -> str:
        v = _get_env(f"{agent_key}_{suffix}")
        if v:
            return v
        v = _get_env(f"{key_prefix}_{suffix}")
        if v:
            return v
        return ""

    platform_type = pick("MODEL_PLATFORM_TYPE") or "OPENAI_COMPATIBLE_MODEL"
    model_type = pick("MODEL_TYPE") or "gpt-4o-mini"
    api_url = pick("MODEL_API_URL")
    api_key = pick("MODEL_API_KEY") or _get_env("OPENAI_API_KEY") or _get_env("LLM_API_KEY")

    return LLMEnv(platform_type=platform_type, model_type=model_type, api_url=api_url, api_key=api_key)
