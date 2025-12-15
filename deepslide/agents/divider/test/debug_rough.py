# debug_test.py (调试版本)
"""
调试测试 - 找出节点数量统计错误的根源
"""

import json
import os
import logging
import datetime
from rough_divider import RoughDivider
from chapter_node import ChapterNode

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("debug_test")

# 配置路径
TEST_FILE_PATH = "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"

def main():
    """调试主函数"""
    logger.info("="*60)
    logger.info("DEBUG TEST - 查找节点数量错误根源")
    logger.info("="*60)
    
    # 1. 加载 LaTeX 内容
    try:
        with open(TEST_FILE_PATH, 'r', encoding='utf-8') as f:
            tex_content = f.read()
        logger.info(f"✅ 成功加载 LaTeX 文件: {len(tex_content)} 字符")
    except Exception as e:
        logger.error(f"❌ 文件读取失败: {str(e)}")
        return 1
    
    # 2. 初始化 RoughDivider
    divider = RoughDivider()
    
    # 3. 设置 Planner 指令
    planner_instructions = {
        "max_section_depth": 3,
        "max_sections": 10,
        "merge_short_threshold": 150,
        "focus_keywords": ["introduction", "method", "experiment", "result", "conclusion"],
        "skip_keywords": ["reference", "bibliography", "appendix", "acknowledgement"],
        "debug_mode": True
    }
    
    # 4. 执行粗略划分
    logger.info("\n⚙️  执行粗略划分...")
    try:
        all_nodes, feedback = divider.divide(tex_content, planner_instructions)
        logger.info(f"RoughDivider 返回: {len(all_nodes)} 个节点")
        
        # 详细检查节点
        root_nodes = [n for n in all_nodes if not n.parent_id]
        child_nodes = [n for n in all_nodes if n.parent_id]
        
        logger.info(f"根节点数量: {len(root_nodes)}")
        logger.info(f"子节点数量: {len(child_nodes)}")
        logger.info(f"总节点数量: {len(all_nodes)}")
        
        # 检查是否有重复的 node_id
        node_ids = [node.node_id for node in all_nodes]
        unique_ids = set(node_ids)
        if len(unique_ids) != len(node_ids):
            duplicates = [x for x in node_ids if node_ids.count(x) > 1]
            logger.error(f"❌ 发现重复的 node_id: {duplicates[:5]}...")  # 只显示前5个
        else:
            logger.info("✅ 所有 node_id 都是唯一的")
        
        # 打印前几个节点信息用于调试
        logger.info("\n📋 前3个节点信息:")
        for i, node in enumerate(all_nodes[:3]):
            logger.info(f"  {i+1}. ID: {node.node_id}, Title: {node.title}, Level: {node.level}, Parent: {node.parent_id}, Children: {len(node.children_ids)}")
        
        logger.info(f"\n✅ 调试完成: 生成 {len(root_nodes)} 个根节点, 共 {len(all_nodes)} 个节点")
        
    except Exception as e:
        logger.error(f"❌ 划分失败: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)