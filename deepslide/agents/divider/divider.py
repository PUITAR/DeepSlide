# divider.py
"""
主 Divider - 协调 RoughDivider 和 RefineAgent
确保有结果生成：CAMEL 失败时回退到 Rough 结果
"""

import json
import os
import logging
import datetime
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from contextlib import contextmanager

from chapter_node import ChapterNode
from rough_divider import RoughDivider
from refine_agent import RefineAgent

logger = logging.getLogger(__name__)

def _load_environment():
    """智能加载环境变量"""
    # 1. 尝试从标准位置加载
    standard_paths = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'env', '.env'),
        '/home/ym/DeepSlide/deepslide/config/env/.env'  # 回退路径
    ]
    
    for env_path in standard_paths:
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path)
            logger.info(f"✅ 环境变量从 {env_path} 加载成功")
            return
    
    # 2. 未找到时警告但不中断
    logger.warning("⚠️  未找到 .env 文件，将使用系统环境变量")

# 初始化环境变量
_load_environment()

class Divider:
    """主 Divider - 协调分割和细化流程"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化 Divider"""
        self.config = config or {}
        self.rough_divider = RoughDivider()
        self.refine_agent = None  # 懒加载，避免初始化失败
        self.camel_initialized = False
        self.camel_init_error = None
        logger.info("✅ Divider 基础组件初始化完成")
    
    def divide(
        self,
        tex_content: str,
        planner_instructions: Dict[str, Any]
    ) -> Tuple[List[ChapterNode], Dict[str, Any]]:
        """
        执行完整的分割流程
        
        Args:
            tex_content: LaTeX 源码
            planner_instructions: Planner 指令
            
        Returns:
            (节点列表, 反馈信息) - 保证有结果返回
        """
        # 1. 输入验证
        if not tex_content or len(tex_content.strip()) < 10:
            logger.error("❌ 输入LaTeX内容过短或为空")
            return [], {
                "status": "error",
                "error_type": "invalid_input",
                "message": "输入内容过短或为空",
                "suggestions": ["检查输入文件", "确保LaTeX内容有效"]
            }
        
        logger.info(f"🚀 开始分割流程 (内容长度: {len(tex_content)} 字符)")
        logger.info(f"⏳ 预计处理时间: {max(2, len(tex_content) // 5000):.1f} 秒")
        
        # 2. 执行粗略划分（必须成功）
        try:
            rough_nodes, rough_feedback = self.rough_divider.divide(
                tex_content, planner_instructions
            )
            logger.info(f"✅ 粗分完成: {len(rough_nodes)} 个节点")
        except Exception as e:
            logger.exception(f"❌ 粗分失败: {str(e)}")  # 使用exception记录完整堆栈
            return [], {
                "status": "error",
                "error_type": "rough_division_failed",
                "message": str(e),
                "suggestions": ["检查 LaTeX 格式", "降低 max_section_depth"]
            }
        
        # 3. 检查是否需要 CAMEL 细化
        use_camel = planner_instructions.get("use_camel_refinement", False)
        logger.info(f"🔍 检测到 {'启用' if use_camel else '禁用'} CAMEL 细化")
        
        if use_camel:
            refined_nodes, refine_feedback = self._try_camel_refinement(
                rough_nodes, planner_instructions
            )
        else:
            # 不使用 CAMEL，直接返回粗分结果
            refined_nodes = rough_nodes
            refine_feedback = {"status": "skipped", "method": "camel_refinement_skipped"}
            logger.info("⏭️  跳过 CAMEL 细化，使用粗分结果")
        
        # 4. 合并反馈
        final_feedback = self._merge_feedbacks(rough_feedback, refine_feedback)
        
        logger.info(f"✅ 分割流程完成: {len(refined_nodes)} 个最终节点")
        return refined_nodes, final_feedback
    
    def _try_camel_refinement(
        self,
        rough_nodes: List[ChapterNode],
        planner_instructions: Dict[str, Any]
    ) -> Tuple[List[ChapterNode], Dict[str, Any]]:
        """
        尝试 CAMEL 细化，失败时回退到粗分结果
        """
        logger.info(f"🤖 尝试 CAMEL 细化 {len(rough_nodes)} 个节点")
        
        # 1. 初始化 CAMEL（如果尚未初始化）
        if self.refine_agent is None:
            try:
                camel_config = self._get_camel_config()
                self.refine_agent = RefineAgent(camel_config)
                self.camel_initialized = True
                logger.info("✅ CAMEL 模型初始化成功")
            except Exception as e:
                logger.warning(f"⚠️  CAMEL 初始化失败: {str(e)}，回退到粗分结果")
                self.camel_init_error = str(e)
                return rough_nodes, {
                    "status": "error",
                    "error_type": "camel_initialization_failed",
                    "message": str(e),
                    "method": "fallback_to_rough",
                    "fallback_reason": "camel_initialization_failed"
                }
        
        # 2. 尝试 CAMEL 细化
        try:
            refined_nodes, refine_feedback = self.refine_agent.refine(
                rough_nodes, planner_instructions
            )
            logger.info(f"✅ CAMEL 细化成功: {len(refined_nodes)} 个节点")
            return refined_nodes, refine_feedback
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"🌐 网络连接错误: {str(e)}，回退到粗分结果")
            return rough_nodes, {
                "status": "error",
                "error_type": "camel_network_error",
                "message": str(e),
                "method": "fallback_to_rough",
                "fallback_reason": "network_error"
            }
        except ValueError as e:
            logger.error(f"❌ 数据验证失败: {str(e)}，回退到粗分结果")
            return rough_nodes, {
                "status": "error",
                "error_type": "camel_validation_error",
                "message": str(e),
                "method": "fallback_to_rough",
                "fallback_reason": "validation_error"
            }
        except Exception as e:
            logger.exception(f"💥 CAMEL 细化未知错误: {str(e)}")  # 记录完整堆栈
            return rough_nodes, {
                "status": "error",
                "error_type": "camel_refinement_failed",
                "message": str(e),
                "method": "fallback_to_rough",
                "fallback_reason": "unknown_error"
            }
    
    def _get_camel_config(self) -> Dict[str, Any]:
        """获取 CAMEL 配置"""
        return {
            "model_type": os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat'),
            "api_key": os.getenv('DEEPSEEK_API_KEY'),
            "base_url": os.getenv('OPENAI_BASE_URL')
        }
    
    def _merge_feedbacks(
        self,
        rough_feedback: Dict[str, Any],
        refine_feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """合并粗分和细化反馈"""
        merged = {
            "status": "success",
            "rough_division": rough_feedback,
            "refinement": refine_feedback,
            "final_node_count": rough_feedback.get("final_node_count", 0),
            "process_method": "rough_then_camel" if refine_feedback.get("status") != "error" else "rough_only",
            "has_camel_results": refine_feedback.get("status") != "error"
        }
        
        # 检查是否回退
        if refine_feedback.get("method") == "fallback_to_rough":
            merged["status"] = "warning"
            merged["warning"] = refine_feedback.get("fallback_reason", "camel_fallback")
        
        return merged

@contextmanager
def divider_context(config: Optional[Dict[str, Any]] = None):
    """Divider上下文管理器，确保资源清理"""
    divider = None
    try:
        divider = Divider(config)
        yield divider
    finally:
        if divider:
            logger.info("🧹 Divider资源已清理")
            # 未来可在此添加更多清理逻辑

def _load_demo_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载演示配置"""
    default_config = {
        "input_path": os.getenv(
            "DEMO_LATEX_PATH", 
            "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"
        ),
        "output_dir": "./divider_results",
        "planner_instructions": {
            "max_section_depth": 3,
            "max_sections": 10,
            "merge_short_threshold": 150,
            "focus_keywords": ["introduction", "method", "experiment", "result", "conclusion"],
            "skip_keywords": ["reference", "bibliography", "appendix", "acknowledgement"],
            "use_camel_refinement": True,
            "refine_threshold": 400,
            "min_segment_length": 80,
            "max_segments_per_node": 3,
            "debug_mode": True
        }
    }
    
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                custom_config = json.load(f)
            # 合并配置
            default_config.update(custom_config)
            logger.info(f"✅ 从 {config_path} 加载自定义演示配置")
        except Exception as e:
            logger.warning(f"⚠️  加载自定义配置失败，使用默认配置: {str(e)}")
    
    return default_config

def run_demo(config_path: Optional[str] = None):
    """可配置的演示函数"""
    # 1. 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    demo_logger = logging.getLogger("divider_demo")
    
    demo_logger.info("="*60)
    demo_logger.info("Divider 完整流程演示")
    demo_logger.info("="*60)
    
    # 2. 加载配置
    demo_config = _load_demo_config(config_path)
    demo_logger.info(f"📋 使用演示配置:\n{json.dumps(demo_config, indent=2, ensure_ascii=False)}")
    
    # 3. 验证输入文件
    input_path = demo_config["input_path"]
    if not os.path.exists(input_path):
        demo_logger.error(f"❌ LaTeX 文件不存在: {input_path}")
        # 尝试相对路径
        relative_path = os.path.join(os.path.dirname(__file__), "test", os.path.basename(input_path))
        if os.path.exists(relative_path):
            demo_logger.info(f"🔄 尝试使用相对路径: {relative_path}")
            input_path = relative_path
        else:
            demo_logger.error("❌ 未找到替代路径，演示终止")
            return 1
    
    # 4. 加载 LaTeX 内容
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            latex_content = f.read()
        demo_logger.info(f"✅ 加载 LaTeX 文件: {len(latex_content)} 字符")
    except Exception as e:
        demo_logger.error(f"❌ 读取文件失败: {str(e)}")
        return 1
    
    # 5. 执行分割
    try:
        with divider_context() as divider:
            demo_logger.info("\n⚙️  执行分割流程...")
            nodes, feedback = divider.divide(latex_content, demo_config["planner_instructions"])
    except Exception as e:
        demo_logger.exception(f"❌ 分割流程异常终止: {str(e)}")
        return 1
    
    # 6. 保存结果
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = demo_config["output_dir"]
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, f"divider_result_{timestamp}.json")
    try:
        result_data = {
            "metadata": {
                "process_timestamp": timestamp,
                "input_path": input_path,
                "input_length": len(latex_content),
                "total_nodes": len(nodes),
                "process_method": feedback.get("process_method", "unknown")
            },
            "nodes": [node.to_dict(include_content=False) for node in nodes],
            "feedback": feedback
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        demo_logger.info(f"✅ 结果已保存至: {os.path.abspath(output_path)}")
    except Exception as e:
        demo_logger.error(f"❌ 保存结果失败: {str(e)}")
    
    # 7. 打印摘要
    demo_logger.info("\n" + "="*60)
    demo_logger.info("📊 分割结果摘要")
    demo_logger.info("="*60)
    demo_logger.info(f"输入文件: {os.path.basename(input_path)}")
    demo_logger.info(f"输入长度: {len(latex_content)} 字符")
    demo_logger.info(f"最终节点数: {len(nodes)}")
    demo_logger.info(f"处理方法: {feedback.get('process_method', 'unknown')}")
    demo_logger.info(f"使用 CAMEL 结果: {feedback.get('has_camel_results', False)}")
    
    # 显示前几个节点
    demo_logger.info(f"\n📋 前5个节点:")
    for i, node in enumerate(nodes[:5]):
        title_preview = node.title[:50] + "..." if len(node.title) > 50 else node.title
        demo_logger.info(f"  {i+1}. [{node.level}] {title_preview} (重要性: {node.importance:.2f})")
    
    if len(nodes) > 5:
        demo_logger.info(f"  ... 还有 {len(nodes)-5} 个节点")
    
    # 检查是否使用了回退
    if feedback.get("status") == "warning":
        demo_logger.warning(f"⚠️  使用了回退策略: {feedback.get('warning')}")
    
    demo_logger.info(f"\n🎉 分割流程演示完成!")
    demo_logger.info(f"📄 详细结果: {os.path.abspath(output_path)}")
    
    return 0

def main():
    """主函数 - 演示完整流程"""
    # 检查运行目录
    current_dir = os.getcwd()
    if "divider" not in current_dir.lower():
        logger.warning("⚠️  当前目录不包含 'divider'，可能需要调整路径")
        logger.info(f"  当前目录: {current_dir}")
    
    # 运行演示
    exit_code = run_demo()
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)