import json
import re
import concurrent.futures
import os
import time
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

from app.core.model_config import sanitize_model_config
from app.core.agent_model_env import resolve_text_llm_env
from app.services.render_plan_models import RenderPlan
from app.services.vlm_beautify import FOCUS_TEMPLATES


_CLIENT_RENDER_PLAN = None


def _get_render_plan_client():
    global _CLIENT_RENDER_PLAN
    if _CLIENT_RENDER_PLAN is not None:
        return _CLIENT_RENDER_PLAN
    cfg = resolve_text_llm_env("RENDER_PLAN")
    api_key = cfg.api_key
    if not api_key:
        _CLIENT_RENDER_PLAN = None
        return None
    platform_type = cfg.platform_type
    model_type = cfg.model_type
    api_url = cfg.api_url
    try:
        try:
            model_platform = ModelPlatformType(platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL
        create_kwargs = {
            "model_platform": model_platform,
            "model_type": model_type,
            "api_key": api_key,
            "model_config_dict": sanitize_model_config(model_type, {"temperature": 0.2}),
        }
        if api_url:
            create_kwargs["url"] = api_url
        client = ModelFactory.create(**create_kwargs)
        _CLIENT_RENDER_PLAN = client
        return client
    except Exception:
        _CLIENT_RENDER_PLAN = None
        return None


def _llm_call(user: str, system_prompt: str) -> str:
    client = _get_render_plan_client()
    if not client:
        raise RuntimeError("LLM client not initialized for RenderPlanAgent")
    sys_msg = BaseMessage.make_assistant_message(role_name="System", content=system_prompt or "You are a helpful assistant.")
    user_msg = BaseMessage.make_user_message(role_name="User", content=user)
    agent = ChatAgent(system_message=sys_msg, model=client)
    timeout_s = 180.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(agent.step, user_msg)
        try:
            response = fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as e:
            raise RuntimeError(f"RenderPlanAgent LLM timeout after {timeout_s:.1f}s") from e
    return response.msg.content


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```\s*$", "", raw).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    if start < 0:
        return None
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
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


class RenderPlanAgent:
    @staticmethod
    def generate(
        *,
        slide_no: int,
        total_slides: int,
        theme: str,
        enabled_effects_hint: List[str],
        content: Dict[str, Any],
        speech: str,
        requirements_context: str,
        allowed_image_urls: List[str],
        table_rows: Optional[List[List[str]]] = None,
        title_meta: Optional[Dict[str, str]] = None,
        deck_style_summary: str = "",
        prev_style_summary: str = "",
        repair_context: Optional[Dict[str, Any]] = None,
    ) -> RenderPlan:
        allowed_effects = [str(x) for x in (enabled_effects_hint or []) if str(x or "").strip()]
        table_rows2 = list(table_rows or [])
        table_preview = table_rows2[:10] if table_rows2 else []

        # Prepare template info for prompt
        template_info = "\n".join([f"- {t['id']}: {t['description']}" for t in FOCUS_TEMPLATES])

        deck_style_summary = str(deck_style_summary or "").strip()[:600]
        prev_style_summary = str(prev_style_summary or "").strip()[:600]
        repair_context = repair_context or {}
        repair_summary = ""
        if repair_context:
            try:
                repair_summary = json.dumps(repair_context, ensure_ascii=False)[:1200]
            except Exception:
                repair_summary = str(repair_context)[:1200]

        sys_base = (
            "You are a senior research keynote slide designer.\n"
            "Task: output ONE single JSON object called a RenderPlan for ONE slide.\n"
            "All layout and content decisions must be made by you; no deterministic renderer logic exists.\n\n"
            "Hard constraints:\n"
            "- Output JSON ONLY. No markdown, no explanations.\n"
            "- NEVER reference /preview/ images.\n"
            "- If you use an image, you MUST select image.url from allowed_image_urls.\n"
            "- kicker MUST be an empty string \"\". Do NOT invent section labels.\n"
            "- Choose exactly ONE layout from: cover|section_transition|toc|references|hero_figure|metric_cards|two_col_compare|table_focus|one_sentence|tri_cards|timeline|process_stack|diagram_flow|solo.\n"
            "- Aesthetic Requirement (URGENT): Avoid putting numbered lists (1. 2. 3.) or steps into a single long core_message paragraph. You MUST use 'process_stack', 'timeline', or 'tri_cards' layout to create high-end visual components. Solo layout is for PUNCHY single sentences ONLY.\n"
            "- Visual Variety: Use 'hero_figure' for impact, 'metric_cards' for data, and 'tri_cards' for conceptual splits. Don't let every slide look like a single card.\n"
            "- Ensure the required fields for the chosen layout are present.\n\n"
            "Layout requirements:\n"
            "- cover: title + optional subtitle; no bullets, no steps.\n"
            "  - For cover, prefer using title_meta.author/title_meta.date when available; set RenderPlan.author/date.\n"
            "- section_transition: title + core_message (or subtitle); minimal text, no steps.\n"
            "- toc: bullets (2-8) representing sections; each bullet should be 'Section: short note' when possible.\n"
            "- references: bullets (1-10) each a citation/reference line; must use references_source if provided.\n"
            "- hero_figure: image{url,caption,focus_template_id?} + optional core_message + 0-3 bullets.\n"
            "- metric_cards: metrics (2-5) + optional core_message + 0-2 bullets.\n"
            "- table_focus: MUST include table_viz.spec with an ECharts option JSON + 0-2 bullets. No HTML table.\n"
            "- diagram_flow: diagram_spec{nodes>=2,edges?,layout?} + optional core_message.\n"
            "- process_stack/timeline: steps (2-5) + optional core_message.\n"
            "- tri_cards: steps (3) + optional core_message.\n"
            "- two_col_compare: bullets (3-4) + optional core_message.\n"
            "- one_sentence: core_message only (bullets must be empty).\n"
            "- solo: core_message and/or bullets.\n\n"
            "Image Focus Templates (Pick ONE if layout=hero_figure):\n"
            f"{template_info}\n\n"
            "Table Viz (ECharts) rules:\n"
            "- For table_focus, output:\n"
            "  table_viz: {\"spec\": {\"type\":\"echarts\",\"option\": <EChartsOption JSON>, \"renderer\":\"auto\"|\"canvas\"|\"svg\"?, \"height\": number?}}\n"
            "- option MUST be valid EChartsOption JSON (NO functions, NO JS code).\n"
            "- option MUST include series (non-empty). Each series MUST have 'type' (e.g. bar/line/scatter/heatmap).\n"
            "- option MUST include a valid coordinate/data system (dataset or xAxis/yAxis or polar/radar/geo).\n"
            "- If multiple series are present, add a legend.\n"
            "- Use transparent backgrounds. Keep text readable.\n\n"
            "Minimal ECharts option examples (JSON only):\n"
            "- Bar:\n"
            "  {\"grid\":{\"left\":42,\"right\":20,\"top\":36,\"bottom\":42,\"containLabel\":true},\"tooltip\":{\"trigger\":\"axis\"},\"legend\":{\"top\":0},\"xAxis\":{\"type\":\"category\",\"data\":[\"A\",\"B\"]},\"yAxis\":{\"type\":\"value\"},\"series\":[{\"type\":\"bar\",\"name\":\"m1\",\"data\":[1,2]}]}\n"
            "- Line:\n"
            "  {\"grid\":{\"left\":42,\"right\":20,\"top\":36,\"bottom\":42,\"containLabel\":true},\"tooltip\":{\"trigger\":\"axis\"},\"legend\":{\"top\":0},\"xAxis\":{\"type\":\"category\",\"data\":[\"A\",\"B\"]},\"yAxis\":{\"type\":\"value\"},\"series\":[{\"type\":\"line\",\"name\":\"m1\",\"smooth\":true,\"data\":[1,2]}]}\n"
            "- Heatmap:\n"
            "  {\"tooltip\":{\"position\":\"top\"},\"grid\":{\"left\":70,\"right\":20,\"top\":30,\"bottom\":56},\"xAxis\":{\"type\":\"category\",\"data\":[\"A\",\"B\"],\"splitArea\":{\"show\":true}},\"yAxis\":{\"type\":\"category\",\"data\":[\"X\",\"Y\"],\"splitArea\":{\"show\":true}},\"visualMap\":{\"min\":0,\"max\":10,\"calculable\":true,\"orient\":\"horizontal\",\"left\":\"center\",\"bottom\":8},\"series\":[{\"type\":\"heatmap\",\"data\":[[0,0,1],[1,1,5]]}]}\n\n"
            "Visual Styles (style_config):\n"
            "- theme_variant: \"default\"|\"glass\"|\"bento\"|\"neon\" (use 'glass' for modern transparency, 'bento' for grid dashboards).\n"
            "- accent_color: \"primary\"|\"cyan\"|\"purple\"|\"orange\"|\"emerald\".\n"
            "- motion_intensity: \"static\"|\"low\"|\"high\" (controls entry animations).\n\n"
            "- highlight_variant: \"aurora\"|\"sunset\"|\"cyber\"|\"violet\"|\"mono\"|\"underline\" (choose ONE per slide).\n\n"
            "Layout Config (layout_config):\n"
            "- split_ratio: \"50:50\"|\"40:60\"|\"60:40\"|\"30:70\"|\"70:30\" (controls container widths).\n"
            "- spacing: \"compact\"|\"normal\"|\"loose\".\n\n"
            "Effects:\n"
            "- enabled_effects_hint is a list of requested effects. You may output effects_used as a SUBSET.\n"
            "- If \"Image Focus\" is used and an image is selected, you MUST pick a 'focus_template_id' from the list above. DO NOT generate manual focus_regions coordinates.\n"
            "- If \"Table Viz\" is used with table_focus, include table_viz.spec.option.\n"
            "- If \"Text Keynote\" is requested, you MUST highlight 1-3 key phrases in title/core_message/bullets by wrapping them with [[[...]]]. These will be rendered as LARGE, BOLD, GRADIENT text.\n"
            "- Highlight PRIORITY (in order): numeric results (e.g. QPS, Recall, speedup factors), key method traits (\"two-stage graph search\", \"routing vectors\"), and sharp conclusion phrases (\"keeps recall unchanged\").\n"
            "- Avoid highlighting vague phrases (\"key insight\", \"novel approach\") or filler text.\n"
            "- Do NOT overuse highlights: keep most text unmarked; only truly critical phrases get [[[...]]].\n\n"
            "Style context:\n"
            "- Deck style summary (global feel for the entire talk):\n"
            f"  {deck_style_summary or 'N/A'}\n"
            "- Previous slide style summary (keep this slide stylistically consistent, but not identical):\n"
            f"  {prev_style_summary or 'N/A'}\n\n"
            "Repair context (only present when regenerating after a failed attempt):\n"
            "- If provided, it describes issues found in the previous render and a small suggested patch.\n"
            "- You MUST fix those issues while changing as little as possible.\n"
            f"- Repair summary (JSON, truncated): {repair_summary or 'N/A'}\n\n"
            "Content integrity rules (CRITICAL):\n"
            "- Do NOT introduce new method/paper/system names that are not present in source_compact.\n"
            "- Do NOT use references_source to invent slide content; references_source is for the references layout only.\n\n"
            "RenderPlan schema (keys must match):\n"
            "{\n"
            "  \"slide_role\": \"intro|method|results|conclusion|content\",\n"
            "  \"kicker\": str,\n"
            "  \"title\": str,\n"
            "  \"subtitle\": str,\n"
            "  \"core_message\": str,\n"
            "  \"author\": str,\n"
            "  \"date\": str,\n"
            "  \"layout\": str,\n"
            "  \"effects_used\": [str,...],\n"
            "  \"layout_config\": {\"split_ratio\":str, \"spacing\":str},\n"
            "  \"style_config\": {\"theme_variant\":str, \"accent_color\":str, \"motion_intensity\":str, \"highlight_variant\":str},\n"
            "  \"bullets\": [str,...],\n"
            "  \"steps\": [str,...],\n"
            "  \"metrics\": [{\"label\":str,\"value\":str,\"delta\":str?},...],\n"
            "  \"image\": {\"url\":str,\"caption\":str,\"focus_template_id\":str?}?,\n"
            "  \"table_viz\": {\"spec\": {\"type\":\"echarts\",\"option\": object, \"renderer\":str?, \"height\":number?}, \"payload\": object?}?,\n"
            "  \"diagram_spec\": object?\n"
            "}\n"
        )

        frame_tex = str((content or {}).get("_frame_tex") or "")[:3600]
        speech_compact = str(speech or "").strip()[:900]
        title_compact = str((content or {}).get("title") or "").strip()[:200]
        subtitle_compact = str((content or {}).get("subtitle") or "").strip()[:240]
        bullets_compact = "\n".join([f"- {str(x).strip()}" for x in ((content or {}).get("bullets") or []) if str(x).strip()][:10])[:1000]
        plain_compact = str((content or {}).get("plain") or "").strip()[:900]

        payload = {
            "slide_no": int(slide_no),
            "total_slides": int(total_slides),
            "theme": str(theme or ""),
            "enabled_effects_hint": allowed_effects,
            "requirements_context": (requirements_context or "")[:1600],
            "title_meta": {
                "title": str((title_meta or {}).get("title") or ""),
                "author": str((title_meta or {}).get("author") or ""),
                "date": str((title_meta or {}).get("date") or ""),
            },
            "references_source": [str(x) for x in ((content or {}).get("_references_source") or []) if str(x or "").strip()][:24],
            "allowed_image_urls": [str(u) for u in (allowed_image_urls or []) if str(u or "").strip()][:10],
            "table_preview": table_preview,
            "source_compact": (
                "[Content]\n"
                + (f"Title: {title_compact}\n" if title_compact else "")
                + (f"Subtitle: {subtitle_compact}\n" if subtitle_compact else "")
                + (f"Bullets:\n{bullets_compact}\n" if bullets_compact else "")
                + (f"Plain:\n{plain_compact}\n" if plain_compact else "")
                + (f"Frame:\n{frame_tex}\n" if frame_tex else "")
                + "\n[Speech]\n"
                + speech_compact
            )[:5200],
        }

        user = json.dumps(payload, ensure_ascii=False)
        last_err = ""
        for attempt in range(5):
            sys = sys_base
            if attempt > 0:
                tail = str(last_err or "").strip()
                if len(tail) > 900:
                    tail = tail[:900] + "…"
                sys = (
                    sys_base
                    + "\nRetry:\n"
                    + "- Your previous output was INVALID.\n"
                    + "- Fix ALL issues and output ONE valid RenderPlan JSON object.\n"
                    + (f"- Error summary: {tail}\n" if tail else "")
                )

            if attempt > 0:
                time.sleep(min(0.25 * float(attempt), 1.0))
            try:
                raw = _llm_call(user, sys)
            except Exception as e:
                last_err = RenderPlan.safe_error_summary(e)
                continue
            obj = _extract_first_json_object(raw)
            if not obj:
                last_err = "No JSON object found."
                continue
            try:
                plan = RenderPlan.model_validate(obj)
            except ValidationError as e:
                last_err = f"Schema validation failed: {str(e)}"
                continue

            try:
                plan.normalize()
                plan.validate_effects(enabled_effects_hint=allowed_effects)
                plan.validate_urls(allowed_image_urls=[str(u) for u in (allowed_image_urls or []) if str(u or "").strip()])
                plan.require()
            except Exception as e:
                last_err = RenderPlan.safe_error_summary(e)
                continue
            return plan

        raise RuntimeError(f"RenderPlan generation failed after retries. last_err={last_err}")
