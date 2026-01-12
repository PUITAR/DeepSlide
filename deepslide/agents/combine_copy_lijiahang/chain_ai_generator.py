import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool

try:
    from app import _log as app_log
except Exception:
    def app_log(msg: str):
        return None

def _wrap_tools_for_agent(tools: List) -> List[FunctionTool]:
    wrapped: List[FunctionTool] = []
    for t in tools:
        if isinstance(t, FunctionTool):
            wrapped.append(t)
        else:
            wrapped.append(FunctionTool(t))
    return wrapped

def generate_chain_via_tools(
    tools: List,
    focus_sections: List[str],
    duration_text: str,
    abstract_text: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    env_path: Optional[str] = "/home/ym/DeepSlide/deepslide/config/env/.env",
) -> Optional[Dict[str, Any]]:
    try:
        app_log("Load environment variables")
        load_dotenv(dotenv_path=env_path)
    except Exception:
        app_log("Load environment variables failed")
        pass
    api_key = os.getenv("DEFAULT_MODEL_API_KEY")
    model_type = os.getenv("DEFAULT_MODEL_TYPE", "deepseek-chat")
    base_url = os.getenv("DEFAULT_MODEL_API_URL", "https://api.deepseek.com")
    try:
        if not api_key or not base_url or not model_type:
            app_log("Create model failed: configuration missing")
            return None
        app_log("Create model")
        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=model_type,
            url=base_url,
            api_key=api_key,
            model_config_dict={"temperature": 0.2, "timeout": 120, "max_tokens": 4096},
        )
    except Exception:
        app_log("Create model failed")
        return None
    sys = (
        "You are a logic-chain generator for a research paper presentation.\n"
        "Minimize tool calls: call each tool at most once unless strictly necessary. Use cached info.\n"
        "Preferred order: list_outline (1) -> search_nodes (if needed) -> get_node_content_by_index (to read details).\n"
        "Output STRICT JSON wrapped in ```json ```:\n"
        "Example:\n"
        "```json\n"
        "{\n"
        '  "nodes": [\n'
        '    {"index": 0, "role": "Introduction", "text": "Background", "description": "...", "duration_ratio": 0.25},\n'
        '    {"index": 1, "role": "Methods", "text": "Model Design", "description": "...", "duration_ratio": 0.75}\n'
        "  ],\n"
        '  "edges": [\n'
        '    {"from_index": 0, "to_index": 1, "reason": "Introduce the problem before presenting the solution", "type": "sequential"}\n'
        "  ]\n"
        "}\n"
        "```\n"
        "Rules:\n"
        "1. roles come from focus_sections (preserve order).\n"
        "2. text must be the concise title of the node.\n"
        "3. description must be a detailed summary (2-3 sentences) combining paper content and user intent.\n"
        "4. duration sum ~= 1.0.\n"
        "5. Edges: Create sequential edges (type='sequential') for the main flow (0->1, 1->2, ...). Do NOT create reference edges (type='reference') initially."
    )
    app_log("Initialize tool agent")
    agent = ChatAgent(
        system_message=BaseMessage.make_assistant_message("LogicChainToolAgent", sys),
        model=model,
        tools=_wrap_tools_for_agent(tools),
    )
    try:
        agent.step_timeout = 1000
    except Exception:
        pass
    fs_str = ", ".join([str(x) for x in (focus_sections or [])])
    user = (
        "Generate logic chain using tools.\n"
        f"focus_sections: [{fs_str}]\n"
        f"total_duration: {duration_text}\n"
        f"abstract: {abstract_text[:1200]}\n"
        "Start by listing sections (tool), then read key excerpts, then produce JSON."
    )
    try:
        app_log("Generate logic chain")
        resp = agent.step(BaseMessage.make_user_message("User", user))
        content = (resp.msg.content or "").strip()
        app_log(f"Raw response content: {content}")
        try:
            # 尝试更加鲁棒的解析
            import re
            cleaned = content.strip()
            
            # 1. 尝试提取 ```json ... ``` 代码块
            match = re.search(r'```json\s*([\s\S]*?)\s*```', cleaned)
            if match:
                cleaned = match.group(1).strip()
            else:
                # 2. 尝试提取 { ... }
                match = re.search(r'\{[\s\S]*\}', cleaned)
                if match:
                    cleaned = match.group(0).strip()
            
            data = json.loads(cleaned)
            app_log(f"Generate logic chain completed, JSON size {len(cleaned)} characters")
            return data if isinstance(data, dict) else None
        except Exception as e:
            app_log(f"JSON parse failed: {e}")
            return None
    except Exception as e:
        app_log(f"Generate logic chain failed: {e}")
        return None
