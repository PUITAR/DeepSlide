from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.types import ModelPlatformType
from camel.models import ModelFactory
import json

class MatrixGenerator:
    def __init__(self):
        sys_msg_content = (
            "你是一个逻辑分析专家。你的任务是分析给定的一系列逻辑节点（演讲段落），"
            "并找出它们两两之间的逻辑联系。\n"
            "输入将是一个逻辑节点的列表。\n"
            "输出必须是一个二维矩阵（JSON格式），其中 matrix[i][j] 表示节点 i 和节点 j 之间的逻辑联系。\n"
            "如果节点 i 和节点 j 之间没有明显的直接逻辑联系，请填入 null 或 空字符串。\n"
            "联系的类型可以是：'因果', '递进', '转折', '举例', '总结', '对比', '补充' 等，或者具体的描述。\n"
            "请确保输出是合法的 JSON 格式，仅包含矩阵数据，不要包含 Markdown 标记。"
        )
        
        self.system_message = BaseMessage.make_assistant_message(
            role_name="LogicAnalyst",
            content=sys_msg_content
        )

    def generate_matrix(self, logic_nodes: list[str]) -> list[list[str]]:
        """
        根据逻辑节点列表生成联系矩阵。
        :param logic_nodes: 逻辑节点内容列表
        :return: 二维列表 (N x N)
        """
        if not logic_nodes:
            return []

        user_prompt = "逻辑节点列表如下：\n"
        for idx, node in enumerate(logic_nodes):
            user_prompt += f"{idx}. {node}\n"
        
        user_prompt += "\n请生成对应的 N x N 逻辑联系矩阵（JSON格式列表的列表）。"

        user_message = BaseMessage.make_user_message(
            role_name="User",
            content=user_prompt
        )

        # 使用 OpenAI 或兼容模型 (这里复用 Presenter 的配置)
        import os
        model_instance = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            url='https://api.deepseek.com',
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            model_config_dict={"temperature": 0.2}
        )

        agent = ChatAgent(
            system_message=self.system_message,
            model=model_instance,
            message_window_size=10
        )

        try:
            response = agent.step(user_message)
            content = response.msg.content
            
            # 尝试提取 JSON 内容
            import re
            json_match = re.search(r'\[\s*\[.*\]\s*\]', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            else:
                # 尝试清理 Markdown
                content = content.replace("```json", "").replace("```", "").strip()
            
            matrix = json.loads(content)
            
            # 验证矩阵维度
            n = len(logic_nodes)
            if len(matrix) != n or any(len(row) != n for row in matrix):
                print(f"[MatrixGenerator] Warning: Matrix dimension mismatch. Expected {n}x{n}")
                # 可以在这里做一些补全或截断处理，或者直接报错
            
            return matrix
        except Exception as e:
            print(f"[MatrixGenerator] Error: {e}")
            print(f"[MatrixGenerator] Raw content: {content if 'content' in locals() else 'None'}")
            # Fallback: return empty matrix
            n = len(logic_nodes)
            return [["" for _ in range(n)] for _ in range(n)]
