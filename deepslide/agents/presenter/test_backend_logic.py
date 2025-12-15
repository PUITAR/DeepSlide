import sys
import os
import json
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(project_root)

from deepslide.agents.presenter.matrix_generator import MatrixGenerator

def test_matrix_generation():
    print("=== Testing Matrix Generator ===")
    
    # 加载环境变量
    env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
    print(f"Loading env from: {env_path}")
    load_dotenv(env_path)
    
    # 检查 API Key
    if not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("Warning: No API Key found in env. Test might fail or fallback to mock if implemented.")
    
    # 模拟逻辑节点
    nodes = [
        "1. 深度学习简介：介绍深度学习的基本概念和历史。",
        "2. 神经网络基础：讲解神经元、层、激活函数等基础组件。",
        "3. 反向传播算法：阐述神经网络如何通过梯度下降进行训练。",
        "4. 卷积神经网络：介绍用于图像处理的 CNN 架构。",
        "5. 总结与展望：总结深度学习的应用并展望未来趋势。"
    ]
    
    print(f"Input Nodes ({len(nodes)}):")
    for node in nodes:
        print(f"  - {node}")
    
    print("\nGenerating Matrix (this calls the LLM)...")
    generator = MatrixGenerator()
    matrix = generator.generate_matrix(nodes)
    
    print("\nGenerated Matrix:")
    print(json.dumps(matrix, indent=2, ensure_ascii=False))
    
    # 简单验证
    if len(matrix) == len(nodes) and len(matrix[0]) == len(nodes):
        print("\n✅ Matrix dimension test passed.")
    else:
        print("\n❌ Matrix dimension mismatch.")

    # 打印非空关系
    print("\nDetected Relationships:")
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j]:
                print(f"  [{i+1}] -> [{j+1}]: {matrix[i][j]}")

if __name__ == "__main__":
    test_matrix_generation()
