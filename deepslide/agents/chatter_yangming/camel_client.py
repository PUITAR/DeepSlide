# Chatter.py
import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage

class CamelAIClient:
    def __init__(self, env_path=None):
        self.env_path = env_path or '/home/ym/DeepSlide/deepslide/config/env/.env'
        self.model = None
        self.agent = None
        self.system_template = (
            "You are the DeepSlide PPT-generation assistant. Your task is to collect the key information required to create a presentation through a conversation with the user.\n"
            "Ask about, but not limited to: target audience, presentation length, key sections, style preferences, special requirements, etc.\n"
            "Guide the user to provide this information step by step, asking only one question at a time and keeping the dialogue natural and smooth.\n\n"
            "When you believe enough information has been gathered, or the user expresses confirmation, completion, or no other requirements, you must:\n"
            "1. Output a JSON structure containing the following fields (strictly follow the format):\n"
            "{\n  \"audience\": \"...\",\n  \"duration\": \"...\",\n  \"focus_sections\": [\"...\", \"...\"],\n  \"style\": \"...\",\n  \"special_notes\": \"...\"\n}\n"
            "2. After the JSON, you may append one summary sentence: The above are the preliminary requirements for generating your PPT. Do you confirm?\n"
            "3. Do not ask any further questions; you must output the JSON."
        )
        self._init_model()
        self._init_agent()

    def _init_model(self):
        load_dotenv(dotenv_path=self.env_path)
        api_key = os.getenv('DEEPSEEK_API_KEY')
        platform_type = os.getenv('DEFAULT_MODEL_PLATFORM_TYPE', 'deepseek')
        model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
        
        self.model = ModelFactory.create(
            model_platform=ModelPlatformType(platform_type),
            model_type=model_type,
            api_key=api_key,
        )

    def _init_agent(self):
        sys_msg = BaseMessage.make_assistant_message(
            role_name="DeepSlide PPT-generation Assistant",
            content=self.system_template
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model)

    def get_response(self, user_input):
        """获取 AI 回复"""
        user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
        response = self.agent.step(user_msg)
        
        if response.terminated:
            return f"[AI Terminated] {response.info}"
        
        return response.msg.content.strip()

    def clear_memory(self):
        """清空对话记忆"""
        if self.agent:
            self.agent.clear_memory()

    def set_context(self, paper_info: dict):
        file_name = paper_info.get("file_name") or ""
        abstract = paper_info.get("abstract") or ""
        merged_main = paper_info.get("merged_main") or ""
        project_dir = paper_info.get("project_dir") or ""
        ctx = (
            f"\n\nPaper Context:\n"
            f"- File Name: {file_name}\n"
            f"- Project Dir: {project_dir}\n"
            f"- Merged Main: {merged_main}\n"
            f"- Abstract: {abstract}\n"
            "Use this context when asking questions and summarizing."
        )
        sys_msg = BaseMessage.make_assistant_message(
            role_name="DeepSlide PPT-generation Assistant",
            content=self.system_template + ctx
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model)
