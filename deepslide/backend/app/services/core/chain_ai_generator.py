import os
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool
from app.core.model_config import build_model_config
from app.core.agent_model_env import resolve_text_llm_env
from app.services.llm_timeout import safe_agent_step
from app.services.core.logic_chain_budget import parse_total_minutes, target_node_range, enforce_max_nodes

logger = logging.getLogger(__name__)


def _preview_text(value: Any, limit: int = 200) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    return s if len(s) <= limit else s[:limit] + "..."

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
    env_path: Optional[str] = None,
    variant: str = "pipeline",
    extra_guidance: str = "",
) -> Optional[Dict[str, Any]]:
    
    if not env_path:
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.env"))

    try:
        logger.info(f"Load environment variables from {env_path}")
        load_dotenv(dotenv_path=env_path)
    except Exception:
        logger.warning("Load environment variables failed")
        pass
        
    cfg = resolve_text_llm_env("CHAIN")
    api_key = cfg.api_key
    platform_type = cfg.platform_type
    model_type = cfg.model_type
    base_url = cfg.api_url
    
    try:
        if not api_key:
            logger.error("Create model failed: configuration missing (API KEY)")
            return None
        logger.info(f"Create model platform={platform_type} type={model_type}")
        try:
            model_platform = ModelPlatformType(platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL

        create_kwargs = {
            "model_platform": model_platform,
            "model_type": model_type,
            "api_key": api_key,
            "model_config_dict": build_model_config(
                model_type=model_type,
                temperature=0.2,
                max_tokens=4096,
                timeout=300,
            ),
        }
        if base_url:
            create_kwargs["url"] = base_url

        model = ModelFactory.create(**create_kwargs)
    except Exception as e:
        logger.error(f"Create model failed: {e}")
        return None
        
    variant = str(variant or "pipeline")

    variant_block = ""
    if variant == "hook":
        variant_block = (
            "\nVariant: hook\n"
            "- You MUST start with a strong Hook node (role='Hook') that states the most interesting result/pain point.\n"
            "- After Hook, follow the main flow of focus_sections.\n"
            "- Ensure the first node text is compelling and concise (<= 12 words).\n"
        )
    elif variant == "bluf":
        variant_block = (
            "\nVariant: bluf\n"
            "- You MUST start with a BottomLine node that states the conclusion in <= 12 words.\n"
            "- Then provide 2-3 supporting nodes (Reasons/Evidence) aligned with focus_sections.\n"
            "- End with Takeaway or Caveats.\n"
        )
    elif variant == "faq":
        variant_block = (
            "\nVariant: faq\n"
            "- Structure the chain as a Q/A driven story (use role='Q' and role='A').\n"
            "- Include at least 3 Q/A pairs, then a final Takeaway.\n"
            "- Questions should be sharp and reflect common reviewer/audience doubts.\n"
        )

    def _get_tool_map(items: List) -> Dict[str, Any]:
        m: Dict[str, Any] = {}
        for t in items or []:
            if isinstance(t, FunctionTool):
                name = getattr(getattr(t, "func", None), "__name__", "") or ""
                if name:
                    m[name] = t
            else:
                name = getattr(t, "__name__", "") or ""
                if name:
                    m[name] = t
        return m

    tool_map = _get_tool_map(tools)
    outline = ""
    try:
        if "list_outline" in tool_map:
            outline = str(tool_map["list_outline"]() or "")
    except Exception:
        outline = ""

    excerpts: List[str] = []
    try:
        if focus_sections and "search_nodes" in tool_map:
            for sec in focus_sections[:6]:
                q = str(sec or "").strip()
                if not q:
                    continue
                res = str(tool_map["search_nodes"](q, 3) or "")
                if res:
                    excerpts.append(f"[search_nodes:{q}]\n{res}")
        if "read_main_excerpt" in tool_map:
            ex = str(tool_map["read_main_excerpt"]() or "")
            if ex:
                excerpts.append(f"[read_main_excerpt]\n{ex}")
    except Exception:
        pass

    total_minutes = parse_total_minutes(duration_text, default=10)
    min_nodes, max_nodes = target_node_range(total_minutes)
    max_nodes = min(int(max_nodes), int(total_minutes))
    min_nodes = min(int(min_nodes), int(max_nodes))

    sys = (
        "You are a logic-chain generator for a research paper presentation.\n"
        "You must NOT mention tools or tool calls. Use the provided outline/excerpts and user requirements.\n"
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
        "CRITICAL RULES:\n"
        "1. **PRIORITIZE USER INTENT**: If 'User Requirements Context' or 'total_duration' implies a specific structure (e.g. 'only Methods and Results', '3 minutes'), you MUST follow it.\n"
        "2. **TEMPLATES ARE REFERENCE ONLY**: If a narrative template conflicts with user intent or duration constraints, you MUST compress/merge template roles to satisfy constraints.\n"
        f"3. **HARD CONSTRAINT**: total_duration={duration_text} (~{total_minutes} minutes). You MUST output between {min_nodes} and {max_nodes} nodes.\n"
        "4. roles should follow the focus_sections or user instructions. You may add extra roles: Hook, Takeaway, Extra.\n"
        "5. text must be the concise title of the node (<= 10 words).\n"
        "6. description must be a detailed summary (2-3 sentences) combining paper content and user intent.\n"
        "7. duration sum ~= 1.0.\n"
        "8. Edges: Create sequential edges (type='sequential') for the main flow (0->1, 1->2, ...). Do NOT create reference edges (type='reference') initially.\n"
        "9. LANGUAGE: Output node text and description in English."
        + variant_block
        + ("\n" + str(extra_guidance) if extra_guidance else "")
    )
    
    agent = ChatAgent(
        system_message=BaseMessage.make_assistant_message("LogicChainAgent", sys),
        model=model,
    )
    
    fs_str = ", ".join([str(x) for x in (focus_sections or [])])
    
    # Include conversation context
    context_str = ""
    if conversation_history:
        # Simplified context
        msgs = [f"{m['role']}: {m['content']}" for m in conversation_history[-6:]] # Last 3 turns
        context_str = "\nUser Requirements Context:\n" + "\n".join(msgs)
        
    user = (
        "Generate a logic chain.\n"
        f"focus_sections: [{fs_str}]\n"
        f"total_duration: {duration_text}\n"
        f"abstract: {abstract_text}\n"
        f"outline:\n{outline}\n"
        f"excerpts:\n{('\\n\\n'.join(excerpts) if excerpts else '')}\n"
        f"{context_str}\n"
        f"variant: {variant}\n"
        "Produce JSON only."
    )
    
    def _extract_json_dict(raw_text: str) -> Optional[Dict[str, Any]]:
        try:
            import re
            cleaned = str(raw_text or "").strip()
            match = re.search(r"```json\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()
            else:
                match = re.search(r"\{[\s\S]*\}", cleaned)
                if match:
                    cleaned = match.group(0).strip()
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _needs_repair(chain: Dict[str, Any]) -> bool:
        nodes = chain.get("nodes") if isinstance(chain, dict) else None
        if not isinstance(nodes, list) or not nodes:
            return True
        k = len(nodes)
        if k < int(min_nodes) or k > int(max_nodes):
            return True
        return False

    def _repair_chain_once(chain: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        repair_sys = (
            "You are a logic-chain repairer.\n"
            "You MUST output STRICT JSON wrapped in ```json```.\n"
            "Do NOT mention tools.\n"
            "HARD CONSTRAINTS:\n"
            f"- total_duration: {duration_text} (~{total_minutes} minutes)\n"
            f"- number_of_nodes MUST be between {min_nodes} and {max_nodes}\n"
            "- Templates are reference only; you may merge/omit template roles to satisfy constraints.\n"
            "- duration_ratio must be positive and sum ~= 1.0.\n"
            "- Edges must be sequential (0->1->2...).\n"
            "- Output in English.\n"
        )
        repair_agent = ChatAgent(
            system_message=BaseMessage.make_assistant_message("LogicChainRepairAgent", repair_sys),
            model=model,
        )
        fs = ", ".join([str(x) for x in (focus_sections or [])])
        prompt = (
            "Repair the following logic chain JSON to satisfy constraints.\n"
            f"focus_sections: [{fs}]\n"
            f"variant: {variant}\n"
            f"template_guidance:\n{str(extra_guidance or '')}\n"
            f"original_chain_json:\n{json.dumps(chain, ensure_ascii=False)}\n"
            "Return JSON only."
        )
        r = safe_agent_step(repair_agent, BaseMessage.make_user_message("User", prompt), timeout_seconds=60.0)
        if not r:
            return None
        return _extract_json_dict((r.msg.content or "").strip())

    try:
        logger.info("Generate logic chain step")
        resp = safe_agent_step(agent, BaseMessage.make_user_message("User", user), timeout_seconds=90.0)
        if not resp:
            logger.error("Generate logic chain timed out")
            return None
        content = (resp.msg.content or "").strip()
        logger.info(f"Raw response content: {_preview_text(content)}")
        
        data = _extract_json_dict(content)
        if not data:
            logger.error("JSON parse failed")
            return None

        if _needs_repair(data):
            repaired = _repair_chain_once(data)
            if repaired and not _needs_repair(repaired):
                data = repaired

        try:
            nodes = data.get("nodes") if isinstance(data, dict) else None
            if isinstance(nodes, list) and nodes:
                capped = enforce_max_nodes(nodes, max_nodes=max_nodes)
                data["nodes"] = capped
        except Exception:
            pass

        logger.info("Generate logic chain completed")
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.error(f"Generate logic chain failed: {e}")
        return None
