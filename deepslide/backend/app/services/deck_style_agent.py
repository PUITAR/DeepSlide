from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from typing import Any, Dict

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env
from app.services.visual_asset_models import DeckStyleDNA


_CLIENT_DECK_STYLE = None


def _get_client():
    global _CLIENT_DECK_STYLE
    if _CLIENT_DECK_STYLE is not None:
        return _CLIENT_DECK_STYLE
    cfg = resolve_text_llm_env("DECK_STYLE")
    if not cfg.api_key:
        _CLIENT_DECK_STYLE = None
        return None
    try:
        try:
            model_platform = ModelPlatformType(cfg.platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL
        create_kwargs = {
            "model_platform": model_platform,
            "model_type": cfg.model_type,
            "api_key": cfg.api_key,
            "model_config_dict": sanitize_model_config(cfg.model_type, {"temperature": 0.2}),
        }
        if cfg.api_url:
            create_kwargs["url"] = cfg.api_url
        _CLIENT_DECK_STYLE = ModelFactory.create(**create_kwargs)
        return _CLIENT_DECK_STYLE
    except Exception:
        _CLIENT_DECK_STYLE = None
        return None


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```\s*$", "", raw).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = raw[start : i + 1]
                try:
                    obj = json.loads(snippet)
                    return obj if isinstance(obj, dict) else {}
                except Exception:
                    return {}
    return {}


def _fallback_style(persona: str, theme: str, requirements_context: str) -> DeckStyleDNA:
    seed = hashlib.sha256((persona + "|" + theme + "|" + (requirements_context or "")[:400]).encode("utf-8")).hexdigest()
    picks = [
        ("primary", "#3B82F6"),
        ("cyan", "#06B6D4"),
        ("purple", "#8B5CF6"),
        ("emerald", "#10B981"),
        ("orange", "#F97316"),
    ]
    rot = int(seed[:2], 16) % len(picks)
    palette = {
        "primary": picks[rot][1],
        "secondary": picks[(rot + 1) % len(picks)][1],
        "accent": picks[(rot + 2) % len(picks)][1],
        "bg": "#F8FAFC" if str(theme).lower() == "light" else "#0B1220",
        "fg": "#0F172A" if str(theme).lower() == "light" else "#E5E7EB",
    }
    return DeckStyleDNA(
        persona=str(persona or "")[:64],
        theme="light" if str(theme).lower() == "light" else "dark",
        palette=palette,
        material="glass",
        illustration_style="abstract",
        stroke_strength="medium",
        radius_strength="medium",
        shadow_strength="medium",
        motion_baseline="low",
        notes="",
    )


def generate_deck_style(*, requirements_context: str, persona: str = "", theme: str = "light") -> DeckStyleDNA:
    client = _get_client()
    if not client:
        return _fallback_style(persona, theme, requirements_context)

    sys = (
        "You are a deck style director.\n"
        "Output ONE JSON object ONLY matching this schema:\n"
        "{\n"
        "  \"version\": \"v1\",\n"
        "  \"persona\": str,\n"
        "  \"theme\": \"light\"|\"dark\",\n"
        "  \"palette\": {\"primary\":str,\"secondary\":str,\"accent\":str,\"bg\":str,\"fg\":str},\n"
        "  \"material\": \"glass\"|\"paper\"|\"dark-grid\"|\"bento\",\n"
        "  \"illustration_style\": \"abstract\"|\"isometric\"|\"flat\"|\"3d\",\n"
        "  \"stroke_strength\": \"low\"|\"medium\"|\"high\",\n"
        "  \"radius_strength\": \"low\"|\"medium\"|\"high\",\n"
        "  \"shadow_strength\": \"low\"|\"medium\"|\"high\",\n"
        "  \"motion_baseline\": \"static\"|\"low\"|\"high\",\n"
        "  \"notes\": str\n"
        "}\n"
        "Hard rules:\n"
        "- No extra keys.\n"
        "- No markdown.\n"
        "- Palette colors must be hex like #RRGGBB.\n"
        "- Keep palette light and colorful; avoid large dark blocks.\n"
    )
    payload = {
        "persona": str(persona or "")[:64],
        "theme": "light" if str(theme).lower() == "light" else "dark",
        "requirements_context": str(requirements_context or "")[:1600],
    }
    user = json.dumps(payload, ensure_ascii=False)
    sys_msg = BaseMessage.make_assistant_message(role_name="System", content=sys)
    user_msg = BaseMessage.make_user_message(role_name="User", content=user)
    agent = ChatAgent(system_message=sys_msg, model=client)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(agent.step, user_msg)
        resp = fut.result(timeout=90.0)
    obj = _extract_first_json_object(str(resp.msg.content or ""))
    try:
        dna = DeckStyleDNA.model_validate(obj)
        dna.persona = str(persona or "")[:64]
        dna.theme = "light" if str(theme).lower() == "light" else "dark"
        return dna
    except Exception:
        return _fallback_style(persona, theme, requirements_context)
