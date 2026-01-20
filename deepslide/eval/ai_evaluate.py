#!/usr/bin/env python3
"""
简单的PPT和演讲稿AI评估脚本
"""

import os
import sys
import json
from datetime import datetime

# 添加当前目录和父目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)  # 添加当前目录(eval)
sys.path.insert(0, parent_dir)   # 添加父目录(deepslide)

try:
    # 尝试直接从当前目录导入
    from evaluate import PPT_Speech_Evaluator
    print("从当前目录导入成功")
except ImportError:
    try:
        # 尝试绝对导入
        import deepslide.eval.evaluate as eval_module
        PPT_Speech_Evaluator = eval_module.PPT_Speech_Evaluator
        print("从deepslide.eval导入成功")
    except ImportError:
        print("无法导入evaluate模块，请检查路径")
        sys.exit(1)

# 导入CamelAIClient
try:
    from agents.combine.camel_client import CamelAIClient
    print("CamelAIClient导入成功")
except ImportError:
    # 尝试其他路径
    try:
        camel_client_path = os.path.join(parent_dir, "agents", "combine", "camel_client.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("camel_client", camel_client_path)
        camel_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(camel_module)
        CamelAIClient = camel_module.CamelAIClient
        print("通过文件路径导入CamelAIClient成功")
    except Exception as e:
        print(f"导入CamelAIClient失败: {e}")
        sys.exit(1)
class SimpleAIPPTEvaluator:
    """
    简单的AI评估器
    对每个PPT-演讲稿对齐对进行AI评估
    """
    
    def __init__(self, env_path=None):
        """
        初始化评估器
        
        Args:
            env_path: .env文件路径
        """
        # 初始化AI客户端
        self.ai_client = CamelAIClient(env_path=env_path)
        
        # 评估提示模板
        self.evaluation_prompt = """
        你是一个专业的PPT演示评估专家。请评估以下PPT内容和对应的演讲稿是否匹配良好。
        
        评估维度：
        1. 内容一致性：PPT内容是否准确反映了演讲稿的核心信息
        2. 逻辑连贯性：PPT与演讲稿在逻辑上是否连贯
        3. 信息完整性：PPT是否包含了演讲稿的关键信息
        4. 表达清晰度：PPT是否能帮助观众理解演讲稿内容
        
        请对每个维度给出1-5分的评分（1分最低，5分最高），并给出简要的评价。
        
        PPT内容：
        {ppt_content}
        
        演讲稿内容：
        {speech_content}
        
        请用以下JSON格式返回评估结果：
        {{
            "content_consistency": 分数,
            "logical_coherence": 分数,
            "information_completeness": 分数,
            "clarity_of_expression": 分数,
            "overall_score": 平均分数,
            "strengths": "优点描述",
            "weaknesses": "改进建议",
            "summary": "总体评价"
        }}
        
        只返回JSON，不要有其他文字。
        """
        
    def evaluate_single_pair(self, ppt_content, speech_content):
        """
        评估单个PPT-演讲稿对
        
        Args:
            ppt_content: PPT内容
            speech_content: 演讲稿内容
            
        Returns:
            dict: 评估结果
        """
        try:
            # 准备评估提示
            prompt = self.evaluation_prompt.format(
                ppt_content=ppt_content[:1000],  # 限制长度，避免token过多
                speech_content=speech_content[:1000]
            )
            
            # 调用AI进行评估
            response = self.ai_client.get_response(prompt, system_prompt="你是一个专业的PPT评估专家。")
            
            # 尝试解析JSON响应
            try:
                # 查找JSON部分
                start_idx = response.find('{')
                end_idx = response.rfind('}') + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    # 如果不是纯JSON，尝试直接解析
                    result = json.loads(response)
                    
                return {
                    "success": True,
                    "result": result,
                    "raw_response": response
                }
                
            except json.JSONDecodeError as e:
                # 如果无法解析为JSON，返回原始响应
                return {
                    "success": False,
                    "error": f"无法解析AI响应为JSON: {e}",
                    "raw_response": response
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"评估过程中出错: {str(e)}"
            }
    
    def evaluate_all_pairs(self, aligned_pairs, max_pairs=None):
        """
        评估所有对齐对
        
        Args:
            aligned_pairs: 对齐对列表
            max_pairs: 最大评估对数（用于测试）
            
        Returns:
            list: 所有评估结果
        """
        results = []
        
        # 限制评估对数（用于测试）
        if max_pairs:
            pairs_to_evaluate = aligned_pairs[:max_pairs]
        else:
            pairs_to_evaluate = aligned_pairs
        
        print(f"开始评估 {len(pairs_to_evaluate)} 个对齐对...")
        
        for i, (ppt, speech) in enumerate(pairs_to_evaluate, 1):
            print(f"评估第 {i}/{len(pairs_to_evaluate)} 对...")
            
            # 评估单个对
            evaluation = self.evaluate_single_pair(ppt, speech)
            
            # 提取PPT标题
            title_start = ppt.find('\\frametitle{')
            title = "无标题"
            if title_start != -1:
                title_end = ppt.find('}', title_start)
                if title_end != -1:
                    title = ppt[title_start+len('\\frametitle{'):title_end]
            
            # 整理结果
            pair_result = {
                "pair_id": i,
                "ppt_title": title,
                "ppt_preview": ppt[:200] + ("..." if len(ppt) > 200 else ""),
                "speech_preview": speech[:200] + ("..." if len(speech) > 200 else ""),
                "evaluation": evaluation
            }
            
            results.append(pair_result)
            
            # 打印进度
            if evaluation.get("success"):
                result = evaluation.get("result", {})
                overall = result.get("overall_score", "N/A")
                print(f"  第 {i} 对评估完成，总体评分: {overall}")
            else:
                print(f"  第 {i} 对评估失败: {evaluation.get('error', '未知错误')}")
            
            # 简单延迟，避免API速率限制
            import time
            time.sleep(1)
        
        return results
    
    def save_results(self, results, output_dir, ppt_frame_count, speech_segment_count):
        """
        保存评估结果
        
        Args:
            results: 评估结果列表
            output_dir: 输出目录
            ppt_frame_count: PPT帧数
            speech_segment_count: 演讲稿段数
        """
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 准备要保存的数据
        summary = {
            "timestamp": timestamp,
            "total_pairs_evaluated": len(results),
            "ppt_frame_count": ppt_frame_count,
            "speech_segment_count": speech_segment_count,
            "successful_evaluations": sum(1 for r in results if r["evaluation"].get("success")),
            "failed_evaluations": sum(1 for r in results if not r["evaluation"].get("success"))
        }
        
        # 计算平均分
        scores = []
        for result in results:
            if result["evaluation"].get("success"):
                eval_result = result["evaluation"].get("result", {})
                overall = eval_result.get("overall_score")
                if overall is not None:
                    scores.append(float(overall))
        
        if scores:
            summary["average_score"] = sum(scores) / len(scores)
            summary["min_score"] = min(scores)
            summary["max_score"] = max(scores)
        
        # 完整的评估数据
        full_data = {
            "summary": summary,
            "detailed_results": results
        }
        
        # 保存为JSON文件
        json_path = os.path.join(output_dir, f"ai_evaluation_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n评估结果已保存到: {json_path}")
        
        # 也保存一个简化的文本摘要
        text_path = os.path.join(output_dir, f"ai_evaluation_summary_{timestamp}.txt")
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write("PPT-演讲稿AI评估摘要\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"评估时间: {timestamp}\n")
            f.write(f"评估对数: {len(results)}\n")
            f.write(f"PPT帧数: {ppt_frame_count}\n")
            f.write(f"演讲稿段数: {speech_segment_count}\n")
            f.write(f"成功评估: {summary['successful_evaluations']}\n")
            f.write(f"失败评估: {summary['failed_evaluations']}\n")
            
            if 'average_score' in summary:
                f.write(f"\n评分统计:\n")
                f.write(f"  平均分: {summary['average_score']:.2f}\n")
                f.write(f"  最低分: {summary['min_score']:.2f}\n")
                f.write(f"  最高分: {summary['max_score']:.2f}\n")
            
            f.write("\n详细结果:\n")
            for result in results[:5]:  # 只显示前5个结果
                f.write(f"\n第 {result['pair_id']} 对: {result['ppt_title']}\n")
                if result["evaluation"].get("success"):
                    eval_result = result["evaluation"].get("result", {})
                    f.write(f"  总体评分: {eval_result.get('overall_score', 'N/A')}\n")
                    f.write(f"  优点: {eval_result.get('strengths', 'N/A')[:100]}...\n")
                else:
                    f.write(f"  评估失败: {result['evaluation'].get('error', '未知错误')}\n")
        
        print(f"评估摘要已保存到: {text_path}")
        
        return json_path


def main():
    """主函数"""
    # 配置路径
    data_dir = "/home/ym/DeepSlide/deepslide/eval/data/gen_7a168fdc2f964310bddef4c3a5ab9be4"
    output_dir = "/home/ym/DeepSlide/deepslide/eval/output"
    env_path = "/home/ym/DeepSlide/deepslide/config/env/.env"
    
    # 文件路径
    ppt_path = os.path.join(data_dir, "content.tex")
    speech_path = os.path.join(data_dir, "speech.txt")
    
    print("开始PPT-演讲稿AI评估...")
    print(f"PPT文件: {ppt_path}")
    print(f"演讲稿文件: {speech_path}")
    print(f"输出目录: {output_dir}")
    
    # 检查文件是否存在
    if not os.path.exists(ppt_path):
        print(f"错误: PPT文件不存在 - {ppt_path}")
        return
    
    if not os.path.exists(speech_path):
        print(f"错误: 演讲稿文件不存在 - {speech_path}")
        return
    
    # 第一步：提取PPT和演讲稿对齐对
    print("\n1. 提取PPT和演讲稿内容...")
    evaluator = PPT_Speech_Evaluator()
    evaluator.load_ppt_from_file(ppt_path)
    evaluator.load_speech_from_file(speech_path)
    
    # 获取对齐对
    aligned_pairs = evaluator.get_aligned_pairs()
    ppt_frames = evaluator.ppt_frames
    speech_segments = evaluator.speech_segments
    
    print(f"  提取到 {len(ppt_frames)} 个PPT帧")
    print(f"  提取到 {len(speech_segments)} 个演讲稿段")
    print(f"  生成 {len(aligned_pairs)} 个对齐对")
    
    if not aligned_pairs:
        print("错误: 没有提取到对齐对")
        return
    
    # 第二步：使用AI进行评估
    print("\n2. 初始化AI评估器...")
    ai_evaluator = SimpleAIPPTEvaluator(env_path=env_path)
    
    # 评估所有对齐对（测试时只评估前3个）
    max_pairs_to_evaluate = 3  # 改为None以评估所有对
    print(f"  将评估前 {max_pairs_to_evaluate if max_pairs_to_evaluate else '所有'} 个对齐对")
    
    evaluation_results = ai_evaluator.evaluate_all_pairs(
        aligned_pairs, 
        max_pairs=max_pairs_to_evaluate
    )
    
    # 第三步：保存结果
    print("\n3. 保存评估结果...")
    ai_evaluator.save_results(
        evaluation_results, 
        output_dir, 
        len(ppt_frames), 
        len(speech_segments)
    )
    
    print("\n评估完成!")


if __name__ == "__main__":
    main()