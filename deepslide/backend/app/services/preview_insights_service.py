import concurrent.futures
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env
from app.services.core.ppt_core import _strip_latex_inline

logger = logging.getLogger(__name__)


def _build_client(agent: str):
    cfg = resolve_text_llm_env(agent)
    api_key = cfg.api_key
    if not api_key:
        return None
    try:
        try:
            model_platform = ModelPlatformType(cfg.platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL
        create_kwargs = {
            "model_platform": model_platform,
            "model_type": cfg.model_type,
            "api_key": api_key,
            "model_config_dict": sanitize_model_config(cfg.model_type, {"temperature": 0.3}),
        }
        if cfg.api_url:
            create_kwargs["url"] = cfg.api_url
        return ModelFactory.create(**create_kwargs)
    except Exception as e:
        logger.error(f"Preview insights client init failed for agent={agent}: {e}")
        return None


def _call_llm(agent: str, user: str, system_prompt: str) -> str:
    client = _build_client(agent)
    if not client:
        raise RuntimeError(f"LLM client not initialized for {agent}")
    sys_msg = BaseMessage.make_assistant_message(role_name="System", content=system_prompt or "You are a helpful assistant.")
    user_msg = BaseMessage.make_user_message(role_name="User", content=user)
    chat_agent = ChatAgent(system_message=sys_msg, model=client)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(chat_agent.step, user_msg)
        response = fut.result(timeout=30.0)
    return response.msg.content


def _safe_read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read() or ""
    except Exception:
        return ""


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _recipe_dir(project_path: str) -> str:
    r = os.path.join(project_path, "recipe")
    return r if os.path.exists(r) else project_path


def _extract_title(frame: str) -> Tuple[str, str]:
    raw = str(frame or "")
    m1 = re.search(r"\\frametitle\{([\s\S]*?)\}", raw)
    m2 = re.search(r"\\framesubtitle\{([\s\S]*?)\}", raw)
    title = _strip_latex_inline(m1.group(1)) if m1 else ""
    subtitle = _strip_latex_inline(m2.group(1)) if m2 else ""
    return title, subtitle


def _frame_to_plain_text(frame: str) -> str:
    raw = str(frame or "")
    raw = re.sub(r"\\frametitle\{[\s\S]*?\}", "", raw)
    raw = re.sub(r"\\framesubtitle\{[\s\S]*?\}", "", raw)
    raw = re.sub(r"\\begin\{frame\}(\[[^\]]*\])?", "", raw)
    raw = raw.replace("\\end{frame}", "")
    return _strip_latex_inline(raw)


def _page_context(project_record: Dict[str, Any], page_index: int) -> Dict[str, Any]:
    project_path = str((project_record or {}).get("path") or "")
    recipe_dir = _recipe_dir(project_path)
    content_tex = _safe_read_text(os.path.join(recipe_dir, "content.tex"))
    speech_raw = _safe_read_text(os.path.join(recipe_dir, "speech.txt"))
    speech_segments = [s.strip() for s in str(speech_raw or "").split("<next>")]

    frames = [m.group(1) for m in re.finditer(r"(\\begin\{frame\}[\s\S]*?\\end\{frame\})", content_tex)]
    alignment = _safe_read_json(os.path.join(recipe_dir, "alignment_dsid.json")) or {}
    dsid_by_page = alignment.get("dsid_by_page") if isinstance(alignment.get("dsid_by_page"), list) else None
    page_meta_by_page = alignment.get("page_meta_by_page") if isinstance(alignment.get("page_meta_by_page"), list) else None

    page_type = "content"
    if page_meta_by_page and 0 <= page_index < len(page_meta_by_page) and isinstance(page_meta_by_page[page_index], dict):
        page_type = str(page_meta_by_page[page_index].get("type") or "content")

    fr_idx = None
    if dsid_by_page and 0 <= page_index < len(dsid_by_page) and isinstance(dsid_by_page[page_index], int):
        fr_idx = int(dsid_by_page[page_index]) - 1
    elif 0 <= page_index < len(frames):
        fr_idx = page_index

    title = ""
    subtitle = ""
    slide_text = ""
    if fr_idx is not None and 0 <= fr_idx < len(frames):
        fr = frames[fr_idx]
        title, subtitle = _extract_title(fr)
        slide_text = " ".join([x for x in [title, subtitle, _frame_to_plain_text(fr)] if x]).strip()

    speech_text = speech_segments[page_index] if 0 <= page_index < len(speech_segments) else ""

    def clip(s: str, n: int) -> str:
        t = " ".join(str(s or "").split())
        return t[:n]

    return {
        "page_index": int(page_index),
        "page_type": page_type,
        "title": title,
        "subtitle": subtitle,
        "slide_text": clip(slide_text, 900),
        "speech_text": clip(speech_text, 900),
    }


def generate_preview_coach_advice(project_record: Dict[str, Any], page_index: int, metrics_payload: Dict[str, Any]) -> List[str]:
    ctx = _page_context(project_record, page_index)
    per_slide = metrics_payload.get("per_slide") if isinstance(metrics_payload, dict) else None
    slide_metrics = None
    if isinstance(per_slide, list):
        for it in per_slide:
            if isinstance(it, dict) and int(it.get("page_index", -1)) == int(page_index):
                slide_metrics = it
                break

    system_prompt = (
        "You are a rehearsal coach for academic talks. Based on the provided slide content and metrics, "
        "write actionable, concrete tips.\n"
        "Output STRICT JSON only: {\"advice\": [\"...\", \"...\", ...]}.\n"
        "Rules:\n"
        "- Write in English.\n"
        "- Return 3 to 6 tips.\n"
        "- Each tip must be short (<= 12 words) and actionable.\n"
        "- No markdown, no explanations, no extra text.\n"
    )

    user = {
        "page_context": ctx,
        "metrics": (slide_metrics or {}),
        "deck_summary": metrics_payload.get("deck_summary") if isinstance(metrics_payload, dict) else {},
    }
    resp = _call_llm("PREVIEW_COACH", json.dumps(user, ensure_ascii=False), system_prompt)
    m = re.search(r"\{[\s\S]*\}", resp)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    adv = data.get("advice")
    if not isinstance(adv, list):
        return []
    out = []
    for s in adv:
        t = str(s or "").strip()
        if t:
            out.append(t)
    return out[:6]


def generate_audience_questions(project_record: Dict[str, Any], page_index: int, metrics_payload: Dict[str, Any]) -> List[str]:
    ctx = _page_context(project_record, page_index)
    per_slide = metrics_payload.get("per_slide") if isinstance(metrics_payload, dict) else None
    slide_metrics = None
    if isinstance(per_slide, list):
        for it in per_slide:
            if isinstance(it, dict) and int(it.get("page_index", -1)) == int(page_index):
                slide_metrics = it
                break

    system_prompt = (
        "You generate likely audience questions for an academic talk. Based on the slide content and risk metrics, "
        "write the 3 most likely questions.\n"
        "Output STRICT JSON only: {\"questions\": [\"Q1\", \"Q2\", \"Q3\"]}.\n"
        "Rules:\n"
        "- Write in English.\n"
        "- Questions must be specific, sharp but polite.\n"
        "- No markdown, no explanations, no extra text.\n"
    )
    user = {
        "page_context": ctx,
        "metrics": (slide_metrics or {}),
    }
    resp = _call_llm("AUDIENCE_QA", json.dumps(user, ensure_ascii=False), system_prompt)
    m = re.search(r"\{[\s\S]*\}", resp)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    qs = data.get("questions")
    if not isinstance(qs, list):
        return []
    out = []
    for s in qs:
        t = str(s or "").strip()
        if t:
            out.append(t)
    return out[:3]
