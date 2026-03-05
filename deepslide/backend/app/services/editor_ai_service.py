import json
import logging
import os
import re
import concurrent.futures
from typing import List, Dict, Any, Optional

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

from app.core.agent_model_env import resolve_text_llm_env
from app.core.model_config import sanitize_model_config
from app.services.core.ppt_utils import extract_frame_by_index, replace_frame_in_content, parse_resp_for_editor


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
            "model_config_dict": sanitize_model_config(cfg.model_type, {"temperature": 0.2}),
        }
        if cfg.api_url:
            create_kwargs["url"] = cfg.api_url
        return ModelFactory.create(**create_kwargs)
    except Exception as e:
        logger.error(f"EditorAI client init failed for agent={agent}: {e}")
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


class EditorAIService:
    def plan_modifications(self, instruction: str, page_idx: int, speeches: List[str], project_path: str) -> List[Dict[str, Any]]:

        current_speech = speeches[page_idx] if page_idx < len(speeches) else ""
        current_latex = ""
        try:
            if page_idx == 0:
                title_path = os.path.join(project_path, "title.tex")
                if os.path.exists(title_path):
                    with open(title_path, "r") as f:
                        current_latex = f.read()
            else:
                tex_path = os.path.join(project_path, "content.tex")
                if os.path.exists(tex_path):
                    with open(tex_path, "r") as f:
                        full_tex = f.read()
                    match, _ = extract_frame_by_index(full_tex, page_idx)
                    if match:
                        current_latex = match
        except Exception as e:
            logger.error(f"Error getting latex context: {e}")

        allowed_actions = []
        is_added = "<add>" in current_speech
        if page_idx == 0:
            allowed_actions = ["MODIFY_TITLE_CONTENT", "MODIFY_SPEECH"]
        elif is_added:
            allowed_actions = ["MODIFY_SPEECH"]
        else:
            allowed_actions = ["MODIFY_SLIDE_CONTENT", "MODIFY_SPEECH"]

        system_prompt = (
            "You are a Presentation Editor Planner. Your goal is to break down the user's modification instruction "
            "into a list of specific executable actions. "
            f"You can ONLY use the following allowed actions: {json.dumps(allowed_actions)}. "
            "Return the plan as a strictly valid JSON list of objects, where each object has:\n"
            "- 'action': One of the allowed actions.\n"
            "- 'instruction': The specific sub-instruction for that action.\n"
            "\n"
            "Example Output:\n"
            "[\n"
            "  {\"action\": \"MODIFY_SLIDE_CONTENT\", \"instruction\": \"Change the bullet point about accuracy to 99%\"},\n"
            "  {\"action\": \"MODIFY_SPEECH\", \"instruction\": \"Mention that our accuracy reached 99%\"}\n"
            "]\n"
            "If the user instruction cannot be fulfilled by allowed actions, ignore that part or return empty list."
        )

        user_prompt = f"""
        User Instruction: "{instruction}"

        Context - Current Speech:
        "{current_speech}"

        Context - Current Slide Content:
        ```latex
        {current_latex}
        ```

        Plan the modifications (JSON format only):
        """

        try:
            resp = _call_llm("EDITOR", user_prompt, system_prompt)
            match = re.search(r"\[.*\]", resp, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.error(f"Planning error: {e}")

        return []

    def modify_title(self, project_path: str, instruction: str) -> bool:
        title_path = os.path.join(project_path, "title.tex")
        if not os.path.exists(title_path):
            return False

        with open(title_path, "r") as f:
            current = f.read()

        system_prompt = "You are a LaTeX Beamer expert. Modify the title/author/date information based on instruction. Return ONLY the modified content (e.g. \\title{...}\\author{...}) in ```latex```."
        full_prompt = f"Original title.tex:\n```latex\n{current}\n```\n\nInstruction: {instruction}"

        try:
            resp = _call_llm("EDITOR", full_prompt, system_prompt)
            new_content = parse_resp_for_editor(resp)
            if new_content:
                with open(title_path, "w") as f:
                    f.write(new_content)
                return True
        except Exception as e:
            logger.error(f"Modify title error: {e}")
        return False

    def modify_content(self, project_path: str, page_idx: int, instruction: str, speeches: List[str]) -> bool:
        frame_idx = 0
        for i in range(page_idx):
            if "<add>" not in speeches[i]:
                frame_idx += 1

        tex_path = os.path.join(project_path, "content.tex")
        if not os.path.exists(tex_path):
            return False

        with open(tex_path, "r") as f:
            full_tex = f.read()
        target_frame, _ = extract_frame_by_index(full_tex, frame_idx)
        if not target_frame:
            return False

        system_prompt = "You are a LaTeX Beamer expert. Modify the content based on instruction. Return ONLY the modified \\begin{frame}...\\end{frame} block in ```latex```. Avoid using '&' symbol in text, use 'and' instead."
        full_prompt = f"Original LaTeX:\n```latex\n{target_frame}\n```\n\nInstruction: {instruction}"

        try:
            resp = _call_llm("EDITOR", full_prompt, system_prompt)
            new_frame = parse_resp_for_editor(resp)
            if new_frame:
                new_full = replace_frame_in_content(full_tex, frame_idx, new_frame)
                with open(tex_path, "w") as f:
                    f.write(new_full)
                return True
        except Exception as e:
            logger.error(f"Modify content error: {e}")
        return False

    def modify_speech(self, project_path: str, page_idx: int, instruction: str, speeches: List[str]) -> Optional[str]:
        current_speech = speeches[page_idx]
        system_prompt = "You are a speech editor. Modify the speech script based on instruction. Return ONLY the modified speech text."
        full_prompt = f"Original Speech:\n{current_speech}\n\nInstruction: {instruction}"

        try:
            resp = _call_llm("EDITOR", full_prompt, system_prompt)
            new_speech = resp.strip()
            if new_speech:
                if "<add>" in current_speech and "<add>" not in new_speech:
                    new_speech = "<add> " + new_speech
                return new_speech
        except Exception as e:
            logger.error(f"Modify speech error: {e}")
        return None

    def recommend_edges(self, node_names: List[str], abstract: str = "") -> List[Dict[str, Any]]:
        names_txt = "\n".join([f"- {i}. {n}" for i, n in enumerate(node_names)])
        ctx = abstract[: min(1000, len(abstract))] if abstract else ""

        system_prompt = (
            "You are a logic chain edge recommender assistant.\n"
            "Based on the given node list (ordered) and context abstract, recommend a set of directed edges and provide a short reason for each edge.\n"
            "Output STRICT JSON: {\"edges\": [{\"from\": i, \"to\": j, \"reason\": \"...\"}, ...]}。\n"
            "Note: Do NOT output any explanation or markdown, ONLY JSON.\n"
        )

        user_prompt = (
            "Node list (0-indexed):\n"
            f"{names_txt}\n\n"
            "Context Abstract (optional):\n"
            f"{ctx}\n\n"
            "Please recommend a set of directed edges, including sequential relationships and key cross-node relationships. Return JSON ONLY."
        )

        try:
            resp = _call_llm("CHAIN", user_prompt, system_prompt)
            match = re.search(r"\{[\\s\\S]*\\}", resp)
            if match:
                data = json.loads(match.group(0))
                edges = data.get("edges", [])
                return edges if isinstance(edges, list) else []
        except Exception as e:
            logger.error(f"Recommend edges error: {e}")
        return []


editor_ai_service = EditorAIService()
