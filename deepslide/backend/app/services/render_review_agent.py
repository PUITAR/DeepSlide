import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from camel.messages import BaseMessage
from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from app.core.agent_model_env import resolve_text_llm_env
from app.core.model_config import sanitize_model_config
from app.services.render_plan_models import RenderPlan
from app.services.render_plan_agent import _extract_first_json_object


class RenderIssue(BaseModel):
    id: str = Field(..., max_length=64)
    severity: str = Field(..., description="low|medium|high|critical")
    message: str = Field(..., max_length=512)
    hint: str = Field(default="", max_length=512)
    location: Dict[str, Any] = Field(default_factory=dict)


class RenderReviewResult(BaseModel):
    issues: List[RenderIssue] = Field(default_factory=list)
    suggested_plan_patch: Dict[str, Any] = Field(
        default_factory=dict,
        description="Partial RenderPlan patch; only fields that should change."
    )
    notes_for_slide_agent: str = Field(
        default="", max_length=2000,
        description="Optional hints that can be fed back into the slide-generation agent."
    )


_CLIENT_RENDER_REVIEW = None


def _get_render_review_client():
    global _CLIENT_RENDER_REVIEW
    if _CLIENT_RENDER_REVIEW is not None:
        return _CLIENT_RENDER_REVIEW

    cfg = resolve_text_llm_env("HTML_REVIEW")
    api_key = cfg.api_key
    if not api_key:
        _CLIENT_RENDER_REVIEW = None
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
            "model_config_dict": sanitize_model_config(model_type, {"temperature": 0.0}),
        }
        if api_url:
            create_kwargs["url"] = api_url
        client = ModelFactory.create(**create_kwargs)
        _CLIENT_RENDER_REVIEW = client
        return client
    except Exception:
        _CLIENT_RENDER_REVIEW = None
        return None


def _llm_call(user: str, system_prompt: str) -> str:
    client = _get_render_review_client()
    if not client:
        raise RuntimeError("LLM client not initialized for RenderReviewAgent")
    sys_msg = BaseMessage.make_assistant_message(
        role_name="System", content=system_prompt or "You are a helpful assistant."
    )
    user_msg = BaseMessage.make_user_message(role_name="User", content=user)
    agent = ChatAgent(system_message=sys_msg, model=client)
    response = agent.step(user_msg)
    return response.msg.content


class RenderReviewAgent:
    """LLM-based reviewer for RenderPlan + rendered HTML.

    This agent is intentionally side-effect free: it only reports issues and
    suggests patches; the caller decides whether and how to apply them.
    """

    @staticmethod
    def review(
        *,
        plan: RenderPlan,
        html: str,
        render_meta: Optional[Dict[str, Any]] = None,
        sandbox_report: Optional[Dict[str, Any]] = None,
        max_issues: int = 16,
    ) -> RenderReviewResult:
        meta = render_meta or {}
        try:
            plan_dict = plan.model_dump()
        except Exception:
            plan_dict = {}

        payload: Dict[str, Any] = {
            "render_plan": plan_dict,
            "render_meta": meta,
            "html_snippet": str(html or ""),
            "sandbox_report": sandbox_report or {},
            "max_issues": int(max_issues),
        }

        user = json.dumps(payload, ensure_ascii=False)

        sys = (
            "You are a senior design QA reviewer for Spec-mode HTML slides.\n"
            "You are given:\n"
            "- The structured RenderPlan used to render a slide.\n"
            "- A small JSON meta summary about the rendered layout and effects.\n"
            "- A snippet of the final HTML (including CSS/JS and body markup).\n"
            "- Optionally, a sandbox_report from a headless browser run containing JS errors, network failures, and basic layout info.\n\n"
            "Your task:\n"
            "1) Detect structural or visual failures in the slide, focusing on:\n"
            "   - Missing or unused assets (hero images, table viz, diagrams).\n"
            "   - Mismatch between layout/effects and actual HTML (e.g., Image Focus effect but no ROI tiles).\n"
            "   - Clearly wrong layout choices (e.g., diagram_layout used when a main figure is available).\n"
            "   - Empty or nearly empty content regions (no visible text or visuals).\n"
            "2) Propose a SMALL patch to the RenderPlan (partial JSON) that would fix the most important problems.\n"
            "   - Only touch layout / style_config / layout_config / effects_used / image.focus_template_id / diagram_spec.\n"
            "   - Do NOT rewrite the actual content (title/core_message/bullets/steps) except when absolutely necessary.\n"
            "3) Provide optional notes_for_slide_agent that explains how future generations could avoid the same issue.\n\n"
            "IMPORTANT:\n"
            "- Output STRICT JSON only, matching the schema:\n"
            "{\n"
            "  \"issues\": [\n"
            "    {\"id\": str, \"severity\": \"low|medium|high|critical\", \"message\": str, \"hint\": str, \"location\": object},\n"
            "    ...\n"
            "  ],\n"
            "  \"suggested_plan_patch\": object,\n"
            "  \"notes_for_slide_agent\": str\n"
            "}\n"
            "- Keep issues array length <= max_issues from the payload.\n"
            "- Use short, precise ids (e.g., \"IMAGE_PRESENT_BUT_NO_HERO\").\n"
        )

        raw = _llm_call(user, sys)
        obj = _extract_first_json_object(raw)
        if not obj:
            raise RuntimeError("RenderReviewAgent: no JSON object in LLM response")

        try:
            result = RenderReviewResult.model_validate(obj)
        except ValidationError as e:
            raise RuntimeError(f"RenderReviewAgent: invalid JSON schema: {e}") from e

        if len(result.issues) > max_issues:
            result.issues = result.issues[:max_issues]
        return result
