import os
import logging
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool
from app.services.llm_timeout import safe_agent_step

from app.core.model_config import sanitize_model_config
from app.services.core.utils import extract_json_from_response
from app.services.core.chapter_node import ChapterNode
from app.services.core.content_tree_builder import make_tree_tools
from app.services.core.chain_ai_generator import generate_chain_via_tools
from app.core.agent_model_env import resolve_text_llm_env

logger = logging.getLogger(__name__)


def _preview_text(value: Any, limit: int = 200) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    return s if len(s) <= limit else s[:limit] + "..."

class RequirementsCollector:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.conversation_history: List[Dict[str, str]] = []
        self.conversation_requirements: Dict[str, Any] = {}
        self.is_confirmed = False
        self.generated_chain: Optional[Dict[str, Any]] = None
        
        # Context
        self.paper_info = {}
        self.nodes: List[ChapterNode] = []
        
        # AI Setup
        self._init_ai()

    def _init_ai(self):
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))
        if os.path.exists(env_path):
            load_dotenv(env_path)
            
        cfg = resolve_text_llm_env("REQUIREMENTS")
        api_key = cfg.api_key
        if not api_key:
            logger.warning("LLM API Key not found for RequirementsCollector.")
            self.agent = None
            return

        platform_type = cfg.platform_type
        model_type = cfg.model_type
        base_url = cfg.api_url

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
            if base_url:
                create_kwargs["url"] = base_url

            self.model = ModelFactory.create(**create_kwargs)
            
            self.system_template = (
                "You are the DeepSlide PPT-generation assistant.\n"
                "Your goal is to help the user define the requirements for a presentation based on the uploaded paper.\n"
                "CRITICAL: Do NOT mention any tools or tool calls. Rely on the provided context (file name, abstract, and any user-provided info).\n"
                "Required Information to Collect:\n"
                "1. Target Audience\n"
                "2. Presentation Length (Duration)\n"
                "3. Key Sections (Focus)\n"
                "4. Style Preferences\n\n"
                "Interaction Style:\n"
                "- Be proactive. Read the paper content to guide the user.\n"
                "- Maintain context. Remember previous turns.\n"
                "- When the user provides new requirements, update your understanding.\n\n"
                "Completion Condition:\n"
                "When requirements are clear/confirmed, output the JSON strictly:\n"
                "```json\n"
                "{\n  \"audience\": \"...\",\n  \"duration\": \"...\",\n  \"focus_sections\": [\"...\"], \"style_preference\": \"...\"\n}\n"
                "```"
                "After the JSON, ask for confirmation.\n\n"
                "CRITICAL: Once the user confirms the requirements, output ONLY a brief acknowledgement (e.g., 'Great, generating logic chain...') and STOP.\n"
                "DO NOT generate any PPT outlines, slide content, or suggestions.\n"
                "DO NOT say any words about your target to collect requirements json and word *JSON*."
            )
            
            self._rebuild_agent()
            
        except Exception as e:
            logger.error(f"Failed to init AI: {e}")
            self.agent = None

    def _rebuild_agent(self):
        if not hasattr(self, 'model') or not self.model: return
        
        # Construct context string
        context_str = ""
        if self.paper_info:
             context_str = (
                f"\n\nPaper Context:\n"
                f"- File Name: {self.paper_info.get('file_name')}\n"
                f"- Abstract: {self.paper_info.get('abstract')}\n"
                "Use this context when asking questions and summarizing."
            )

        sys_msg = BaseMessage.make_assistant_message(
            role_name="Assistant",
            content=self.system_template + context_str
        )
        
        self.agent = ChatAgent(system_message=sys_msg, model=self.model)

    def set_context(self, file_name: str, abstract: str):
        self.paper_info = {
            "file_name": file_name,
            "abstract": abstract
        }
        self._rebuild_agent()
        
    def set_nodes(self, nodes: List[ChapterNode]):
        self.nodes = nodes
        self._rebuild_agent()

    def process_input(self, user_input: str) -> str:
        if not self.agent:
            return "AI Service Unavailable (Check API Key)"

        self.conversation_history.append({"role": "user", "content": user_input})

        def _strip_json_blocks(text: str) -> str:
            if not text:
                return ""
            out = re.sub(r"```json\s*[\s\S]*?```", "", str(text), flags=re.IGNORECASE)
            out = re.sub(r"```\s*[\s\S]*?```", "", out)
            return "\n".join([ln.rstrip() for ln in out.splitlines() if ln.strip()]).strip()

        def _summarize(reqs: Dict[str, Any]) -> str:
            audience = str(reqs.get("audience", "")).strip()
            duration = str(reqs.get("duration", "")).strip()
            focus = reqs.get("focus_sections")
            style = str(reqs.get("style_preference", "")).strip()
            focus_txt = ", ".join([str(x) for x in focus]) if isinstance(focus, list) and focus else ""
            parts = []
            if audience:
                parts.append(f"Audience: {audience}")
            if duration:
                parts.append(f"Duration: {duration}")
            if focus_txt:
                parts.append(f"Focus: {focus_txt}")
            if style:
                parts.append(f"Style: {style}")
            base = "; ".join(parts) if parts else "Noted your requirements."
            return base

        def _ready_for_recommendation(reqs: Dict[str, Any]) -> bool:
            try:
                audience = str(reqs.get("audience", "")).strip()
                duration = str(reqs.get("duration", "")).strip()
                focus = reqs.get("focus_sections")
                has_focus = isinstance(focus, list) and any(str(x).strip() for x in focus)
                return bool(audience and duration and has_focus)
            except Exception:
                return False

        try:
            user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
            response = safe_agent_step(self.agent, user_msg, timeout_seconds=30.0)
            if not response:
                return "Sorry, the AI service timed out processing your request."
            raw = (response.msg.content or "").strip()

            extracted = extract_json_from_response(raw)
            if extracted:
                self.conversation_requirements.update(extracted)

            clean = _strip_json_blocks(raw)
            if extracted:
                clean = _summarize(self.conversation_requirements)

            if extracted and _ready_for_recommendation(self.conversation_requirements):
                self.is_confirmed = True
                clean = "Got it. I'm generating logic-chain candidates—please pick one to proceed to the Logic Chain stage."

            if "generating logic chain" in raw.lower() or self.is_confirmed:
                self.is_confirmed = True
                clean = "Got it. I'm generating logic-chain candidates—please pick one to proceed to the Logic Chain stage."

            self.conversation_history.append({"role": "assistant", "content": clean})
            return clean
        except Exception as e:
            logger.error(f"AI Step error: {e}")
            return "Sorry, I encountered an error processing your request."

    def _generate_logic_chain(self):
        if not self.nodes:
            logger.warning("No nodes available for logic chain generation.")
            return

        logger.info("Generating logic chain...")
        tools = make_tree_tools(self.nodes)
        
        req = self.conversation_requirements
        
        chain_data = generate_chain_via_tools(
            tools=tools,
            focus_sections=req.get("focus_sections", []),
            duration_text=req.get("duration", "5min"),
            abstract_text=self.paper_info.get("abstract", ""),
            conversation_history=self.conversation_history
        )
        
        if chain_data:
            self.generated_chain = chain_data
            logger.info(f"Logic chain generated with {len(chain_data.get('nodes', []))} nodes.")
        else:
            logger.error("Failed to generate logic chain.")

class RequirementsService:
    def __init__(self):
        self.collectors: Dict[str, RequirementsCollector] = {}

    def get_collector(self, project_id: str) -> RequirementsCollector:
        if project_id not in self.collectors:
            self.collectors[project_id] = RequirementsCollector(project_id)
        return self.collectors[project_id]
    
    def init_project(self, project_id: str, file_name: str, abstract: str, nodes: List[Dict[str, Any]] = None):
        collector = self.get_collector(project_id)
        collector.set_context(file_name, abstract)
        
        if nodes:
            # Convert dicts back to ChapterNodes
            chapter_nodes = [ChapterNode.from_dict(n) for n in nodes]
            collector.set_nodes(chapter_nodes)
        
        # Add initial greeting
        if not collector.conversation_history:
             greeting = "Hello! I've analyzed your paper. To get started, please tell me:\n- Who is the audience?\n- Presentation duration?\n- Which chapters to highlight?\n- Style preference?"
             if abstract:
                 greeting = f"**Abstract detected:**\n{_preview_text(abstract)}\n\n" + greeting
             
             collector.conversation_history.append({"role": "assistant", "content": greeting})

requirements_service = RequirementsService()
