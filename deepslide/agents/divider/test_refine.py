# end_to_end_test.py
"""
端到端测试：LaTeX → RoughDivider → RefineAgent
直接从 LaTeX 文件开始，验证完整的分割和细化流程
"""

import json
import os
import logging
import datetime
import time
from typing import List, Dict, Any
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("end_to_end_test")

# 配置路径
LATEX_FILE_PATH = "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"
RESULT_DIR = "./end_to_end_results"
os.makedirs(RESULT_DIR, exist_ok=True)

# 加载环境变量
ENV_PATH = '/home/ym/DeepSlide/deepslide/config/env/.env'
load_dotenv(dotenv_path=ENV_PATH)

def test_end_to_end():
    """端到端测试流程"""
    logger.info("="*60)
    logger.info("END-TO-END TEST: LaTeX → RoughDivider → RefineAgent")
    logger.info("="*60)
    
    # 1. 加载 LaTeX 内容
    if not os.path.exists(LATEX_FILE_PATH):
        logger.error(f"❌ LaTeX 文件不存在: {LATEX_FILE_PATH}")
        return 1
    
    try:
        with open(LATEX_FILE_PATH, 'r', encoding='utf-8') as f:
            latex_content = f.read()
        logger.info(f"✅ 成功加载 LaTeX 文件: {len(latex_content)} 字符")
    except Exception as e:
        logger.error(f"❌ 读取 LaTeX 文件失败: {str(e)}")
        return 1
    
    # 2. 导入模块（在函数内导入，避免路径问题）
    try:
        from rough_divider import RoughDivider
        from refine_agent import RefineAgent
        from chapter_node import ChapterNode
    except ImportError as e:
        logger.error(f"❌ 模块导入失败: {str(e)}")
        logger.info("请确保在正确目录运行: /home/ym/DeepSlide/deepslide/agents/divider/")
        return 1
    
    # 3. 创建 Planner 指令
    planner_instructions = {
        # 粗分控制
        "max_section_depth": 3,
        "max_sections": 10,
        "merge_short_threshold": 150,
        "focus_keywords": ["introduction", "method", "experiment", "result", "conclusion"],
        "skip_keywords": ["reference", "bibliography", "appendix", "acknowledgement"],
        
        # 细化控制
        "use_camel_segmentation": True,
        "refine_threshold": 500,
        "min_segment_length": 100,
        "max_segments_per_node": 4,
        
        # 关系构建
        "build_semantic_relations": True,
        "semantic_relation_threshold": 0.6,
        "max_camel_relation_calls": 5,
        "allowed_relationship_types": ["DEPENDENT", "SIMILAR", "CONTRAST"],
        "max_camel_calls_per_node": 2,
        
        "debug_mode": True
    }
    
    camel_config = {
        "model_type": os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat'),
        "api_key": os.getenv('DEEPSEEK_API_KEY'),
        "base_url": os.getenv('OPENAI_BASE_URL')
    }
    
    if not camel_config.get('api_key'):
        logger.error("❌ 缺少 CAMEL API 密钥")
        return 1
    
    logger.info(f"\n📋 Planner 指令:\n{json.dumps(planner_instructions, indent=2, ensure_ascii=False)}")
    
    # 4. 粗略划分
    logger.info("\n⚙️  执行粗略划分...")
    start_time = time.time()
    
    try:
        rough_divider = RoughDivider()
        rough_nodes, rough_feedback = rough_divider.divide(latex_content, planner_instructions)
        rough_time = time.time() - start_time
        logger.info(f"✅ 粗分完成: {len(rough_nodes)} 个节点, 耗时: {rough_time:.2f} 秒")
    except Exception as e:
        logger.error(f"❌ 粗分失败: {str(e)}", exc_info=True)
        return 1
    
    # 5. CAMEL 细化
    logger.info("\n🤖 执行 CAMEL 细化...")
    start_time = time.time()
    
    try:
        refine_agent = RefineAgent(camel_config)
        refined_nodes, refine_feedback = refine_agent.refine(rough_nodes, planner_instructions)
        refine_time = time.time() - start_time
        logger.info(f"✅ 细化完成: {len(refined_nodes)} 个节点, 耗时: {refine_time:.2f} 秒")
    except Exception as e:
        logger.error(f"❌ 细化失败: {str(e)}", exc_info=True)
        return 1
    
    # 6. 验证结果
    logger.info("\n🔍 验证结果...")
    validation = validate_results(rough_nodes, refined_nodes)
    
    # 7. 保存结果
    logger.info("\n💾 保存结果...")
    save_results(rough_nodes, refined_nodes, rough_feedback, refine_feedback, validation)
    
    # 8. 打印摘要
    logger.info("\n" + "="*60)
    logger.info("📊 端到端测试摘要")
    logger.info("="*60)
    logger.info(f"LaTeX 文件大小: {len(latex_content)} 字符")
    logger.info(f"粗分节点数: {len(rough_nodes)}")
    logger.info(f"细化后节点数: {len(refined_nodes)} (+{len(refined_nodes)-len(rough_nodes)})")
    logger.info(f"粗分耗时: {rough_time:.2f} 秒")
    logger.info(f"细化耗时: {refine_time:.2f} 秒")
    logger.info(f"总耗时: {rough_time + refine_time:.2f} 秒")
    logger.info(f"内容完整性: {'✅ 通过' if validation['content_integrity'] else '❌ 失败'}")
    logger.info(f"建立关系数: {refine_feedback.get('relationships_built', 0)}")
    logger.info(f"CAMEL 调用数: {refine_feedback.get('camel_relation_calls', 0)}")
    
    if refine_feedback.get('errors', 0) > 0:
        logger.warning(f"⚠️  {refine_feedback['errors']} 次细化错误")
    else:
        logger.info("✅ 无细化错误")
    
    logger.info(f"\n🎉 端到端测试成功完成!")
    logger.info(f"📄 详细结果已保存至: {os.path.abspath(RESULT_DIR)}")
    
    return 0

def validate_results(
    rough_nodes: List['ChapterNode'],
    refined_nodes: List['ChapterNode']
) -> Dict[str, Any]:
    """验证端到端结果"""
    validation = {
        "content_integrity": True,
        "content_diff": 0,
        "nodes_with_relations": 0,
        "nodes_with_tags": 0,
        "nodes_with_importance": 0
    }
    
    # 1. 内容完整性检查
    rough_content = ''.join([node.content for node in rough_nodes])
    refined_content = ''.join([node.content for node in refined_nodes])
    
    content_diff = abs(len(rough_content) - len(refined_content)) / max(1, len(rough_content))
    validation["content_diff"] = content_diff
    validation["content_integrity"] = content_diff < 0.05
    
    if not validation["content_integrity"]:
        logger.warning(f"⚠️  内容完整性警告: 差异率 {content_diff:.1%}")
    
    # 2. 元数据检查
    for node in refined_nodes:
        # 检查关系
        relations = node.get_all_relationships()
        if relations:
            validation["nodes_with_relations"] += 1
        
        # 检查标签
        if node.tags:
            validation["nodes_with_tags"] += 1
        
        # 检查重要性
        if hasattr(node, 'importance') and 0.0 <= node.importance <= 1.0:
            validation["nodes_with_importance"] += 1
    
    logger.info(f"✅ 验证完成: 内容完整性={validation['content_integrity']}, "
                f"关系节点={validation['nodes_with_relations']}/{len(refined_nodes)}, "
                f"标签节点={validation['nodes_with_tags']}/{len(refined_nodes)}")
    
    return validation

def save_results(
    rough_nodes: List['ChapterNode'],
    refined_nodes: List['ChapterNode'],
    rough_feedback: Dict[str, Any],
    refine_feedback: Dict[str, Any],
    validation: Dict[str, Any]
):
    """保存端到端结果"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. 保存完整结果
        result_data = {
            "metadata": {
                "test_timestamp": timestamp,
                "source_file": os.path.basename(LATEX_FILE_PATH),
                "latex_file_size": len(open(LATEX_FILE_PATH, 'r', encoding='utf-8').read()),
                "validation": validation
            },
            "rough_division": {
                "nodes": [node.to_dict(include_content=False) for node in rough_nodes],
                "feedback": rough_feedback
            },
            "refined_results": {
                "nodes": [node.to_dict(include_content=False) for node in refined_nodes],
                "feedback": refine_feedback
            }
        }
        
        json_path = os.path.join(RESULT_DIR, f"end_to_end_result_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ 完整结果已保存至: {os.path.abspath(json_path)}")
        
        # 2. 生成摘要报告
        report_path = os.path.join(RESULT_DIR, f"end_to_end_report_{timestamp}.txt")
        generate_summary_report(rough_nodes, refined_nodes, rough_feedback, refine_feedback, report_path)
        
        return json_path, report_path
        
    except Exception as e:
        logger.error(f"❌ 保存结果失败: {str(e)}")

def generate_summary_report(
    rough_nodes: List['ChapterNode'],
    refined_nodes: List['ChapterNode'],
    rough_feedback: Dict[str, Any],
    refine_feedback: Dict[str, Any],
    report_path: str
):
    """生成摘要报告"""
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("END-TO-END TEST REPORT\n")
            f.write("="*60 + "\n\n")
            
            f.write("📋 测试元数据\n")
            f.write("-"*40 + "\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"源 LaTeX 文件: {os.path.basename(LATEX_FILE_PATH)}\n")
            f.write(f"LaTeX 大小: {len(open(LATEX_FILE_PATH, 'r', encoding='utf-8').read())} 字符\n\n")
            
            f.write("📊 粗分阶段结果\n")
            f.write("-"*40 + "\n")
            f.write(f"粗分节点数: {len(rough_nodes)}\n")
            f.write(f"方法: {rough_feedback.get('method', 'unknown')}\n")
            f.write(f"合并操作: {rough_feedback.get('merge_operations', 0)}\n")
            f.write(f"内容覆盖率: {rough_feedback.get('content_coverage_ratio', 0):.1%}\n\n")
            
            f.write("🤖 细化阶段结果\n")
            f.write("-"*40 + "\n")
            f.write(f"细化后节点数: {len(refined_nodes)}\n")
            f.write(f"创建片段数: {refine_feedback.get('segments_created', 0)}\n")
            f.write(f"建立关系数: {refine_feedback.get('relationships_built', 0)}\n")
            f.write(f"CAMEL 关系调用: {refine_feedback.get('camel_relation_calls', 0)}\n")
            f.write(f"错误数: {refine_feedback.get('errors', 0)}\n\n")
            
            f.write("🔍 节点统计详情\n")
            f.write("-"*40 + "\n")
            f.write(f"有关系的节点: {sum(1 for n in refined_nodes if n.get_all_relationships())}/{len(refined_nodes)}\n")
            f.write(f"有标签的节点: {sum(1 for n in refined_nodes if n.tags)}/{len(refined_nodes)}\n")
            f.write(f"有重要性评分的节点: {sum(1 for n in refined_nodes if 0 <= n.importance <= 1)}/{len(refined_nodes)}\n\n")
            
            f.write("📋 前5个细化节点详情\n")
            f.write("-"*40 + "\n")
            for i, node in enumerate(refined_nodes[:5], 1):
                f.write(f"\n节点 #{i}: {node.title}\n")
                f.write(f"  • 级别: {node.level}, 类型: {node.node_type.value}\n")
                f.write(f"  • 长度: {len(node.content)} 字符\n")
                f.write(f"  • 重要性: {node.importance:.2f}\n")
                f.write(f"  • 标签: {', '.join(sorted(node.tags)) if node.tags else '无'}\n")
                
                relations = node.get_all_relationships()
                if relations:
                    f.write(f"  • 关系数: {sum(len(rels) for rels in relations.values())}\n")
                else:
                    f.write("  • 无关系\n")
            
            if len(refined_nodes) > 5:
                f.write(f"\n... 还有 {len(refined_nodes)-5} 个节点未显示\n")
        
        logger.info(f"✅ 摘要报告已保存至: {os.path.abspath(report_path)}")
        
    except Exception as e:
        logger.error(f"❌ 生成报告失败: {str(e)}")

if __name__ == "__main__":
    # 确保在正确目录运行
    current_dir = os.getcwd()
    if "divider" not in current_dir:
        logger.error("❌ 请在 /home/ym/DeepSlide/deepslide/agents/divider/ 目录下运行此脚本")
        logger.info(f"当前目录: {current_dir}")
        exit(1)
    
    exit_code = test_end_to_end()
    exit(exit_code)