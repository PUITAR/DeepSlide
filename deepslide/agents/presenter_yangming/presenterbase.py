import os
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.types import ModelPlatformType
from camel.models import ModelFactory
from dotenv import load_dotenv
from deepslide.agents.presenter.utils import parse_presentation

class PresenterAgent:
    def __init__(self):
        sys_msg_content = (
            "你是一位专业的公众演讲家。任务是根据 Slide 内容生成**中文演讲稿**。\n\n"
            "### 核心要求：\n"
            "1. **开场与自我介绍**：输入的第一页通常是封面（包含标题、作者）。"
            "请在这一部分进行大气的开场，介绍演讲主题并做自我介绍（我是...）。\n"
            "2. **口语化**：使用自然的连接词（“接下来”、“大家请看图表”）。\n"
            "3. **结构**：为**每一页 Slide** 生成一段独立的演讲词。\n"
            "4. **分隔符**：不同 Slide 之间必须严格用 `<next>` 隔开。\n"
            "5.**符号禁用**：你生成的结果务必不要出现markdown符号。\n"
            "5. **结尾**：如果是参考文献或致谢页，请礼貌地结束演讲。"
        )
        
        self.system_message = BaseMessage.make_assistant_message(
            role_name="Presenter",
            content=sys_msg_content
        )

    def generate_script(self, base_tex_path: str, content_tex_path: str, output_file_path: str):
        """
        :param base_tex_path: base.tex 路径 (用于提取封面和框架)
        :param content_tex_path: content.tex 路径 (主要内容)
        :param output_file_path: 输出 txt 路径
        """
        print(f"[Presenter] 正在解析: {base_tex_path} + {content_tex_path} ...")
        
        slides = parse_presentation(base_tex_path, content_tex_path)
        
        if not slides:
            print("[Presenter] 错误: 未提取到任何 Slide 内容。")
            return

        print(f"[Presenter] 共提取到 {len(slides)} 页 Slide (含封面/参考文献)。正在请求模型...")

        # 2. 构建 User Prompt
        user_prompt = "以下是按顺序排列的幻灯片内容，请生成演讲稿：\n\n"
        for idx, slide_text in enumerate(slides):
            # 标记 Slide 类型，辅助模型理解
            label = "封面/Title Page" if idx == 0 else f"第 {idx + 1} 页 Slide"
            user_prompt += f"=== {label} ===\n{slide_text}\n\n"
        
        user_prompt += "请开始生成。切记用 <next> 分隔每一页的演讲词。"

        user_message = BaseMessage.make_user_message(
            role_name="User",
            content=user_prompt
        )

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
        load_dotenv(env_path)
        api_key = os.getenv('DEFAULT_MODEL_API_KEY')
        model_instance = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            url='https://api.deepseek.com',
            api_key=api_key,
            model_config_dict={"temperature": 0.7}
        )

        # 4. Agent 执行
        agent = ChatAgent(
            system_message=self.system_message,
            model=model_instance,
            message_window_size=10
        )

        try:
            response = agent.step(user_message)
            script_content = response.msg.content
        except Exception as e:
            print(f"[Presenter] 模型调用失败: {e}")
            return

        # 5. 后处理与保存
        script_content = script_content.replace("```txt", "").replace("```", "").strip()
        
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
            
        print(f"[Presenter] 成功！演讲稿已保存至: {output_file_path}")
        print(f"[Presenter] <next> 标签数量: {script_content.count('<next>')}")
