# Chatter.py
import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool

class CamelAIClient:
    def __init__(self, env_path=None):
        self.env_path = env_path or '/home/ym/DeepSlide/deepslide/config/env/.env'
        self.model = None
        self.agent = None
        self.tools = []
        self.context_str = ""
        self.system_template = (
            "You are the DeepSlide PPT-generation assistant. You have access to the paper's content via tools.\n"
            "Your goal is to help the user define the requirements for a presentation based on the uploaded paper.\n"
            "CRITICAL: DO NOT ask the user for information you can find in the paper. Instead, use tools like `list_outline` or `read_main_excerpt` to understand the paper first, then make informed suggestions.\n"
            "For example:\n"
            "- Instead of asking 'What is the topic?', use tools to find the title and abstract.\n"
            "- Instead of asking 'Which sections to cover?', suggest key sections based on the duration (e.g., 'For a 10min talk, I suggest focusing on Method and Experiments sections [index 2, 3].').\n\n"
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
            "{\n  \"audience\": \"...\",\n  \"duration\": \"...\",\n  \"focus_sections\": [\"...\"], \"style_preference\": \"...\"\n}\n"
            "After the JSON, ask for confirmation.\n\n"
            "CRITICAL: Once the user confirms the requirements, output ONLY a brief acknowledgement (e.g., 'Great, generating logic chain...') and STOP. DO NOT generate any PPT outlines, slide content, or suggestions. The next step is handled by another agent."
        )
        self._init_model()
        self._init_agent()

    def _init_model(self):
        load_dotenv(dotenv_path=self.env_path)
        api_key = os.getenv('DEFAULT_MODEL_API_KEY')
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
        self.agent = ChatAgent(system_message=sys_msg, model=self.model, tools=self.tools)

    def get_response(self, user_input, system_prompt=None):
        """获取 AI 回复"""
        # 如果提供了临时 system_prompt，创建一个新的轻量级 agent 来处理
        if system_prompt:
             # 创建临时 agent
             temp_sys_msg = BaseMessage.make_assistant_message(
                 role_name="Temp Assistant",
                 content=system_prompt
             )
             temp_agent = ChatAgent(system_message=temp_sys_msg, model=self.model)
             user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
             response = temp_agent.step(user_msg)
             if response.terminated:
                 return f"[AI Terminated] {response.info}"
             return response.msg.content.strip()

        # 否则使用主 agent
        user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
        response = self.agent.step(user_msg)
        
        if response.terminated:
            return f"[AI Terminated] {response.info}"
        
        return response.msg.content.strip()

    def clear_memory(self):
        """清空对话记忆"""
        if self.agent:
            self.agent.clear_memory()

    def set_tools(self, tools):
        """设置工具（用于在收集需求时调用论文检索/阅读工具）"""
        self.tools = [t if isinstance(t, FunctionTool) else FunctionTool(t) for t in tools]
        sys_msg = BaseMessage.make_assistant_message(
            role_name="DeepSlide PPT-generation Assistant",
            content=self.system_template + self.context_str
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model, tools=self.tools)

    def set_context(self, paper_info: dict):
        file_name = paper_info.get("file_name") or ""
        abstract = paper_info.get("abstract") or ""
        merged_main = paper_info.get("merged_main") or ""
        project_dir = paper_info.get("project_dir") or ""
        self.context_str = (
            f"\n\nPaper Context:\n"
            f"- File Name: {file_name}\n"
            f"- Project Dir: {project_dir}\n"
            f"- Merged Main: {merged_main}\n"
            f"- Abstract: {abstract}\n"
            "Use this context when asking questions and summarizing."
        )
        sys_msg = BaseMessage.make_assistant_message(
            role_name="DeepSlide PPT-generation Assistant",
            content=self.system_template + self.context_str
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model, tools=self.tools)
