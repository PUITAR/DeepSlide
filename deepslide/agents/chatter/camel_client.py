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
            role_name="PPT需求助手",
            content="""
            你是PPT生成助手。你的任务是通过与用户对话，收集生成PPT所需的关键信息。
            需要询问的信息包括但不限于：目标受众、演讲时长、重点章节、风格偏好、特殊要求等。
            请逐步引导用户提供这些信息，每次只问一个问题，保持对话自然流畅。
            
            当你认为已经收集了足够信息后，或用户表达了“确认”、“完成”、“没有其他要求”等意思时，
            你必须执行以下操作：
            1. 输出一个包含以下字段的 JSON 结构（严格按照格式）：
            {
              "audience": "...",
              "duration": "...",
              "focus_sections": ["...", "..."],
              "style": "...",
              "special_notes": "..."
            }
            2. JSON 后面可以附加一句话总结：“以上是为您生成PPT的初步需求，是否确认？”
            3. 严禁继续提问，必须输出 JSON。
            """
        )
        self.agent = ChatAgent(system_message=sys_msg, model=self.model)

    def get_response(self, user_input):
        """获取 AI 回复"""
        user_msg = BaseMessage.make_user_message(role_name="User", content=user_input)
        response = self.agent.step(user_msg)
        
        if response.terminated:
            return f"[AI 终止] {response.info}"
        
        return response.msg.content.strip()

    def clear_memory(self):
        """清空对话记忆"""
        if self.agent:
            self.agent.clear_memory()