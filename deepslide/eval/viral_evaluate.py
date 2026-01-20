#!/usr/bin/env python3
"""
短视频爆点逻辑PPT评估系统
整合现有的PPT_Speech_Evaluator和CamelAIClient
实现可扩展的多维度评估框架
"""

import os
import sys
import json
import time
import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Any, Optional, Type
from datetime import datetime
import re

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

try:
    from eval.evaluate import PPT_Speech_Evaluator
    print("✓ 成功导入 PPT_Speech_Evaluator")
except ImportError as e:
    print(f"✗ 导入 PPT_Speech_Evaluator 失败: {e}")
    print("尝试从上级目录导入...")
    sys.path.insert(0, os.path.join(project_root, "deepslide"))
    try:
        from evaluate import PPT_Speech_Evaluator
        print("✓ 从上级目录导入成功")
    except ImportError:
        print("✗ 导入失败，使用简化版本")
        # 使用简化版本
        class PPT_Speech_Evaluator:
            def __init__(self):
                pass
            def load_ppt_from_file(self, filepath):
                return self
            def load_speech_from_file(self, filepath):
                return self
            def get_aligned_pairs(self):
                return []

try:
    from agents.combine.camel_client import CamelAIClient
    print("✓ 成功导入 CamelAIClient")
except ImportError as e:
    print(f"✗ 导入 CamelAIClient 失败: {e}")
    # 创建模拟客户端用于测试
    class CamelAIClient:
        def __init__(self, env_path=None):
            self.env_path = env_path
            print(f"[模拟AI] 使用env文件: {env_path}")
        
        def get_response(self, user_input, system_prompt=None):
            # 模拟AI响应
            print(f"[模拟AI] 收到请求，长度: {len(user_input)}")
            
            # 根据提示词类型返回不同的模拟响应
            if "钩子效果" in user_input or "hook" in user_input.lower():
                return json.dumps({
                    "score": 3,
                    "reason": "开头成功提出尖锐问题并展示反常识结论",
                    "strengths": ["问题尖锐性高", "结果先行明确", "利害关系清晰"],
                    "weaknesses": ["开头稍长", "可以更快进入主题"],
                    "suggestions": ["压缩前30秒内容", "增加一个视觉冲击元素"]
                })
            elif "节奏" in user_input or "pacing" in user_input.lower():
                return json.dumps({
                    "score": 4,
                    "reason": "节奏良好，爆点分布合理",
                    "strengths": ["信息密度有起伏", "爆点间隔合理", "高潮部分突出"],
                    "weaknesses": ["中间部分稍显平淡"],
                    "suggestions": ["在第15分钟处增加一个案例爆点"]
                })
            elif "利害关系" in user_input or "stake" in user_input.lower():
                return json.dumps({
                    "score": 4,
                    "reason": "充分建立观众利益关联",
                    "strengths": ["频繁使用'你'、'我们'", "明确观众利益", "使用目标受众语言"],
                    "weaknesses": ["部分技术术语未解释"],
                    "suggestions": ["增加更多具体应用场景"]
                })
            else:
                return json.dumps({
                    "score": 4,
                    "reason": "整体评估良好",
                    "strengths": ["内容一致性好", "逻辑连贯"],
                    "weaknesses": ["可进一步优化"],
                    "suggestions": ["持续改进"]
                })


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class EvaluationResult:
    """评估结果统一格式"""
    metric_name: str                    # 指标名称
    metric_version: str = "1.0"         # 指标版本
    score: float = 0.0                  # 得分
    confidence: float = 0.0             # 评估置信度
    strengths: List[str] = field(default_factory=list)  # 优点
    weaknesses: List[str] = field(default_factory=list) # 缺点
    suggestions: List[str] = field(default_factory=list) # 改进建议
    details: Dict[str, Any] = field(default_factory=dict) # 详细数据
    raw_response: str = ""              # 原始AI响应
    evaluation_time: float = 0.0        # 评估耗时
    success: bool = True                # 是否成功
    
    def to_dict(self):
        """转换为字典"""
        return asdict(self)


@dataclass
class MetricConfig:
    """评估指标配置"""
    name: str                          # 指标名称
    enabled: bool = True               # 是否启用
    weight: float = 1.0                # 权重
    max_score: float = 5.0             # 最高分
    min_score: float = 0.0             # 最低分
    description: str = ""              # 描述
    evaluator_class: Optional[str] = None  # 评估器类名
    evaluator_params: Dict = field(default_factory=dict)  # 评估器参数
    
    def __post_init__(self):
        if not self.description:
            self.description = f"{self.name} 评估指标"


# ============================================================================
# 评估器基类
# ============================================================================

class BaseEvaluator:
    """评估器基类"""
    
    def __init__(self, name: str, version: str = "1.0"):
        self.name = name
        self.version = version
        self.description = ""
        self.required_inputs = ["ppt_content", "speech_content"]
        self.ai_client = None
        
    def set_ai_client(self, ai_client):
        """设置AI客户端"""
        self.ai_client = ai_client
        
    def prepare_input(self, ppt_content: str, speech_content: str) -> Dict:
        """准备评估输入"""
        return {
            "ppt_content": ppt_content,
            "speech_content": speech_content
        }
    
    def evaluate(self, **kwargs) -> EvaluationResult:
        """评估方法（子类必须实现）"""
        raise NotImplementedError(f"Evaluator {self.name} 必须实现 evaluate 方法")
    
    def _parse_json_response(self, response: str) -> Dict:
        """解析AI的JSON响应"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            try:
                # 查找JSON对象
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    return json.loads(json_str)
            except:
                pass
            
            # 如果仍然失败，返回默认结构
            return {
                "score": 0,
                "reason": "无法解析AI响应",
                "strengths": [],
                "weaknesses": ["响应格式错误"],
                "suggestions": ["请检查提示词设计"]
            }


# ============================================================================
# 具体评估器实现
# ============================================================================

class BasicAlignmentEvaluator(BaseEvaluator):
    """基础对齐评估器"""
    
    def __init__(self, ai_client=None):
        super().__init__(name="basic_alignment", version="1.0")
        self.description = "基础内容对齐评估"
        self.ai_client = ai_client
        
        self.prompt_template = """
        你是一个专业的PPT演示评估专家。请评估以下PPT内容和对应的演讲稿是否匹配良好。
        
        评估维度：
        1. 内容一致性：PPT内容是否准确反映了演讲稿的核心信息
        2. 逻辑连贯性：PPT与演讲稿在逻辑上是否连贯
        3. 信息完整性：PPT是否包含了演讲稿的关键信息
        4. 表达清晰度：PPT是否能帮助观众理解演讲稿内容
        
        请对每个维度给出1-5分的评分（1分最低，5分最高），并给出简要的评价。
        
        PPT内容（片段）：
        {ppt_content}
        
        演讲稿内容（片段）：
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
    
    def evaluate(self, ppt_content: str, speech_content: str, **kwargs) -> EvaluationResult:
        """执行基础对齐评估"""
        start_time = time.time()
        
        try:
            # 准备提示词
            prompt = self.prompt_template.format(
                ppt_content=ppt_content[:800],  # 限制长度
                speech_content=speech_content[:800]
            )
            
            # 调用AI
            response = self.ai_client.get_response(prompt)
            
            # 解析响应
            result_data = self._parse_json_response(response)
            
            # 计算总体分数
            overall_score = result_data.get("overall_score", 0)
            if overall_score == 0:
                # 如果没有overall_score，计算平均值
                scores = [
                    result_data.get("content_consistency", 0),
                    result_data.get("logical_coherence", 0),
                    result_data.get("information_completeness", 0),
                    result_data.get("clarity_of_expression", 0)
                ]
                overall_score = sum(scores) / len(scores) if any(scores) else 0
            
            # 创建评估结果
            result = EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=overall_score,
                confidence=0.8,
                strengths=[result_data.get("strengths", "无")],
                weaknesses=[result_data.get("weaknesses", "无")],
                suggestions=["基于评估结果进行改进"],
                details={
                    "content_consistency": result_data.get("content_consistency", 0),
                    "logical_coherence": result_data.get("logical_coherence", 0),
                    "information_completeness": result_data.get("information_completeness", 0),
                    "clarity_of_expression": result_data.get("clarity_of_expression", 0),
                    "summary": result_data.get("summary", "无")
                },
                raw_response=response,
                evaluation_time=time.time() - start_time,
                success=True
            )
            
            return result
            
        except Exception as e:
            return EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=0.0,
                confidence=0.0,
                strengths=[],
                weaknesses=[f"评估失败: {str(e)}"],
                suggestions=["请检查AI服务连接"],
                details={"error": str(e)},
                raw_response="",
                evaluation_time=time.time() - start_time,
                success=False
            )


class HookEvaluator(BaseEvaluator):
    """开头吸引力评估器"""
    
    def __init__(self, ai_client=None):
        super().__init__(name="hook_score", version="1.0")
        self.description = "评估PPT开头是否具有短视频般的钩子效果"
        self.ai_client = ai_client
        self.opening_length = 500  # 开头内容长度
        
        self.prompt_template = """
        你是一个专业的短视频内容策划师和PPT设计专家。请评估以下PPT的开头部分是否具有短视频般的"钩子"（Hook）效果。
        
        评估任务：判断这个PPT开头是否能在前30秒内抓住观众注意力，像爆款短视频一样让人想继续看下去。
        
        评估标准（0-3分）：
        - 0分：平淡开头，直接"目录/背景介绍/定义"，没有任何问题/结果/利害关系
        - 1分：模糊介绍，有"本文主要介绍..."但没制造好奇，缺乏尖锐问题
        - 2分：明确提出问题，有初步引导，但不够强烈或缺乏反常识元素
        - 3分：有强烈问题 + 结果先行/反差 + 清晰利害关系（例如"如果你在做XX，这能帮你少走3天弯路"）
        
        请从以下4个维度分析：
        1. 问题尖锐性：是否提出尖锐、具体、紧迫的问题或矛盾？
        2. 结果先行性：是否提前展示关键结果、数据或反常识结论？
        3. 利害明确性：是否明确告诉观众"这对你有什么用？有什么好处？"
        4. 悬念制造度：是否制造了继续观看的强烈欲望和好奇心？
        
        PPT开头内容：
        {ppt_opening}
        
        演讲稿开头：
        {speech_opening}
        
        请用以下JSON格式返回评估结果，只返回JSON，不要有其他文字：
        {{
            "score": 0-3的整数,
            "reason": "详细的评估理由，解释为什么给这个分数",
            "strengths": ["具体的优点1", "具体的优点2"],
            "weaknesses": ["具体的缺点1", "具体的缺点2"],
            "suggestions": ["具体的改进建议1", "具体的改进建议2"]
        }}
        """
    
    def extract_opening(self, ppt_content: str, speech_content: str) -> Tuple[str, str]:
        """提取开头部分"""
        # 简单实现：取前N个字符
        ppt_opening = ppt_content[:self.opening_length]
        speech_opening = speech_content[:self.opening_length]
        
        # 如果内容太短，返回全部
        if len(ppt_content) < self.opening_length:
            ppt_opening = ppt_content
        if len(speech_content) < self.opening_length:
            speech_opening = speech_content
            
        return ppt_opening, speech_opening
    
    def evaluate(self, ppt_content: str, speech_content: str, **kwargs) -> EvaluationResult:
        """执行钩子效果评估"""
        start_time = time.time()
        
        try:
            # 提取开头内容
            ppt_opening, speech_opening = self.extract_opening(ppt_content, speech_content)
            
            # 准备提示词
            prompt = self.prompt_template.format(
                ppt_opening=ppt_opening,
                speech_opening=speech_opening
            )
            
            # 调用AI
            response = self.ai_client.get_response(prompt)
            
            # 解析响应
            result_data = self._parse_json_response(response)
            
            # 创建评估结果
            result = EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=float(result_data.get("score", 0)),
                confidence=0.85,
                strengths=result_data.get("strengths", []),
                weaknesses=result_data.get("weaknesses", []),
                suggestions=result_data.get("suggestions", []),
                details={
                    "ppt_opening_preview": ppt_opening[:200] + ("..." if len(ppt_opening) > 200 else ""),
                    "speech_opening_preview": speech_opening[:200] + ("..." if len(speech_opening) > 200 else ""),
                    "reason": result_data.get("reason", "无"),
                    "parsed_data": result_data
                },
                raw_response=response,
                evaluation_time=time.time() - start_time,
                success=True
            )
            
            return result
            
        except Exception as e:
            return EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=0.0,
                confidence=0.0,
                strengths=[],
                weaknesses=[f"评估失败: {str(e)}"],
                suggestions=["请检查评估器配置"],
                details={"error": str(e)},
                raw_response="",
                evaluation_time=time.time() - start_time,
                success=False
            )


class PeakStructureEvaluator(BaseEvaluator):
    """节奏与爆点分布评估器"""
    
    def __init__(self, ai_client=None):
        super().__init__(name="peak_structure", version="1.0")
        self.description = "评估PPT的节奏和爆点分布是否合理"
        self.ai_client = ai_client
        
        self.prompt_template = """
        你是一个专业的演讲节奏分析师。请评估以下PPT内容的节奏和爆点分布。
        
        在短视频中，爆款内容的特点是：
        1. 信息密度有起伏，不会长时间平铺直叙
        2. 每隔一段时间就有"新东西/反转/案例/图表"等爆点
        3. 整体节奏张弛有度，高潮部分突出
        
        请分析这个PPT：
        1. 识别可能的高潮/爆点页面（如关键结论、重要图表、反转点）
        2. 评估爆点分布的均匀性和合理性
        3. 检查是否有过长的平淡段落
        
        PPT内容概要：
        {ppt_summary}
        
        演讲稿概要：
        {speech_summary}
        
        请用以下JSON格式返回评估结果：
        {{
            "score": 1-5分,
            "reason": "节奏分析说明",
            "estimated_peaks": 估计的爆点数量,
            "peak_distribution": "均匀/集中/稀疏",
            "longest_flat_section": "最长平淡段描述",
            "strengths": ["优点列表"],
            "weaknesses": ["缺点列表"],
            "suggestions": ["改进建议列表"]
        }}
        
        只返回JSON，不要有其他文字。
        """
    
    def create_summary(self, content: str, max_length: int = 1000) -> str:
        """创建内容概要"""
        if len(content) <= max_length:
            return content
        
        # 简单摘要：取开头、中间和结尾
        third = len(content) // 3
        summary = content[:third//2] + "\n...\n" + content[third:third*2] + "\n...\n" + content[-third//2:]
        return summary
    
    def evaluate(self, ppt_content: str, speech_content: str, **kwargs) -> EvaluationResult:
        """执行节奏评估"""
        start_time = time.time()
        
        try:
            # 创建概要
            ppt_summary = self.create_summary(ppt_content)
            speech_summary = self.create_summary(speech_content)
            
            # 准备提示词
            prompt = self.prompt_template.format(
                ppt_summary=ppt_summary,
                speech_summary=speech_summary
            )
            
            # 调用AI
            response = self.ai_client.get_response(prompt)
            
            # 解析响应
            result_data = self._parse_json_response(response)
            
            # 创建评估结果
            result = EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=float(result_data.get("score", 0)),
                confidence=0.75,
                strengths=result_data.get("strengths", []),
                weaknesses=result_data.get("weaknesses", []),
                suggestions=result_data.get("suggestions", []),
                details={
                    "estimated_peaks": result_data.get("estimated_peaks", 0),
                    "peak_distribution": result_data.get("peak_distribution", "未知"),
                    "longest_flat_section": result_data.get("longest_flat_section", "未知"),
                    "reason": result_data.get("reason", "无"),
                    "parsed_data": result_data
                },
                raw_response=response,
                evaluation_time=time.time() - start_time,
                success=True
            )
            
            return result
            
        except Exception as e:
            return EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=0.0,
                confidence=0.0,
                strengths=[],
                weaknesses=[f"评估失败: {str(e)}"],
                suggestions=["请检查评估器配置"],
                details={"error": str(e)},
                raw_response="",
                evaluation_time=time.time() - start_time,
                success=False
            )


class StakeEvaluator(BaseEvaluator):
    """利害关系评估器"""
    
    def __init__(self, ai_client=None):
        super().__init__(name="stake_score", version="1.0")
        self.description = "评估PPT是否明确建立观众利害关系"
        self.ai_client = ai_client
        
        self.prompt_template = """
        你是一个专业的观众心理学专家。请评估以下PPT内容是否成功建立了与观众的利害关系。
        
        爆款短视频的关键特点是让观众在短时间内意识到"这跟我有关系"。对于PPT，需要评估：
        1. 是否明确提到目标受众，用他们的语言说话
        2. 是否反复把内容与"你之后可以怎么用"关联起来
        3. 是否明确说明能帮助观众"少掉哪些坑"、"获得什么好处"
        
        请分析以下内容：
        1. 统计"你"、"我们"等第二人称词的使用频率和效果
        2. 检查是否明确说明对观众的价值和利益
        3. 评估内容是否贴近目标受众的实际需求和场景
        
        PPT内容：
        {ppt_content}
        
        演讲稿：
        {speech_content}
        
        请用以下JSON格式返回评估结果：
        {{
            "score": 1-5分,
            "reason": "利害关系分析说明",
            "you_count": "你"字出现次数估计,
            "we_count": "我们"出现次数估计,
            "value_propositions": ["发现的价值主张1", "发现的价值主张2"],
            "audience_targeting": "明确/一般/模糊",
            "strengths": ["优点列表"],
            "weaknesses": ["缺点列表"],
            "suggestions": ["改进建议列表"]
        }}
        
        只返回JSON，不要有其他文字。
        """
    
    def evaluate(self, ppt_content: str, speech_content: str, **kwargs) -> EvaluationResult:
        """执行利害关系评估"""
        start_time = time.time()
        
        try:
            # 准备提示词
            prompt = self.prompt_template.format(
                ppt_content=ppt_content[:1000],
                speech_content=speech_content[:1000]
            )
            
            # 调用AI
            response = self.ai_client.get_response(prompt)
            
            # 解析响应
            result_data = self._parse_json_response(response)
            
            # 创建评估结果
            result = EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=float(result_data.get("score", 0)),
                confidence=0.8,
                strengths=result_data.get("strengths", []),
                weaknesses=result_data.get("weaknesses", []),
                suggestions=result_data.get("suggestions", []),
                details={
                    "you_count": result_data.get("you_count", "未知"),
                    "we_count": result_data.get("we_count", "未知"),
                    "value_propositions": result_data.get("value_propositions", []),
                    "audience_targeting": result_data.get("audience_targeting", "未知"),
                    "reason": result_data.get("reason", "无"),
                    "parsed_data": result_data
                },
                raw_response=response,
                evaluation_time=time.time() - start_time,
                success=True
            )
            
            return result
            
        except Exception as e:
            return EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=0.0,
                confidence=0.0,
                strengths=[],
                weaknesses=[f"评估失败: {str(e)}"],
                suggestions=["请检查评估器配置"],
                details={"error": str(e)},
                raw_response="",
                evaluation_time=time.time() - start_time,
                success=False
            )


class VisualDynamismEvaluator(BaseEvaluator):
    """视觉动态性评估器"""
    
    def __init__(self, ai_client=None):
        super().__init__(name="visual_dynamism", version="1.0")
        self.description = "评估PPT的视觉变化和多样性"
        self.ai_client = ai_client
        
        self.prompt_template = """
        你是一个专业的视觉设计评估师。请评估以下PPT内容的视觉动态性和多样性。
        
        短视频通过镜头、构图、景别变化保持视觉新鲜感。PPT也需要：
        1. 版式/色块/图文比例的变化
        2. 避免连续多页相同布局
        3. 合理使用图表、代码、引用等不同元素
        
        请分析这个PPT：
        1. 评估视觉元素的多样性
        2. 检查是否有连续重复的布局
        3. 识别视觉亮点和需要改进的地方
        
        PPT内容（关注视觉元素描述）：
        {ppt_content}
        
        请用以下JSON格式返回评估结果：
        {{
            "score": 1-5分,
            "reason": "视觉动态性分析说明",
            "visual_variety": "高/中/低",
            "repetition_issues": ["发现的重复问题1", "发现的重复问题2"],
            "visual_highlights": ["视觉亮点1", "视觉亮点2"],
            "strengths": ["优点列表"],
            "weaknesses": ["缺点列表"],
            "suggestions": ["改进建议列表"]
        }}
        
        只返回JSON，不要有其他文字。
        """
    
    def evaluate(self, ppt_content: str, speech_content: str, **kwargs) -> EvaluationResult:
        """执行视觉动态性评估"""
        start_time = time.time()
        
        try:
            # 准备提示词
            prompt = self.prompt_template.format(
                ppt_content=ppt_content[:800]
            )
            
            # 调用AI
            response = self.ai_client.get_response(prompt)
            
            # 解析响应
            result_data = self._parse_json_response(response)
            
            # 创建评估结果
            result = EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=float(result_data.get("score", 0)),
                confidence=0.7,
                strengths=result_data.get("strengths", []),
                weaknesses=result_data.get("weaknesses", []),
                suggestions=result_data.get("suggestions", []),
                details={
                    "visual_variety": result_data.get("visual_variety", "未知"),
                    "repetition_issues": result_data.get("repetition_issues", []),
                    "visual_highlights": result_data.get("visual_highlights", []),
                    "reason": result_data.get("reason", "无"),
                    "parsed_data": result_data
                },
                raw_response=response,
                evaluation_time=time.time() - start_time,
                success=True
            )
            
            return result
            
        except Exception as e:
            return EvaluationResult(
                metric_name=self.name,
                metric_version=self.version,
                score=0.0,
                confidence=0.0,
                strengths=[],
                weaknesses=[f"评估失败: {str(e)}"],
                suggestions=["请检查评估器配置"],
                details={"error": str(e)},
                raw_response="",
                evaluation_time=time.time() - start_time,
                success=False
            )


# ============================================================================
# 主评估系统
# ============================================================================

class ViralPPTEvaluator:
    """
    短视频爆点逻辑PPT评估系统
    支持多种评估指标的动态加载和组合
    """
    
    def __init__(self, ai_client=None, config_path: str = None):
        """
        初始化评估系统
        
        Args:
            ai_client: AI客户端实例
            config_path: 配置文件路径
        """
        self.ai_client = ai_client
        self.evaluators: Dict[str, BaseEvaluator] = {}
        self.metrics_config: Dict[str, MetricConfig] = {}
        self.results: Dict[str, List[EvaluationResult]] = {}
        
        # 初始化默认配置
        self._init_default_config()
        
        # 加载外部配置（如果有）
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
        
        # 初始化评估器
        self._init_evaluators()
    
    def _init_default_config(self):
        """初始化默认配置"""
        default_metrics = {
            "basic_alignment": MetricConfig(
                name="basic_alignment",
                description="基础内容对齐评估",
                enabled=True,
                weight=0.2,
                max_score=5.0,
                min_score=0.0,
                evaluator_class="BasicAlignmentEvaluator"
            ),
            "hook_score": MetricConfig(
                name="hook_score",
                description="开头吸引力指数",
                enabled=True,
                weight=0.25,
                max_score=3.0,  # Hook分数是0-3
                min_score=0.0,
                evaluator_class="HookEvaluator"
            ),
            "peak_structure": MetricConfig(
                name="peak_structure",
                description="节奏与爆点分布",
                enabled=True,
                weight=0.20,
                max_score=5.0,
                min_score=0.0,
                evaluator_class="PeakStructureEvaluator"
            ),
            "stake_score": MetricConfig(
                name="stake_score",
                description="利害关系指数",
                enabled=True,
                weight=0.15,
                max_score=5.0,
                min_score=0.0,
                evaluator_class="StakeEvaluator"
            ),
            "visual_dynamism": MetricConfig(
                name="visual_dynamism",
                description="视觉动态性",
                enabled=True,
                weight=0.10,
                max_score=5.0,
                min_score=0.0,
                evaluator_class="VisualDynamismEvaluator"
            ),
            "load_balance": MetricConfig(
                name="load_balance",
                description="认知负荷控制",
                enabled=False,  # 暂时禁用
                weight=0.10,
                max_score=5.0,
                min_score=0.0,
                evaluator_class=None
            )
        }
        
        self.metrics_config = default_metrics
    
    def _init_evaluators(self):
        """初始化评估器实例"""
        evaluator_classes = {
            "BasicAlignmentEvaluator": BasicAlignmentEvaluator,
            "HookEvaluator": HookEvaluator,
            "PeakStructureEvaluator": PeakStructureEvaluator,
            "StakeEvaluator": StakeEvaluator,
            "VisualDynamismEvaluator": VisualDynamismEvaluator,
        }
        
        for metric_name, config in self.metrics_config.items():
            if not config.enabled:
                continue
                
            if config.evaluator_class and config.evaluator_class in evaluator_classes:
                evaluator_class = evaluator_classes[config.evaluator_class]
                evaluator = evaluator_class(self.ai_client)
                self.evaluators[metric_name] = evaluator
                print(f"✓ 初始化评估器: {metric_name}")
            else:
                print(f"⚠ 无法初始化评估器: {metric_name} (类名: {config.evaluator_class})")
    
    def load_config(self, config_path: str):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if 'metrics' in config_data:
                for metric_name, metric_config in config_data['metrics'].items():
                    if metric_name in self.metrics_config:
                        # 更新现有配置
                        for key, value in metric_config.items():
                            setattr(self.metrics_config[metric_name], key, value)
                    else:
                        # 添加新配置
                        self.metrics_config[metric_name] = MetricConfig(
                            name=metric_name,
                            **metric_config
                        )
                
                print(f"✓ 加载配置文件: {config_path}")
                # 重新初始化评估器
                self._init_evaluators()
                
        except Exception as e:
            print(f"✗ 加载配置文件失败: {e}")
    
    def save_config(self, config_path: str):
        """保存配置文件"""
        try:
            config_data = {"metrics": {}}
            for metric_name, config in self.metrics_config.items():
                config_data["metrics"][metric_name] = asdict(config)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True, indent=2)
            
            print(f"✓ 保存配置文件到: {config_path}")
            
        except Exception as e:
            print(f"✗ 保存配置文件失败: {e}")
    
    def register_evaluator(self, metric_name: str, evaluator: BaseEvaluator):
        """注册评估器"""
        self.evaluators[metric_name] = evaluator
        if metric_name not in self.metrics_config:
            self.metrics_config[metric_name] = MetricConfig(
                name=metric_name,
                description=evaluator.description,
                enabled=True
            )
        print(f"✓ 注册评估器: {metric_name}")
    
    def evaluate_single_pair(self, ppt_content: str, speech_content: str, 
                           pair_id: int = 1) -> Dict[str, EvaluationResult]:
        """
        评估单个PPT-演讲稿对
        
        Args:
            ppt_content: PPT内容
            speech_content: 演讲稿内容
            pair_id: 对ID
            
        Returns:
            评估结果字典
        """
        results = {}
        
        for metric_name, config in self.metrics_config.items():
            if not config.enabled:
                continue
                
            # 获取评估器
            evaluator = self.evaluators.get(metric_name)
            if evaluator is None:
                print(f"⚠ 指标 {metric_name} 没有对应的评估器")
                continue
            
            # 执行评估
            try:
                print(f"  评估 {metric_name}...")
                result = evaluator.evaluate(
                    ppt_content=ppt_content,
                    speech_content=speech_content,
                    pair_id=pair_id
                )
                results[metric_name] = result
                
                # 记录结果
                if metric_name not in self.results:
                    self.results[metric_name] = []
                self.results[metric_name].append(result)
                
                if result.success:
                    print(f"    ✓ 得分: {result.score:.2f}")
                else:
                    print(f"    ✗ 失败: {result.weaknesses[0] if result.weaknesses else '未知错误'}")
                
            except Exception as e:
                print(f"✗ 评估指标 {metric_name} 失败: {e}")
                # 创建失败结果
                failed_result = EvaluationResult(
                    metric_name=metric_name,
                    metric_version=config.version if hasattr(config, 'version') else "1.0",
                    score=0.0,
                    confidence=0.0,
                    strengths=[],
                    weaknesses=[f"评估失败: {str(e)}"],
                    suggestions=["请检查评估器配置"],
                    details={"error": str(e)},
                    raw_response="",
                    evaluation_time=0.0,
                    success=False
                )
                results[metric_name] = failed_result
        
        return results
    
    def evaluate_all_pairs(self, aligned_pairs: List[Tuple[str, str]], 
                          max_pairs: int = None) -> Dict[str, List[EvaluationResult]]:
        """
        评估所有对齐对
        
        Args:
            aligned_pairs: 对齐对列表
            max_pairs: 最大评估对数
            
        Returns:
            按指标分组的评估结果
        """
        if not aligned_pairs:
            print("⚠ 没有可评估的对齐对")
            return {}
        
        if max_pairs:
            pairs_to_evaluate = aligned_pairs[:max_pairs]
        else:
            pairs_to_evaluate = aligned_pairs
        
        total_pairs = len(pairs_to_evaluate)
        print(f"开始评估 {total_pairs} 个对齐对...")
        
        for i, (ppt_content, speech_content) in enumerate(pairs_to_evaluate, 1):
            print(f"\n评估第 {i}/{total_pairs} 对...")
            
            # 评估单个对
            pair_results = self.evaluate_single_pair(ppt_content, speech_content, i)
            
            # 延迟避免API限制
            if i < total_pairs:
                time.sleep(0.5)
        
        print(f"\n✓ 评估完成，共评估 {total_pairs} 个对齐对")
        return self.results
    
    def calculate_overall_score(self) -> Dict:
        """计算综合得分"""
        if not self.results:
            return {}
        
        overall_scores = {}
        total_weighted_score = 0.0
        total_enabled_weight = 0.0
        
        print("\n" + "="*60)
        print("综合评分计算")
        print("="*60)
        
        for metric_name, results_list in self.results.items():
            if not results_list:
                continue
                
            # 获取配置
            config = self.metrics_config.get(metric_name, MetricConfig(name=metric_name))
            
            if not config.enabled:
                continue
            
            # 计算平均值（只计算成功的）
            successful_scores = [r.score for r in results_list if r.success]
            if successful_scores:
                avg_score = sum(successful_scores) / len(successful_scores)
                normalized_score = (avg_score - config.min_score) / (config.max_score - config.min_score) * 5.0
                weighted_score = normalized_score * config.weight
                
                overall_scores[metric_name] = {
                    "raw_average": avg_score,
                    "normalized_score": normalized_score,
                    "weighted_score": weighted_score,
                    "weight": config.weight,
                    "success_count": len(successful_scores),
                    "total_count": len(results_list),
                    "max_score": config.max_score
                }
                
                total_weighted_score += weighted_score
                total_enabled_weight += config.weight
                
                print(f"{metric_name:20s}: {normalized_score:5.2f} (原始: {avg_score:5.2f}, 权重: {config.weight:.2f}, 加权: {weighted_score:.2f})")
            else:
                overall_scores[metric_name] = {
                    "raw_average": 0.0,
                    "normalized_score": 0.0,
                    "weighted_score": 0.0,
                    "weight": config.weight,
                    "success_count": 0,
                    "total_count": len(results_list)
                }
        
        # 计算总分
        if total_enabled_weight > 0:
            overall_score = total_weighted_score / total_enabled_weight
            
            overall_scores["total"] = {
                "overall_score": overall_score,
                "total_weighted": total_weighted_score,
                "total_weight": total_enabled_weight,
                "viral_potential": self._get_viral_potential_label(overall_score)
            }
            
            print("-"*60)
            print(f"{'总分':20s}: {overall_score:5.2f} ({overall_scores['total']['viral_potential']})")
            print("="*60)
        
        return overall_scores
    
    def _get_viral_potential_label(self, score: float) -> str:
        """获取爆点潜力标签"""
        if score >= 4.5:
            return "★★★★★ 爆款潜力极高"
        elif score >= 4.0:
            return "★★★★☆ 优秀，具有爆款潜力"
        elif score >= 3.0:
            return "★★★☆☆ 良好，有改进空间"
        elif score >= 2.0:
            return "★★☆☆☆ 一般，需要优化"
        else:
            return "★☆☆☆☆ 需要大幅改进"
    
    def save_results(self, output_dir: str, prefix: str = "viral_evaluation"):
        """
        保存评估结果
        
        Args:
            output_dir: 输出目录
            prefix: 文件名前缀
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. 保存详细结果（JSON格式）
        detailed_results = {
            "timestamp": timestamp,
            "metrics_config": {name: asdict(config) for name, config in self.metrics_config.items()},
            "results_by_metric": {}
        }
        
        for metric_name, results_list in self.results.items():
            detailed_results["results_by_metric"][metric_name] = [
                result.to_dict() for result in results_list
            ]
        
        # 计算综合评分
        overall_scores = self.calculate_overall_score()
        detailed_results["overall_scores"] = overall_scores
        
        json_path = os.path.join(output_dir, f"{prefix}_detailed_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 详细结果已保存到: {json_path}")
        
        # 2. 保存摘要报告（文本格式）
        summary_path = os.path.join(output_dir, f"{prefix}_summary_{timestamp}.txt")
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("            短视频爆点逻辑PPT评估报告\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"评估文件: {prefix}_detailed_{timestamp}.json\n\n")
            
            # 综合评分
            if "total" in overall_scores:
                total = overall_scores["total"]
                f.write("【综合评分】\n")
                f.write(f"总分: {total['overall_score']:.2f}/5.0\n")
                f.write(f"爆点潜力: {total['viral_potential']}\n\n")
            
            # 各维度评分
            f.write("【各维度评分】\n")
            for metric_name, metric_info in overall_scores.items():
                if metric_name == "total":
                    continue
                    
                config = self.metrics_config.get(metric_name, MetricConfig(name=metric_name))
                if metric_info["success_count"] > 0:
                    f.write(f"  {config.description:20s}: {metric_info['normalized_score']:.2f}/5.0")
                    f.write(f" (权重: {metric_info['weight']:.2f})\n")
            
            # 改进建议
            f.write("\n【关键改进建议】\n")
            all_suggestions = []
            
            for metric_name, results_list in self.results.items():
                for result in results_list:
                    if result.success and result.suggestions:
                        all_suggestions.extend(result.suggestions)
            
            # 去重并限制数量
            unique_suggestions = list(set(all_suggestions))[:10]
            for i, suggestion in enumerate(unique_suggestions, 1):
                f.write(f"  {i}. {suggestion}\n")
            
            f.write("\n" + "="*70 + "\n")
            f.write("报告结束\n")
            f.write("="*70 + "\n")
        
        print(f"✓ 摘要报告已保存到: {summary_path}")
        
        return json_path, summary_path
    
    def get_evaluation_summary(self) -> Dict:
        """获取评估摘要"""
        summary = {
            "total_pairs_evaluated": 0,
            "successful_evaluations": 0,
            "failed_evaluations": 0,
            "metrics_summary": {}
        }
        
        for metric_name, results_list in self.results.items():
            summary["total_pairs_evaluated"] = len(results_list)
            success_count = sum(1 for r in results_list if r.success)
            summary["successful_evaluations"] += success_count
            summary["failed_evaluations"] += len(results_list) - success_count
            
            if success_count > 0:
                avg_score = sum(r.score for r in results_list if r.success) / success_count
                summary["metrics_summary"][metric_name] = {
                    "average_score": avg_score,
                    "success_count": success_count,
                    "total_count": len(results_list)
                }
        
        # 添加综合评分
        overall_scores = self.calculate_overall_score()
        if "total" in overall_scores:
            summary["overall_score"] = overall_scores["total"]["overall_score"]
            summary["viral_potential"] = overall_scores["total"]["viral_potential"]
        
        return summary


# ============================================================================
# 使用示例和主程序
# ============================================================================

def create_sample_config(config_path: str):
    """创建示例配置文件"""
    sample_config = {
        "metrics": {
            "basic_alignment": {
                "enabled": True,
                "weight": 0.2,
                "description": "基础内容对齐评估",
                "evaluator_class": "BasicAlignmentEvaluator"
            },
            "hook_score": {
                "enabled": True,
                "weight": 0.25,
                "max_score": 3.0,
                "description": "开头吸引力指数",
                "evaluator_class": "HookEvaluator",
                "evaluator_params": {
                    "opening_length": 500
                }
            },
            "peak_structure": {
                "enabled": True,
                "weight": 0.20,
                "description": "节奏与爆点分布",
                "evaluator_class": "PeakStructureEvaluator"
            },
            "stake_score": {
                "enabled": True,
                "weight": 0.15,
                "description": "利害关系指数",
                "evaluator_class": "StakeEvaluator"
            },
            "visual_dynamism": {
                "enabled": True,
                "weight": 0.10,
                "description": "视觉动态性",
                "evaluator_class": "VisualDynamismEvaluator"
            }
        }
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(sample_config, f, allow_unicode=True, indent=2)
    
    print(f"✓ 示例配置文件已创建: {config_path}")
    return config_path


def main():
    """主函数"""
    # 配置路径
    data_dir = "/home/ym/DeepSlide/deepslide/eval/data/gen_7a168fdc2f964310bddef4c3a5ab9be4"
    output_dir = "/home/ym/DeepSlide/deepslide/eval/output"
    env_path = "/home/ym/DeepSlide/deepslide/config/env/.env"
    
    # 配置文件路径
    config_dir = os.path.join(os.path.dirname(__file__), "config")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "viral_evaluation_config.yaml")
    
    # 文件路径
    ppt_path = os.path.join(data_dir, "content.tex")
    speech_path = os.path.join(data_dir, "speech.txt")
    
    print("="*70)
    print("短视频爆点逻辑PPT评估系统")
    print("="*70)
    print(f"PPT文件: {ppt_path}")
    print(f"演讲稿文件: {speech_path}")
    print(f"输出目录: {output_dir}")
    print(f"配置文件: {config_path}")
    print()
    
    # 检查文件是否存在
    if not os.path.exists(ppt_path):
        print(f"✗ 错误: PPT文件不存在 - {ppt_path}")
        return
    
    if not os.path.exists(speech_path):
        print(f"✗ 错误: 演讲稿文件不存在 - {speech_path}")
        return
    
    # 创建示例配置文件（如果不存在）
    if not os.path.exists(config_path):
        print("未找到配置文件，创建示例配置...")
        create_sample_config(config_path)
    
    # 1. 初始化AI客户端
    print("\n1. 初始化AI客户端...")
    try:
        ai_client = CamelAIClient(env_path=env_path)
        print("✓ AI客户端初始化成功")
    except Exception as e:
        print(f"✗ AI客户端初始化失败: {e}")
        print("使用模拟AI客户端...")
        ai_client = CamelAIClient(env_path=env_path)  # 使用模拟版本
    
    # 2. 提取PPT和演讲稿对齐对
    print("\n2. 提取PPT和演讲稿内容...")
    ppt_speech_evaluator = PPT_Speech_Evaluator()
    ppt_speech_evaluator.load_ppt_from_file(ppt_path)
    ppt_speech_evaluator.load_speech_from_file(speech_path)
    
    aligned_pairs = ppt_speech_evaluator.get_aligned_pairs()
    print(f"✓ 提取到 {len(aligned_pairs)} 个对齐对")
    
    if not aligned_pairs:
        print("✗ 错误: 没有提取到对齐对")
        return
    
    # 3. 初始化爆点评估系统
    print("\n3. 初始化爆点评估系统...")
    viral_evaluator = ViralPPTEvaluator(ai_client=ai_client, config_path=config_path)
    print(f"✓ 加载了 {len(viral_evaluator.evaluators)} 个评估器")
    
    # 4. 执行评估（只评估前3个对作为测试）
    print("\n4. 执行爆点逻辑评估...")
    max_pairs_to_evaluate = 3  # 测试时只评估前3个
    print(f"  将评估前 {max_pairs_to_evaluate} 个对齐对")
    
    evaluation_results = viral_evaluator.evaluate_all_pairs(
        aligned_pairs, 
        max_pairs=max_pairs_to_evaluate
    )
    
    # 5. 计算综合评分
    print("\n5. 计算综合评分...")
    overall_scores = viral_evaluator.calculate_overall_score()
    
    # 6. 保存结果
    print("\n6. 保存评估结果...")
    json_path, summary_path = viral_evaluator.save_results(output_dir)
    
    # 7. 打印摘要
    print("\n" + "="*70)
    print("评估完成!")
    print("="*70)
    
    summary = viral_evaluator.get_evaluation_summary()
    print(f"评估摘要:")
    print(f"  评估对齐对: {summary['total_pairs_evaluated']}")
    print(f"  成功评估: {summary['successful_evaluations']}")
    print(f"  失败评估: {summary['failed_evaluations']}")
    
    if 'overall_score' in summary:
        print(f"  综合评分: {summary['overall_score']:.2f}/5.0")
        print(f"  爆点潜力: {summary['viral_potential']}")
    
    print(f"\n结果文件:")
    print(f"  详细结果: {json_path}")
    print(f"  摘要报告: {summary_path}")
    print("="*70)


if __name__ == "__main__":
    main()