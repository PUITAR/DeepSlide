from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from ..config import load_env

if TYPE_CHECKING:  # pragma: no cover
    from camel.agents import ChatAgent


class CamelAIClient:
    """LLM client for requirements-collection chat.

    Important: do NOT hardcode dotenv paths; use combine124.config.load_env.
    """

    def __init__(self, env_path: Optional[str] = None):
        self.env_path = env_path
        self.model = None
        self.agent: Optional["ChatAgent"] = None
        self._system_extra_context: Optional[str] = None

        self.system_template = (
            "你是 DeepSlide 的 PPT 需求收集助手。你的任务是通过多轮对话收集生成演示所需的关键信息。\n"
            "请一步步引导用户补全（每次只问一个问题）：听众、演讲时长、重点章节、风格偏好、特殊要求等。\n\n"
            "当你认为信息足够，或用户表达确认/完成/没有更多要求时，你必须：\n"
            "1) 输出严格 JSON（不要 Markdown），字段必须包含：\n"
            "{\n"
            '  "audience": "...",\n'
            '  "duration": "...",\n'
            '  "focus_sections": ["..."],\n'
            '  "style": "...",\n'
            '  "special_notes": "..."\n'
            "}\n"
            "2) JSON 后可追加一句确认：以上为生成 PPT 的初步需求，是否确认？\n"
            "3) 输出 JSON 后不要继续提问。"
        )

        # Lazy init: don't touch network/LLM during Streamlit startup.
        # We will initialize on first get_response() / set_context().

    def _init_model(self) -> None:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType

        load_env(self.env_path)

        api_key = os.getenv("DEFAULT_MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "CamelAIClient: missing API key. Please set DEFAULT_MODEL_API_KEY (or DEEPSEEK_API_KEY) in .env."
            )

        url = os.getenv("DEFAULT_MODEL_API_URL") or "https://api.deepseek.com"
        model_type = os.getenv("DEFAULT_MODEL_TYPE") or "deepseek-chat"

        self.model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=model_type,
            url=url,
            api_key=api_key,
            model_config_dict={"temperature": 0.2},
        )

    def _init_agent(self, system_extra_context: Optional[str]) -> None:
        from camel.agents import ChatAgent
        from camel.messages import BaseMessage

        if self.model is None:
            self._init_model()
        content = self.system_template
        if system_extra_context:
            content = content + "\n\n" + system_extra_context

        sys_msg = BaseMessage.make_assistant_message(
            role_name="DeepSlide PPT Requirements Assistant",
            content=content,
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model)

    def _ensure_agent(self) -> None:
        if self.agent is None:
            self._init_agent(system_extra_context=self._system_extra_context)

    def get_response(self, user_input: str) -> str:
        from camel.messages import BaseMessage

        self._ensure_agent()
        if not self.agent:
            raise RuntimeError("CamelAIClient: agent is not initialized")

        user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
        response = self.agent.step(user_msg)

        if getattr(response, "terminated", False):
            info = getattr(response, "info", None)
            return f"[AI Terminated] {info}"

        return (response.msg.content or "").strip()

    def clear_memory(self) -> None:
        if self.agent:
            self.agent.clear_memory()

    def set_context(self, paper_info: dict) -> None:
        file_name = paper_info.get("file_name") or ""
        abstract = paper_info.get("abstract") or ""
        merged_main = paper_info.get("merged_main") or ""
        project_dir = paper_info.get("project_dir") or ""

        ctx = (
            "Paper Context:\n"
            f"- File Name: {file_name}\n"
            f"- Project Dir: {project_dir}\n"
            f"- Merged Main: {merged_main}\n"
            f"- Abstract: {abstract}\n"
            "Use this context when asking questions and summarizing."
        )

        self._system_extra_context = ctx
        # Rebuild agent with new system context (lazy model init inside)
        self._init_agent(system_extra_context=ctx)
