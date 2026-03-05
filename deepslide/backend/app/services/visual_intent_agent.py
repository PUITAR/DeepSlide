from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env


@dataclass(frozen=True)
class VisualIntent:
    version: str
    topic: str
    scene: str
    action_sequence: List[str]
    mood: str
    style_tags: List[str]
    negative: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "topic": self.topic,
            "scene": self.scene,
            "action_sequence": list(self.action_sequence),
            "mood": self.mood,
            "style_tags": list(self.style_tags),
            "negative": list(self.negative),
        }


_CLIENT_VISUAL_INTENT = None


def _get_client():
    global _CLIENT_VISUAL_INTENT
    if _CLIENT_VISUAL_INTENT is not None:
        return _CLIENT_VISUAL_INTENT
    cfg = resolve_text_llm_env("VISUAL_INTENT")
    if not cfg.api_key:
        _CLIENT_VISUAL_INTENT = None
        return None
    try:
        try:
            platform = ModelPlatformType(cfg.platform_type)
        except Exception:
            platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL
        kwargs = {
            "model_platform": platform,
            "model_type": cfg.model_type,
            "api_key": cfg.api_key,
            "model_config_dict": sanitize_model_config(cfg.model_type, {"temperature": 0.25}),
        }
        if cfg.api_url:
            kwargs["url"] = cfg.api_url
        _CLIENT_VISUAL_INTENT = ModelFactory.create(**kwargs)
        return _CLIENT_VISUAL_INTENT
    except Exception:
        _CLIENT_VISUAL_INTENT = None
        return None


def _stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> Dict[str, Any]:
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


def _fallback_intent(source: str) -> VisualIntent:
    s = " ".join(str(source or "").split())[:900].lower()
    def has_any(*keys: str) -> bool:
        return any(k in s for k in keys)

    if has_any("embodied", "robot", "manipulation", "locomotion", "grasp", "tactile", "imitation", "reinforcement"):
        return VisualIntent(
            version="v1",
            topic="embodied intelligence",
            scene="a futuristic lab scene with a humanoid robot and a robotic arm, mid-action, cinematic lighting, clean negative space",
            action_sequence=["reach", "grasp", "place"],
            mood="clean cinematic academic",
            style_tags=["poster", "high-end", "minimal text-free", "motion-ready"],
            negative=["text", "numbers", "watermark", "logo", "caption", "UI", "diagram labels"],
        )
    if has_any("black hole", "event horizon", "hawking", "relativity", "gravity", "cosmology", "astrophysics"):
        return VisualIntent(
            version="v1",
            topic="high-energy physics / black hole",
            scene="a stylized black hole with accretion disk and gravitational lensing, deep space, cinematic, clean negative space",
            action_sequence=["accretion flow intensifies", "lensing swirl shifts", "glow stabilizes"],
            mood="cinematic scientific",
            style_tags=["poster", "space", "lensing", "high contrast"],
            negative=["text", "numbers", "watermark", "logo", "caption", "UI", "diagram labels"],
        )
    if has_any("graph", "search", "nearest neighbor", "vector", "index", "routing", "retrieval"):
        return VisualIntent(
            version="v1",
            topic="graph search / retrieval",
            scene="an abstract network topology with glowing nodes and paths, clean grid-like space, subtle depth, no text",
            action_sequence=["path highlights appear", "nodes glow shifts", "routes converge"],
            mood="modern technical",
            style_tags=["abstract", "network", "minimal", "poster"],
            negative=["text", "numbers", "watermark", "logo", "caption", "UI", "diagram labels"],
        )
    return VisualIntent(
        version="v1",
        topic="research presentation",
        scene="abstract modern gradient background with subtle scientific motifs, clean whitespace, no text",
        action_sequence=["light bloom shifts", "gradient drifts", "subtle particles move"],
        mood="clean academic",
        style_tags=["abstract", "minimal", "poster"],
        negative=["text", "numbers", "watermark", "logo", "caption", "UI", "diagram labels"],
    )


def generate_visual_intent(*, slide_payload: Dict[str, Any]) -> tuple[VisualIntent, str]:
    payload = dict(slide_payload or {})
    payload["version"] = "v1"
    h = _stable_hash(payload)[:24]

    client = _get_client()
    if not client:
        src = json.dumps(payload, ensure_ascii=False)
        return _fallback_intent(src), h

    sys = (
        "You are a visual art director for scientific slide decks.\n"
        "Task: output ONE JSON object ONLY.\n"
        "Goal: produce a content-driven background/poster concept for this slide.\n"
        "Hard rules:\n"
        "- No markdown, no explanation.\n"
        "- Do NOT include any text/letters/numbers/logos/watermarks in the image.\n"
        "- The image must be thematically aligned with the slide content.\n"
        "- If the slide domain is physics (e.g., black holes), do NOT output robots.\n"
        "- If the slide domain is robotics/embodied intelligence, prefer robot manipulation/locomotion scenes.\n"
        "Output schema:\n"
        "{\n"
        "  \"version\": \"v1\",\n"
        "  \"topic\": str,\n"
        "  \"scene\": str,\n"
        "  \"action_sequence\": [str, str, str],\n"
        "  \"mood\": str,\n"
        "  \"style_tags\": [str,...],\n"
        "  \"negative\": [str,...]\n"
        "}\n"
    )
    user = json.dumps(payload, ensure_ascii=False)
    sys_msg = BaseMessage.make_assistant_message(role_name="System", content=sys)
    user_msg = BaseMessage.make_user_message(role_name="User", content=user)
    agent = ChatAgent(system_message=sys_msg, model=client)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        resp = ex.submit(agent.step, user_msg).result(timeout=60.0)
    obj = _extract_json(str(resp.msg.content or ""))
    try:
        vi = VisualIntent(
            version="v1",
            topic=str(obj.get("topic") or "").strip()[:120] or "research presentation",
            scene=str(obj.get("scene") or "").strip()[:400] or "abstract modern background, clean whitespace, no text",
            action_sequence=[str(x).strip()[:80] for x in (obj.get("action_sequence") or []) if str(x or "").strip()][:3],
            mood=str(obj.get("mood") or "").strip()[:120] or "clean academic",
            style_tags=[str(x).strip()[:40] for x in (obj.get("style_tags") or []) if str(x or "").strip()][:10],
            negative=[str(x).strip()[:40] for x in (obj.get("negative") or []) if str(x or "").strip()][:20],
        )
        if len(vi.action_sequence) < 2:
            vi = _fallback_intent(user)
        return vi, h
    except Exception:
        return _fallback_intent(user), h
