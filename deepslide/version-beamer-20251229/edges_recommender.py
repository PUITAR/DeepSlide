import os
from typing import List, Dict, Any, Optional
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool
from dotenv import load_dotenv
try:
    from app import _log as app_log
except Exception:
    def app_log(msg: str):
        return None

class EdgesRecommender:
    def __init__(self) -> None:
        try:
            env_path = os.path.join(os.path.dirname(__file__), "../../config/env/.env")
            load_dotenv(dotenv_path=env_path)
        except Exception:
            pass
        try:
            mt = os.getenv("DEFAULT_MODEL_TYPE", "deepseek-chat")
            url = os.getenv("DEFAULT_MODEL_API_URL", "https://api.deepseek.com")
            key = os.getenv("DEFAULT_MODEL_API_KEY")
            if not mt or not url or not key:
                self.model = None
                app_log("Model Phase: Edges recommender config missing")
            else:
                app_log("Model Phase: Create edges recommender model")
                self.model = ModelFactory.create(
                    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
                    model_type=mt,
                    url=url,
                    api_key=key,
                    model_config_dict={"temperature": 0.2, "timeout": 60, "max_tokens": 4096},
                )
        except Exception:
            self.model = None
            app_log("Model Phase: Failed to create edges recommender model")
        sys = (
            "You are a logic chain edge recommender assistant.\n"
            "Based on the given node list (ordered) and context abstract, recommend a set of directed edges and provide a short reason for each edge.\n"
            "Output STRICT JSON: {\"edges\": [{\"from\": i, \"to\": j, \"reason\": \"...\"}, ...]}。\n"
            "Note: Do NOT output any explanation or markdown, ONLY JSON.\n"
        )
        try:
            if self.model:
                self.agent = ChatAgent(system_message=BaseMessage.make_assistant_message("EdgeRecommender", sys), model=self.model)
            else:
                self.agent = None
        except Exception:
            self.agent = None

    def recommend(self, node_names: List[str], context_text: str, tools: Optional[List] = None) -> List[Dict[str, Any]]:
        import json
        import re
        names_txt = "\n".join([f"- {i}. {n}" for i, n in enumerate(node_names)])
        ctx = context_text[:4000] if context_text else ""
        user = (
            "Node list (0-indexed):\n"
            f"{names_txt}\n\n"
            "Context Abstract (optional):\n"
            f"{ctx}\n\n"
            "Please recommend a set of directed edges, including sequential relationships and key cross-node relationships. Return JSON ONLY."
        )
        try:
            if not self.model:
                return []
            if tools:
                tlist = [t if isinstance(t, FunctionTool) else FunctionTool(t) for t in tools]
                # Re-define system message to include rules
                sys_content = (
                    "You are a logic chain edge recommender assistant.\n"
                    "Based on the given node list (ordered) and context abstract, recommend a set of directed edges and provide a short reason for each edge.\n"
                    "Output STRICT JSON: {\"edges\": [{\"from\": i, \"to\": j, \"reason\": \"...\"}, ...]}。\n"
                    "Note: Do NOT output any explanation or markdown, ONLY JSON.\n"
                    "IMPORTANT: The output must be valid JSON format, do NOT include ```json ... ``` markers."
                )
                sys_msg = BaseMessage.make_assistant_message("EdgeRecommender", sys_content)
                agent = ChatAgent(system_message=sys_msg, model=self.model, tools=tlist)
                app_log("Model Phase: Start recommending edges (with tools)")
                resp = agent.step(BaseMessage.make_user_message("User", user))
            else:
                if not self.agent:
                    return []
                app_log("Model Phase: Start recommending edges")
                resp = self.agent.step(BaseMessage.make_user_message("User", user))
            
            content = (resp.msg.content or "").strip()
            
            # Robust JSON extraction
            try:
                # 1. Try direct parse
                data = json.loads(content)
            except json.JSONDecodeError:
                # 2. Try to find code block
                match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
                if match:
                    try:
                        data = json.loads(match.group(1))
                    except:
                        data = {}
                else:
                    # 3. Try to find { ... }
                    match = re.search(r'\{[\s\S]*\}', content)
                    if match:
                        try:
                            data = json.loads(match.group(0))
                        except:
                            data = {}
                    else:
                        data = {}
            
            edges = data.get("edges") or []
            app_log(f"Model Phase: Edge count {len(edges)}")
            return edges if isinstance(edges, list) else []
        except Exception as e:
            app_log(f"Model Phase: Edge recommendation failed {e}")
            return []
