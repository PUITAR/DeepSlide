from camel_client import CamelAIClient
from utils import extract_json_from_response, validate_requirements
import json

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
