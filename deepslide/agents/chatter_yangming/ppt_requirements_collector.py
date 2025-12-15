# ppt_requirements_collector.py
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

    def process_user_input(self, user_input):
        """处理用户输入，返回 AI 回复"""
        # 保存用户输入
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # 获取 AI 回复
        ai_response = self.camel_client.get_response(user_input)
        
        # 尝试提取 JSON 数据
        extracted_data = extract_json_from_response(ai_response)
        if extracted_data:
            self.conversation_requirements.update(extracted_data)
            self.is_confirmed = True  # 标记为已确认
        
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
