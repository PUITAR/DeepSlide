import json
import os
from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.toolkits import FunctionTool

from utils import extract_json_from_response, validate_requirements

class CamelAIClient:
    def __init__(self, env_path=None):
        # self.env_path = env_path or '/home/ym/DeepSlide/deepslide/config/env/.env'
        self.env_path = env_path or os.path.join(os.path.dirname(__file__), '../config/env/.env')
        load_dotenv(self.env_path)
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
            "```json\n"
            "{\n  \"audience\": \"...\",\n  \"duration\": \"...\",\n  \"focus_sections\": [\"...\"], \"style_preference\": \"...\"\n}\n"
            "```"
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
        """Get AI response for user input"""
        try:
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
        except Exception as e:
            print(f"Error in CamelAIClient.get_response: {e}")
            import traceback
            traceback.print_exc()
            return f"Error communicating with AI: {str(e)}"

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

class PPTRequirementsCollector:
    def __init__(self, env_path=None):
        self.camel_client = CamelAIClient(env_path)
        self.paper_file_name = ""
        self.paper_project_dir = ""
        self.paper_main_tex = ""
        self.paper_abstract = ""
        self.merged_main_path = ""
        self.conversation_history = []
        self.conversation_requirements = {}
        self.is_confirmed = False  # ✅ 保留此状态，但会配合 app_state 使用

    def set_paper_file(self, file_name):
        """设置论文文件名"""
        self.paper_file_name = file_name

    def set_paper_project(self, project_dir, main_tex_path=None, merged_main_path=None):
        self.paper_project_dir = project_dir or ""
        self.paper_main_tex = main_tex_path or ""
        self.merged_main_path = merged_main_path or ""

    def set_paper_abstract(self, abstract_text):
        self.paper_abstract = abstract_text or ""

    def prime_context(self):
        self.camel_client.set_context({
            "file_name": self.paper_file_name,
            "project_dir": self.paper_project_dir,
            "main_tex": self.paper_main_tex,
            "merged_main": self.merged_main_path,
            "abstract": self.paper_abstract,
        })

    def _llm_judge_user_intent(self, user_input: str) -> bool:
        """
        Call LLM to determine if the user's input expresses a clear intent of "confirmation".
        Return True if the user has confirmed, False otherwise.
        """
        prompt = f"""Please judge whether the following user input expresses a clear intent of "confirmation" or "agreement".
If the user says something like "ok", "fine", "confirm", "no problem", "yes", etc., indicating agreement, please reply "YES".
If the user is still asking questions, requesting changes, expressing denial or hesitation, please reply "NO".
Only reply "YES" or "NO", do not output any other content.

User Input: {user_input}"""
        # Use lightweight call, do not pollute main conversation history
        judge_response = self.camel_client.get_response(prompt, system_prompt="You are an intent judgment assistant, only answer YES or NO.").strip().upper()
        return judge_response == "YES"

    def process_user_input(self, user_input):
        """处理用户输入，返回 AI 回复"""
        # 保存用户输入
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # 获取 AI 回复
        ai_response = self.camel_client.get_response(user_input)
        
        extracted_data = extract_json_from_response(ai_response)
        
        # 判断用户意图是否为确认
        is_user_agreeing = self._llm_judge_user_intent(user_input)
        is_user_providing_json = extract_json_from_response(user_input) is not None
        
        if extracted_data:
            self.conversation_requirements.update(extracted_data)
            # 如果这一轮包含JSON且用户也确认了（或者直接给JSON），则锁定
            if is_user_agreeing or is_user_providing_json:
                self.is_confirmed = True
        else:
            # 如果这一轮 AI 没有输出 JSON（例如只是确认 "Great..."），但用户意图是确认，且我们之前已经收集了需求
            if is_user_agreeing and self.conversation_requirements:
                self.is_confirmed = True
        
        # 保存 AI 回复
        self.conversation_history.append({"role": "assistant", "content": ai_response})
        
        return ai_response

    def get_requirements(self):
        """获取当前收集到的需求"""
        return {
            "paper_info": {
                "file_name": self.paper_file_name,
                "project_dir": self.paper_project_dir,
                "main_tex": self.paper_main_tex,
                "merged_main": self.merged_main_path,
                "abstract": self.paper_abstract,
            },
            "conversation_requirements": self.conversation_requirements,
            "conversation_history": self.conversation_history
        }

    def confirm_requirements(self):
        """确认需求（可选，用于手动触发）"""
        self.is_confirmed = True

    def reset(self):
        """重置收集器状态"""
        self.conversation_history = []
        self.conversation_requirements = {}
        self.is_confirmed = False
        self.paper_file_name = ""
        self.paper_project_dir = ""
        self.paper_main_tex = ""
        self.paper_abstract = ""
        self.merged_main_path = ""
        self.camel_client.clear_memory()
