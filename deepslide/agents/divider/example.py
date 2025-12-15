# example_usage.py
from divider import Divider
import json

def main():
    # 1. 初始化
    divider = Divider()
    document = "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"
    # 2. 加载 LaTeX
    with open(document, "r", encoding="utf-8") as f:
        latex_content = f.read()
    
    # 3. 设置指令
    instructions = {
        "max_section_depth": 3,
        "max_sections": 10,
        "use_camel_refinement": False,  # 启用 CAMEL
        "refine_threshold": 400
    }
    
    # 4. 执行分割
    nodes, feedback = divider.divide(latex_content, instructions)
    
    # 5. 检查结果
    if feedback["status"] == "warning":
        print(f"⚠️  使用了回退策略: {feedback.get('fallback_reason')}")
    
    print(f"✅ 生成 {len(nodes)} 个节点")
    print(f"📊 处理方法: {feedback['process_method']}")
    
    # 6. 保存结果
    result = {
        "nodes": [node.to_dict(include_content=False) for node in nodes],
        "feedback": feedback
    }
    
    with open("dicide_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()