from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from ..io_utils import ensure_dir, sha1_bytes
from .env import LLMEnv, resolve_llm_env


def _build_model_config(model_type: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"temperature": float(temperature)}
    if model_type.startswith("gpt"):
        cfg["max_completion_tokens"] = int(max_tokens)
    else:
        cfg["max_tokens"] = int(max_tokens)
    return cfg


@dataclass(frozen=True)
class JudgeConfig:
    agent_name: str
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout_seconds: int = 120


class LLMJudge:
    def __init__(self, cache_dir: Path, config: JudgeConfig):
        self.cache_dir = cache_dir
        self.config = config
        ensure_dir(self.cache_dir)
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model

        env: LLMEnv = resolve_llm_env(self.config.agent_name)
        if not env.api_key:
            raise RuntimeError("Missing API key: set OPENAI_API_KEY or EVAL_MODEL_API_KEY in experiments/evaluation/.env")

        try:
            platform_enum = ModelPlatformType(env.platform_type)
        except Exception:
            platform_enum = ModelPlatformType.OPENAI_COMPATIBLE_MODEL

        create_kwargs: Dict[str, Any] = {
            "model_platform": platform_enum,
            "model_type": env.model_type,
            "api_key": env.api_key,
            "model_config_dict": _build_model_config(env.model_type, temperature=self.config.temperature, max_tokens=self.config.max_tokens),
        }
        if platform_enum == ModelPlatformType.OPENAI_COMPATIBLE_MODEL and env.api_url:
            create_kwargs["url"] = env.api_url

        self._model = ModelFactory.create(**create_kwargs)
        return self._model

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"judge_{key}.json"

    def judge_json(self, system_prompt: str, user_payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"system_prompt": system_prompt, "user": user_payload, "cfg": self.config.__dict__}
        key = sha1_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        path = self._cache_path(key)
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if not cached.get("ok") and cached.get("parsed") is None and cached.get("raw"):
                reparsed = _try_parse_json(cached.get("raw", ""))
                if reparsed is not None:
                    cached["ok"] = True
                    cached["parsed"] = reparsed
                    path.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
            return cached

        model = self._get_model()
        sys_msg = BaseMessage.make_assistant_message(role_name="Evaluator", content=system_prompt)
        agent = ChatAgent(system_message=sys_msg, model=model)
        user_msg = BaseMessage.make_user_message(role_name="User", content=json.dumps(user_payload, ensure_ascii=False))

        start = time.time()
        resp = agent.step(user_msg)
        elapsed = time.time() - start
        raw = resp.msg.content.strip() if getattr(resp, "msg", None) is not None else ""

        out: Dict[str, Any] = {
            "ok": False,
            "elapsed_seconds": elapsed,
            "raw": raw,
            "parsed": None,
        }

        parsed = _try_parse_json(raw)
        if parsed is not None:
            out["ok"] = True
            out["parsed"] = parsed

        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)


def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None

    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    return None
