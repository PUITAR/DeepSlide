from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.types import ModelPlatformType
from camel.models import ModelFactory
import json
import os
from typing import List, Dict, Any

class RelationshipExplainer:
    def __init__(self):
        sys_msg_content = (
            "你是一个学术逻辑说明专家。你将根据给定的节点列表与选中的关系对，"
            "为每一对节点生成尽量详细的逻辑关系说明。"
            "输出必须是合法的 JSON，包含一个列表，其中每个元素为："
            "{\"from_index\": 整数, \"to_index\": 整数, \"explanation\": \"详细说明\"}。"
            "说明需包含关系类型或性质（如因果、递进、对比、补充等）以及2-3句中文解释，避免使用 Markdown。"
        )
        self.system_message = BaseMessage.make_assistant_message(
            role_name="RelationExplainer",
            content=sys_msg_content
        )
        api_key = os.getenv('DEEPSEEK_API_KEY')
        self.model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            url='https://api.deepseek.com',
            api_key=api_key,
            model_config_dict={"temperature": 0.3}
        )
        self.agent = ChatAgent(
            system_message=self.system_message,
            model=self.model,
            message_window_size=10
        )

    def explain(self, nodes: List[str], edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not nodes or not edges:
            return edges
        user_prompt = "节点列表：\n"
        for idx, n in enumerate(nodes):
            user_prompt += f"{idx}. {n}\n"
        user_prompt += "\n需要说明的关系对（使用索引）：\n"
        for e in edges:
            user_prompt += f"{e['from_index']} -> {e['to_index']}\n"
        user_prompt += "\n请返回 JSON 列表，每项包含 from_index、to_index、explanation。"
        user_message = BaseMessage.make_user_message(role_name="User", content=user_prompt)
        try:
            resp = self.agent.step(user_message)
            content = resp.msg.content
            content = content.replace("```json", "").replace("```", "").strip()
            result = json.loads(content)
            by_key = {(item.get("from_index"), item.get("to_index")): item.get("explanation", "") for item in result if isinstance(item, dict)}
            enriched = []
            for e in edges:
                key = (e["from_index"], e["to_index"])
                detail = by_key.get(key, "")
                enriched.append({**e, "detail": detail})
            return enriched
        except Exception:
            return edges
