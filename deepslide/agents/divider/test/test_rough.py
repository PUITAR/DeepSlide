# test_rough_divider_correct.py
"""
正确的测试代码 - 基于调试结果
只使用 RoughDivider 返回的 all_nodes，不进行额外的节点收集
"""

import json
import os
import logging
import datetime
from rough_divider import RoughDivider
from chapter_node import ChapterNode
from typing import List, Dict, Any
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_rough_divider_correct")

# 配置路径
TEST_FILE_PATH = "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"
RESULT_DIR = "./result"
os.makedirs(RESULT_DIR, exist_ok=True)

def save_chapter_nodes(nodes: List[ChapterNode], feedback: Dict[str, Any], output_path: str):
    """保存 ChapterNode 结构到 JSON 文件"""
    try:
        nodes_data = []
        for node in nodes:
            node_dict = node.to_dict(include_content=True)
            node_dict["content_preview"] = node.content[:200] + "..." if len(node.content) > 200 else node.content
            node_dict["children_count"] = len(node.children_ids)
            nodes_data.append(node_dict)
        
        result_data = {
            "metadata": {
                "test_file": os.path.basename(TEST_FILE_PATH),
                "timestamp": datetime.datetime.now().isoformat(),
                "total_nodes": len(nodes),
                "divider_version": "2.1-correct"
            },
            "nodes": nodes_data,
            "feedback": feedback
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ ChapterNode 结构已保存至: {os.path.abspath(output_path)}")
        return True
    except Exception as e:
        logger.error(f"❌ 保存结果失败: {str(e)}")
        return False

def validate_chapter_node_structure(nodes: List[ChapterNode]):
    """验证 ChapterNode 结构完整性"""
    if not nodes:
        raise ValueError("没有生成任何 ChapterNode 节点")
    
    node_map = {node.node_id: node for node in nodes}
    
    # 验证1: 所有节点必须有唯一ID
    node_ids = [node.node_id for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        duplicates = [x for x in node_ids if node_ids.count(x) > 1]
        raise ValueError(f"存在重复的 node_id: {duplicates[:3]}...")
    
    # 验证2: 父子关系一致性
    for node in nodes:
        if node.parent_id:
            if node.parent_id not in node_map:
                raise ValueError(f"父节点不存在: {node.parent_id}")
            parent = node_map[node.parent_id]
            if node.node_id not in parent.children_ids:
                raise ValueError(f"父子关系不一致: {node.title}")
        
        for child_id in node.children_ids:
            if child_id not in node_map:
                raise ValueError(f"子节点不存在: {child_id}")
            child = node_map[child_id]
            if child.parent_id != node.node_id:
                raise ValueError(f"父子关系反向不一致: {child.title}")
    
    # 验证3: 重要性范围
    for node in nodes:
        if not (0.0 <= node.importance <= 1.0):
            raise ValueError(f"节点重要性超出范围: {node.title} ({node.importance})")
    
    # 验证4: 位置信息
    for node in nodes:
        if not hasattr(node, 'position') or not isinstance(node.position.start_char, int):
            raise ValueError(f"节点缺少有效 position: {node.title}")
    
    logger.info("✅ ChapterNode 结构验证通过")

def main():
    """主测试函数"""
    logger.info("="*60)
    logger.info("ROUGH DIVIDER CORRECT TEST")
    logger.info("="*60)
    
    if not os.path.exists(TEST_FILE_PATH):
        logger.error(f"❌ 测试文件不存在: {TEST_FILE_PATH}")
        return 1
    
    try:
        with open(TEST_FILE_PATH, 'r', encoding='utf-8') as f:
            tex_content = f.read()
        logger.info(f"✅ 成功加载 LaTeX 文件: {len(tex_content)} 字符")
    except Exception as e:
        logger.error(f"❌ 文件读取失败: {str(e)}")
        return 1
    
    # 设置 Planner 指令
    planner_instructions = {
        "max_section_depth": 3,
        "max_sections": 10,
        "merge_short_threshold": 150,
        "focus_keywords": ["introduction", "method", "experiment", "result", "conclusion"],
        "skip_keywords": ["reference", "bibliography", "appendix", "acknowledgement"],
        "debug_mode": True
    }
    
    # 执行划分
    logger.info("\n⚙️  执行粗略划分...")
    try:
        all_nodes, feedback = RoughDivider().divide(tex_content, planner_instructions)
        
        # 直接计算根节点（不进行额外操作）
        root_nodes = [n for n in all_nodes if not n.parent_id]
        
        logger.info(f"✅ 粗略划分成功! 生成 {len(root_nodes)} 个根节点, 共 {len(all_nodes)} 个节点")
        
    except Exception as e:
        logger.error(f"❌ 划分失败: {str(e)}", exc_info=True)
        return 1
    
    # 验证结构
    try:
        validate_chapter_node_structure(all_nodes)
    except Exception as e:
        logger.error(f"❌ 结构验证失败: {str(e)}")
        return 1
    
    # 保存结果
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(RESULT_DIR, f"rough_division_{timestamp}.json")
    
    if not save_chapter_nodes(all_nodes, feedback, json_path):
        return 1
    
    # 打印摘要
    logger.info("\n" + "="*60)
    logger.info("📊 测试摘要")
    logger.info("="*60)
    logger.info(f"总节点数: {len(all_nodes)}")
    logger.info(f"根节点数: {len(root_nodes)}")
    logger.info(f"内容覆盖率: {feedback.get('content_coverage_ratio', 0):.1%}")
    logger.info(f"合并操作: {feedback.get('merge_operations', 0)} 次")
    
    if len(all_nodes) > max(feedback.get('section_hierarchy', {}).values(), default=0) * 2:
        logger.warning("⚠️  某些章节可能需要 CAMEL 细化（内容过长）")
    else:
        logger.info("✅ 所有章节长度均衡，无需额外细化")
    
    logger.info(f"\n🎉 测试成功完成! 结果保存在: {os.path.abspath(RESULT_DIR)}")
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)