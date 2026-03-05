from __future__ import annotations

from typing import Optional, Dict, Any


def _use_max_completion_tokens(model_type: Optional[str]) -> bool:
    if not model_type:
        return False
    lowered = model_type.lower()
    return lowered.startswith("gpt")


def _supports_custom_temperature(model_type: Optional[str]) -> bool:
    if not model_type:
        return True
    lowered = model_type.lower().strip()
    if lowered.startswith("gpt-5"):
        return False
    return True


def sanitize_model_config(model_type: Optional[str], config: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(config or {})
    if "temperature" in out and not _supports_custom_temperature(model_type):
        out.pop("temperature", None)
    return out


def build_model_config(
    model_type: Optional[str],
    temperature: float,
    max_tokens: int,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if _supports_custom_temperature(model_type):
        config["temperature"] = temperature
    if timeout is not None:
        config["timeout"] = timeout
    if _use_max_completion_tokens(model_type):
        config["max_completion_tokens"] = max_tokens
    else:
        config["max_tokens"] = max_tokens
    return sanitize_model_config(model_type, config)
