"""
可靠性法则评估模块
包含：系统稳定度、文本忠诚度、视觉忠诚度等评估指标
"""

import math
import logging
from typing import List, Dict, Tuple, Optional, Any, Callable
from dataclasses import dataclass
import re
from collections import Counter

# 设置日志
logger = logging.getLogger(__name__)

@dataclass
class CompilationResult:
    """编译结果数据结构"""
    success: bool
    attempt_id: str
    duration_ms: float
    error_message: Optional[str] = None
    output_size_kb: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class FigureInfo:
    """图像信息数据结构"""
    figure_id: str
    source_path: str
    slide_position: Optional[int] = None
    figure_type: str = "unknown"  # chart, diagram, photo, icon, etc.
    size_kb: float = 0.0
    resolution: Optional[Tuple[int, int]] = None
    caption: Optional[str] = None
    relevance_score: float = 1.0  # 与内容的关联度

# ==================== 系统稳定度函数 ====================

def calculate_acsr(compilation_results: List[CompilationResult]) -> Dict[str, float]:
    """计算平均编译通过成功率 (Average Compilation Success Rate)
    
    Args:
        compilation_results: 编译结果列表
        
    Returns:
        包含多个稳定性指标的字典
    """
    if not compilation_results:
        return {
            "success_rate": 0.0,
            "avg_duration_ms": 0.0,
            "successful_compilations": 0,
            "total_attempts": 0,
            "error_breakdown": {}
        }
    
    total_attempts = len(compilation_results)
    successful_compilations = sum(1 for r in compilation_results if r.success)
    
    # 计算平均编译时长（仅成功编译）
    successful_durations = [r.duration_ms for r in compilation_results if r.success]
    avg_duration = sum(successful_durations) / len(successful_durations) if successful_durations else 0.0
    
    # 错误分类统计
    error_breakdown = {}
    for result in compilation_results:
        if not result.success and result.error_message:
            error_type = _categorize_error(result.error_message)
            error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1
    
    success_rate = successful_compilations / total_attempts
    
    return {
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration,
        "successful_compilations": successful_compilations,
        "total_attempts": total_attempts,
        "error_breakdown": error_breakdown
    }

def _categorize_error(error_message: str) -> str:
    """对错误信息进行分类"""
    error_lower = error_message.lower()
    
    if "memory" in error_lower or "out of memory" in error_lower:
        return "memory_error"
    elif "timeout" in error_lower or "time out" in error_lower:
        return "timeout_error"
    elif "syntax" in error_lower or "parse" in error_lower:
        return "syntax_error"
    elif "import" in error_lower or "module" in error_lower or "package" in error_lower:
        return "dependency_error"
    elif "file" in error_lower or "path" in error_lower or "directory" in error_lower:
        return "file_error"
    elif "permission" in error_lower or "access" in error_lower:
        return "permission_error"
    elif "network" in error_lower or "connection" in error_lower or "http" in error_lower:
        return "network_error"
    else:
        return "other_error"

# ==================== 文本相似度基础函数 ====================

def _tokenize(text: str, ngram: int = 1, lower: bool = True) -> List[str]:
    """文本分词和n-gram生成"""
    if not text:
        return []
    
    if lower:
        text = text.lower()
    
    # 简单的分词（可根据需要改进）
    tokens = re.findall(r'\b\w+\b', text)
    
    if ngram == 1:
        return tokens
    
    # 生成n-gram
    ngrams = []
    for i in range(len(tokens) - ngram + 1):
        ngrams.append(' '.join(tokens[i:i+ngram]))
    
    return ngrams

def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """计算Jaccard相似度"""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    
    return intersection / union

def _lcs_length(seq_a, seq_b):
    """计算最长公共子序列长度（动态规划）"""
    m, n = len(seq_a), len(seq_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i-1] == seq_b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    return dp[m][n]

def _cosine_similarity(vec_a, vec_b):
    """计算余弦相似度"""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)

# ==================== ROUGE评估函数 ====================

def calculate_rouge_n(candidate: str, reference: str, n: int = 1) -> Dict[str, float]:
    """计算ROUGE-N分数
    
    Args:
        candidate: 生成文本
        reference: 参考文本
        n: n-gram大小
        
    Returns:
        包含precision, recall, f1分数的字典
    """
    if not candidate or not reference:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 生成n-gram
    cand_ngrams = _tokenize(candidate, ngram=n)
    ref_ngrams = _tokenize(reference, ngram=n)
    
    if not cand_ngrams or not ref_ngrams:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 使用多重集（允许重复）
    cand_counter = Counter(cand_ngrams)
    ref_counter = Counter(ref_ngrams)
    
    # 计算重叠
    overlap_sum = 0
    for ngram, count in cand_counter.items():
        if ngram in ref_counter:
            overlap_sum += min(count, ref_counter[ngram])
    
    # 计算precision, recall, f1
    precision = overlap_sum / len(cand_ngrams) if cand_ngrams else 0.0
    recall = overlap_sum / len(ref_ngrams) if ref_ngrams else 0.0
    
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

def calculate_rouge_l(candidate: str, reference: str) -> Dict[str, float]:
    """计算ROUGE-L分数（基于最长公共子序列）"""
    if not candidate or not reference:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 分词
    cand_tokens = _tokenize(candidate, ngram=1)
    ref_tokens = _tokenize(reference, ngram=1)
    
    if not cand_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 计算LCS长度
    lcs_len = _lcs_length(cand_tokens, ref_tokens)
    
    # 计算precision, recall, f1
    precision = lcs_len / len(cand_tokens) if cand_tokens else 0.0
    recall = lcs_len / len(ref_tokens) if ref_tokens else 0.0
    
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

def calculate_rouge_s(candidate: str, reference: str, skip_gap: int = 2) -> Dict[str, float]:
    """计算ROUGE-S分数（基于skip-bigram）"""
    if not candidate or not reference:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    def get_skip_bigrams(tokens, max_gap):
        """获取skip-bigram"""
        skip_bigrams = []
        n = len(tokens)
        
        for i in range(n):
            for j in range(i + 1, min(i + max_gap + 1, n)):
                skip_bigrams.append(f"{tokens[i]}_{tokens[j]}")
        
        return skip_bigrams
    
    # 分词
    cand_tokens = _tokenize(candidate, ngram=1)
    ref_tokens = _tokenize(reference, ngram=1)
    
    if not cand_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 获取skip-bigram
    cand_skip_bigrams = get_skip_bigrams(cand_tokens, skip_gap)
    ref_skip_bigrams = get_skip_bigrams(ref_tokens, skip_gap)
    
    if not cand_skip_bigrams or not ref_skip_bigrams:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    # 计算重叠
    cand_counter = Counter(cand_skip_bigrams)
    ref_counter = Counter(ref_skip_bigrams)
    
    overlap_sum = 0
    for bigram, count in cand_counter.items():
        if bigram in ref_counter:
            overlap_sum += min(count, ref_counter[bigram])
    
    # 计算precision, recall, f1
    precision = overlap_sum / len(cand_skip_bigrams) if cand_skip_bigrams else 0.0
    recall = overlap_sum / len(ref_skip_bigrams) if ref_skip_bigrams else 0.0
    
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1
    }

# ==================== 语义相似度函数 ====================

def calculate_jaccard_similarity(candidate: str, reference: str) -> float:
    """计算Jaccard相似度（基于词集）"""
    if not candidate or not reference:
        return 0.0
    
    cand_tokens = set(_tokenize(candidate, ngram=1))
    ref_tokens = set(_tokenize(reference, ngram=1))
    
    return _jaccard_similarity(cand_tokens, ref_tokens)

def calculate_cosine_similarity_bow(candidate: str, reference: str) -> float:
    """基于词袋模型的余弦相似度"""
    if not candidate or not reference:
        return 0.0
    
    # 分词并构建词袋
    cand_tokens = _tokenize(candidate, ngram=1)
    ref_tokens = _tokenize(reference, ngram=1)
    
    if not cand_tokens or not ref_tokens:
        return 0.0
    
    # 构建词汇表
    all_tokens = set(cand_tokens + ref_tokens)
    token_to_idx = {token: i for i, token in enumerate(all_tokens)}
    
    # 构建向量
    cand_vector = [0] * len(all_tokens)
    ref_vector = [0] * len(all_tokens)
    
    for token in cand_tokens:
        if token in token_to_idx:
            cand_vector[token_to_idx[token]] += 1
    
    for token in ref_tokens:
        if token in token_to_idx:
            ref_vector[token_to_idx[token]] += 1
    
    return _cosine_similarity(cand_vector, ref_vector)

# ==================== 综合文本忠诚度函数 ====================

def calculate_textual_fidelity(
    frames_text: List[str],
    paras_text: List[str],
    refs_text: List[str],
    metrics_config: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """计算综合文本忠诚度
    
    Args:
        frames_text: 幻灯片文本列表
        paras_text: 演讲稿文本列表
        refs_text: 参考文本列表
        metrics_config: 指标权重配置
        
    Returns:
        包含各项指标分数的字典
    """
    # 默认配置
    if metrics_config is None:
        metrics_config = {
            "rouge1_weight": 0.25,
            "rouge2_weight": 0.20,
            "rougeL_weight": 0.20,
            "rougeS_weight": 0.10,
            "jaccard_weight": 0.15,
            "cosine_weight": 0.10
        }
    
    # 验证输入
    n = min(len(frames_text or []), len(paras_text or []), len(refs_text or []))
    if n <= 0:
        return _empty_text_fidelity_result()
    
    # 初始化分数累加器
    scores = {
        "rouge1": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        "rouge2": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        "rougeL": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        "rougeS": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
        "jaccard": 0.0,
        "cosine": 0.0
    }
    
    # 逐帧计算
    for k in range(n):
        # ROUGE-1
        rouge1_para = calculate_rouge_n(paras_text[k], refs_text[k], 1)
        rouge1_frame = calculate_rouge_n(frames_text[k], refs_text[k], 1)
        
        # ROUGE-2
        rouge2_para = calculate_rouge_n(paras_text[k], refs_text[k], 2)
        rouge2_frame = calculate_rouge_n(frames_text[k], refs_text[k], 2)
        
        # ROUGE-L
        rougeL_para = calculate_rouge_l(paras_text[k], refs_text[k])
        rougeL_frame = calculate_rouge_l(frames_text[k], refs_text[k])
        
        # ROUGE-S
        rougeS_para = calculate_rouge_s(paras_text[k], refs_text[k])
        rougeS_frame = calculate_rouge_s(frames_text[k], refs_text[k])
        
        # Jaccard相似度
        jaccard_para = calculate_jaccard_similarity(paras_text[k], refs_text[k])
        jaccard_frame = calculate_jaccard_similarity(frames_text[k], refs_text[k])
        
        # 余弦相似度
        cosine_para = calculate_cosine_similarity_bow(paras_text[k], refs_text[k])
        cosine_frame = calculate_cosine_similarity_bow(frames_text[k], refs_text[k])
        
        # 累加平均（幻灯片和演讲稿各50%权重）
        for metric in ["precision", "recall", "f1"]:
            scores["rouge1"][metric] += 0.5 * (rouge1_para[metric] + rouge1_frame[metric])
            scores["rouge2"][metric] += 0.5 * (rouge2_para[metric] + rouge2_frame[metric])
            scores["rougeL"][metric] += 0.5 * (rougeL_para[metric] + rougeL_frame[metric])
            scores["rougeS"][metric] += 0.5 * (rougeS_para[metric] + rougeS_frame[metric])
        
        scores["jaccard"] += 0.5 * (jaccard_para + jaccard_frame)
        scores["cosine"] += 0.5 * (cosine_para + cosine_frame)
    
    # 计算平均值
    for metric in ["rouge1", "rouge2", "rougeL", "rougeS"]:
        for submetric in ["precision", "recall", "f1"]:
            scores[metric][submetric] /= n
    
    scores["jaccard"] /= n
    scores["cosine"] /= n
    
    # 计算综合分数
    weighted_scores = {
        "rouge1_f1": scores["rouge1"]["f1"] * metrics_config["rouge1_weight"],
        "rouge2_f1": scores["rouge2"]["f1"] * metrics_config["rouge2_weight"],
        "rougeL_f1": scores["rougeL"]["f1"] * metrics_config["rougeL_weight"],
        "rougeS_f1": scores["rougeS"]["f1"] * metrics_config["rougeS_weight"],
        "jaccard": scores["jaccard"] * metrics_config["jaccard_weight"],
        "cosine": scores["cosine"] * metrics_config["cosine_weight"]
    }
    
    overall_score = sum(weighted_scores.values())
    
    # 构建结果
    result = {
        "overall": overall_score,
        "detailed_scores": scores,
        "weighted_scores": weighted_scores,
        "config": metrics_config,
        "num_frames": n
    }
    
    return result

def _empty_text_fidelity_result() -> Dict[str, Any]:
    """返回空的文本忠诚度结果"""
    return {
        "overall": 0.0,
        "detailed_scores": {
            "rouge1": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "rouge2": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "rougeL": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "rougeS": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "jaccard": 0.0,
            "cosine": 0.0
        },
        "weighted_scores": {},
        "config": {},
        "num_frames": 0
    }

# ==================== 视觉忠诚度函数 ====================

def calculate_visual_fidelity(
    source_figures: List[FigureInfo],
    slide_figures: List[FigureInfo],
    include_content_analysis: bool = False
) -> Dict[str, Any]:
    """计算综合视觉忠诚度
    
    Args:
        source_figures: 源文档中的图像列表
        slide_figures: 幻灯片中的图像列表
        include_content_analysis: 是否包含内容分析（需要图像处理库）
        
    Returns:
        包含各项指标的字典
    """
    if not source_figures:
        return {
            "figure_proportion": 0.0,
            "matched_figures": 0,
            "total_source_figures": 0,
            "total_slide_figures": len(slide_figures),
            "figure_types_match": {},
            "relevance_scores": [],
            "overall": 0.0
        }
    
    total_source = len(source_figures)
    total_slide = len(slide_figures)
    
    # 1. 图像比例
    figure_proportion = total_slide / total_source if total_source > 0 else 0.0
    
    # 2. 图像匹配（简单基于文件名/路径匹配）
    matched_figures = 0
    figure_types_match = {}
    relevance_scores = []
    
    for slide_fig in slide_figures:
        # 寻找匹配的源图像
        best_match = None
        best_score = 0.0
        
        for source_fig in source_figures:
            # 简单匹配策略：文件名相似度
            match_score = _figure_match_score(slide_fig, source_fig)
            if match_score > best_score:
                best_score = match_score
                best_match = source_fig
        
        if best_match and best_score > 0.3:  # 阈值可调
            matched_figures += 1
            relevance_scores.append(best_score)
            
            # 统计类型匹配
            fig_type = best_match.figure_type
            figure_types_match[fig_type] = figure_types_match.get(fig_type, 0) + 1
    
    # 3. 类型分布分析
    source_type_dist = {}
    for fig in source_figures:
        source_type_dist[fig.figure_type] = source_type_dist.get(fig.figure_type, 0) + 1
    
    slide_type_dist = {}
    for fig in slide_figures:
        slide_type_dist[fig.figure_type] = slide_type_dist.get(fig.figure_type, 0) + 1
    
    # 4. 计算综合分数
    proportion_score = min(1.0, figure_proportion)  # 比例分数（不超过100%）
    match_score = matched_figures / total_source if total_source > 0 else 0.0
    relevance_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
    
    # 类型匹配分数（Jaccard相似度）
    source_types = set(source_type_dist.keys())
    slide_types = set(slide_type_dist.keys())
    type_match_score = _jaccard_similarity(source_types, slide_types)
    
    # 综合分数（可调整权重）
    overall_score = (
        0.4 * proportion_score +  # 图像比例
        0.3 * match_score +       # 匹配数量
        0.2 * relevance_score +   # 匹配质量
        0.1 * type_match_score    # 类型分布
    )
    
    return {
        "figure_proportion": figure_proportion,
        "matched_figures": matched_figures,
        "total_source_figures": total_source,
        "total_slide_figures": total_slide,
        "proportion_score": proportion_score,
        "match_score": match_score,
        "relevance_score": relevance_score,
        "type_match_score": type_match_score,
        "source_type_distribution": source_type_dist,
        "slide_type_distribution": slide_type_dist,
        "figure_types_match": figure_types_match,
        "relevance_scores": relevance_scores,
        "overall": overall_score
    }

def _figure_match_score(fig1: FigureInfo, fig2: FigureInfo) -> float:
    """计算两个图像之间的匹配分数"""
    score = 0.0
    
    # 1. 文件名匹配
    if fig1.source_path and fig2.source_path:
        # 提取文件名
        import os
        name1 = os.path.basename(fig1.source_path).lower()
        name2 = os.path.basename(fig2.source_path).lower()
        
        if name1 == name2:
            score += 0.5
        elif name1 in name2 or name2 in name1:
            score += 0.3
    
    # 2. 图像类型匹配
    if fig1.figure_type == fig2.figure_type:
        score += 0.2
    
    # 3. 大小相似度（如果都有大小信息）
    if fig1.size_kb > 0 and fig2.size_kb > 0:
        size_ratio = min(fig1.size_kb, fig2.size_kb) / max(fig1.size_kb, fig2.size_kb)
        score += 0.2 * size_ratio
    
    # 4. 标题相似度（如果都有标题）
    if fig1.caption and fig2.caption:
        caption_similarity = calculate_jaccard_similarity(fig1.caption, fig2.caption)
        score += 0.1 * caption_similarity
    
    return min(1.0, score)  # 确保不超过1.0

# ==================== 综合可靠性评估器 ====================

class ReliabilityEvaluator:
    """可靠性法则综合评估器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
    def evaluate_system_stability(self, compilation_results: List[CompilationResult]) -> Dict:
        """评估系统稳定度"""
        self.logger.info("评估系统稳定度...")
        return calculate_acsr(compilation_results)
    
    def evaluate_textual_fidelity(self, 
                                  frames_text: List[str],
                                  paras_text: List[str],
                                  refs_text: List[str]) -> Dict:
        """评估文本忠诚度"""
        self.logger.info("评估文本忠诚度...")
        return calculate_textual_fidelity(frames_text, paras_text, refs_text, self.config.get("text_metrics"))
    
    def evaluate_visual_fidelity(self,
                                 source_figures: List[FigureInfo],
                                 slide_figures: List[FigureInfo]) -> Dict:
        """评估视觉忠诚度"""
        self.logger.info("评估视觉忠诚度...")
        return calculate_visual_fidelity(source_figures, slide_figures)
    
    def comprehensive_evaluate(self,
                              compilation_results: List[CompilationResult],
                              frames_text: List[str],
                              paras_text: List[str],
                              refs_text: List[str],
                              source_figures: List[FigureInfo],
                              slide_figures: List[FigureInfo]) -> Dict:
        """综合可靠性评估"""
        results = {
            "system_stability": {},
            "textual_fidelity": {},
            "visual_fidelity": {},
            "overall_reliability": 0.0,
            "diagnosis": {},
            "suggestions": []
        }
        
        # 系统稳定度
        if compilation_results:
            results["system_stability"] = self.evaluate_system_stability(compilation_results)
        
        # 文本忠诚度
        if frames_text and paras_text and refs_text:
            results["textual_fidelity"] = self.evaluate_textual_fidelity(frames_text, paras_text, refs_text)
        
        # 视觉忠诚度
        if source_figures:
            results["visual_fidelity"] = self.evaluate_visual_fidelity(source_figures, slide_figures)
        
        # 计算综合可靠性分数
        overall_score = self._calculate_overall_reliability(results)
        results["overall_reliability"] = overall_score
        
        # 诊断和建议
        results["diagnosis"] = self._diagnose_reliability_issues(results)
        results["suggestions"] = self._generate_reliability_suggestions(results)
        
        return results
    
    def _calculate_overall_reliability(self, results: Dict) -> float:
        """计算综合可靠性分数"""
        weights = self.config.get("reliability_weights", {
            "system_stability": 0.3,
            "textual_fidelity": 0.4,
            "visual_fidelity": 0.3
        })
        
        score = 0.0
        total_weight = 0.0
        
        # 系统稳定度
        if "system_stability" in results and results["system_stability"]:
            stability_score = results["system_stability"].get("success_rate", 0.0)
            score += stability_score * weights["system_stability"]
            total_weight += weights["system_stability"]
        
        # 文本忠诚度
        if "textual_fidelity" in results and results["textual_fidelity"]:
            text_score = results["textual_fidelity"].get("overall", 0.0)
            score += text_score * weights["textual_fidelity"]
            total_weight += weights["textual_fidelity"]
        
        # 视觉忠诚度
        if "visual_fidelity" in results and results["visual_fidelity"]:
            visual_score = results["visual_fidelity"].get("overall", 0.0)
            score += visual_score * weights["visual_fidelity"]
            total_weight += weights["visual_fidelity"]
        
        # 归一化
        if total_weight > 0:
            return score / total_weight
        return 0.0
    
    def _diagnose_reliability_issues(self, results: Dict) -> Dict:
        """诊断可靠性问题"""
        diagnosis = {}
        
        # 系统稳定度诊断
        if "system_stability" in results:
            stability = results["system_stability"]
            if stability.get("success_rate", 0) < 0.8:
                diagnosis["stability_issue"] = f"编译成功率较低: {stability.get('success_rate', 0):.1%}"
            
            error_breakdown = stability.get("error_breakdown", {})
            if error_breakdown:
                diagnosis["common_errors"] = error_breakdown
        
        # 文本忠诚度诊断
        if "textual_fidelity" in results:
            text_fid = results["textual_fidelity"]
            if text_fid.get("overall", 0) < 0.7:
                diagnosis["text_fidelity_issue"] = f"文本忠诚度较低: {text_fid.get('overall', 0):.3f}"
                
                # 分析具体哪个指标低
                detailed = text_fid.get("detailed_scores", {})
                low_metrics = []
                for metric_name, metric_scores in detailed.items():
                    if isinstance(metric_scores, dict):
                        f1 = metric_scores.get("f1", 0)
                        if f1 < 0.6:
                            low_metrics.append(f"{metric_name}: {f1:.3f}")
                    elif isinstance(metric_scores, (int, float)) and metric_scores < 0.6:
                        low_metrics.append(f"{metric_name}: {metric_scores:.3f}")
                
                if low_metrics:
                    diagnosis["low_text_metrics"] = low_metrics
        
        # 视觉忠诚度诊断
        if "visual_fidelity" in results:
            visual_fid = results["visual_fidelity"]
            if visual_fid.get("overall", 0) < 0.6:
                diagnosis["visual_fidelity_issue"] = f"视觉忠诚度较低: {visual_fid.get('overall', 0):.3f}"
            
            proportion = visual_fid.get("figure_proportion", 0)
            if proportion < 0.5:
                diagnosis["low_figure_proportion"] = f"图像保留比例较低: {proportion:.1%}"
        
        return diagnosis
    
    def _generate_reliability_suggestions(self, results: Dict) -> List[str]:
        """生成可靠性改进建议"""
        suggestions = []
        
        # 系统稳定度建议
        if "system_stability" in results:
            stability = results["system_stability"]
            success_rate = stability.get("success_rate", 0)
            
            if success_rate < 0.8:
                suggestions.append(f"系统稳定度较低(成功率: {success_rate:.1%})，建议：检查编译环境，优化资源管理")
            
            error_breakdown = stability.get("error_breakdown", {})
            for error_type, count in error_breakdown.items():
                if count > 2:  # 频繁出现的错误
                    suggestions.append(f"频繁出现{error_type}错误({count}次)，建议排查相关配置")
        
        # 文本忠诚度建议
        if "textual_fidelity" in results:
            text_fid = results["textual_fidelity"]
            overall = text_fid.get("overall", 0)
            
            if overall < 0.7:
                suggestions.append(f"文本忠诚度较低({overall:.3f})，建议检查内容提取和生成逻辑")
                
                detailed = text_fid.get("detailed_scores", {})
                rouge1_f1 = detailed.get("rouge1", {}).get("f1", 0)
                rouge2_f1 = detailed.get("rouge2", {}).get("f1", 0)
                
                if rouge2_f1 < rouge1_f1 * 0.7:
                    suggestions.append("ROUGE-2分数明显低于ROUGE-1，说明短语级别匹配不佳，建议改进连贯性生成")
        
        # 视觉忠诚度建议
        if "visual_fidelity" in results:
            visual_fid = results["visual_fidelity"]
            overall = visual_fid.get("overall", 0)
            
            if overall < 0.6:
                suggestions.append(f"视觉忠诚度较低({overall:.3f})，建议检查图像提取和布局逻辑")
            
            proportion = visual_fid.get("figure_proportion", 0)
            if proportion < 0.5:
                suggestions.append(f"图像保留比例较低({proportion:.1%})，建议优化图像检测和选择算法")
        
        if not suggestions:
            suggestions.append("可靠性表现良好，继续保持当前生成策略。")
        
        return suggestions
    
    def generate_reliability_report(self, results: Dict, format: str = "text") -> str:
        """生成可靠性评估报告"""
        report_lines = []
        
        report_lines.append("=" * 60)
        report_lines.append("可靠性评估报告")
        report_lines.append("=" * 60)
        
        # 系统稳定度
        if "system_stability" in results and results["system_stability"]:
            stability = results["system_stability"]
            report_lines.append("\n【系统稳定度】")
            report_lines.append(f"编译成功率: {stability.get('success_rate', 0):.1%}")
            report_lines.append(f"成功编译次数: {stability.get('successful_compilations', 0)}")
            report_lines.append(f"总尝试次数: {stability.get('total_attempts', 0)}")
            report_lines.append(f"平均编译时长: {stability.get('avg_duration_ms', 0):.1f}ms")
            
            error_breakdown = stability.get("error_breakdown", {})
            if error_breakdown:
                report_lines.append("错误分布:")
                for error_type, count in error_breakdown.items():
                    report_lines.append(f"  - {error_type}: {count}次")
        
        # 文本忠诚度
        if "textual_fidelity" in results and results["textual_fidelity"]:
            text_fid = results["textual_fidelity"]
            report_lines.append("\n【文本忠诚度】")
            report_lines.append(f"综合分数: {text_fid.get('overall', 0):.3f}")
            report_lines.append(f"评估帧数: {text_fid.get('num_frames', 0)}")
            
            detailed = text_fid.get("detailed_scores", {})
            if detailed:
                report_lines.append("详细指标:")
                report_lines.append(f"  ROUGE-1 F1: {detailed.get('rouge1', {}).get('f1', 0):.3f}")
                report_lines.append(f"  ROUGE-2 F1: {detailed.get('rouge2', {}).get('f1', 0):.3f}")
                report_lines.append(f"  ROUGE-L F1: {detailed.get('rougeL', {}).get('f1', 0):.3f}")
                report_lines.append(f"  Jaccard相似度: {detailed.get('jaccard', 0):.3f}")
                report_lines.append(f"  余弦相似度: {detailed.get('cosine', 0):.3f}")
        
        # 视觉忠诚度
        if "visual_fidelity" in results and results["visual_fidelity"]:
            visual_fid = results["visual_fidelity"]
            report_lines.append("\n【视觉忠诚度】")
            report_lines.append(f"综合分数: {visual_fid.get('overall', 0):.3f}")
            report_lines.append(f"图像比例: {visual_fid.get('figure_proportion', 0):.1%}")
            report_lines.append(f"匹配图像数: {visual_fid.get('matched_figures', 0)}/{visual_fid.get('total_source_figures', 0)}")
            report_lines.append(f"源文档图像数: {visual_fid.get('total_source_figures', 0)}")
            report_lines.append(f"幻灯片图像数: {visual_fid.get('total_slide_figures', 0)}")
        
        # 综合可靠性
        report_lines.append("\n【综合可靠性】")
        report_lines.append(f"总体可靠性分数: {results.get('overall_reliability', 0):.3f}")
        
        # 诊断和建议
        diagnosis = results.get("diagnosis", {})
        if diagnosis:
            report_lines.append("\n【问题诊断】")
            for issue, description in diagnosis.items():
                if isinstance(description, list):
                    report_lines.append(f"{issue}:")
                    for item in description:
                        report_lines.append(f"  - {item}")
                else:
                    report_lines.append(f"{issue}: {description}")
        
        suggestions = results.get("suggestions", [])
        if suggestions:
            report_lines.append("\n【改进建议】")
            for i, suggestion in enumerate(suggestions, 1):
                report_lines.append(f"{i}. {suggestion}")
        
        report_lines.append("\n" + "=" * 60)
        
        if format == "markdown":
            return self._format_markdown_report(report_lines)
        
        return "\n".join(report_lines)
    
    def _format_markdown_report(self, lines: List[str]) -> str:
        """格式化为Markdown报告"""
        md_lines = []
        for line in lines:
            if line.startswith("【"):
                md_lines.append(f"## {line[1:-1]}")
            elif line.startswith("  -"):
                md_lines.append(line)
            elif ":" in line and not line.startswith("=") and not line.startswith("综合分数"):
                parts = line.split(":", 1)
                md_lines.append(f"**{parts[0]}**:{parts[1]}")
            elif not line.startswith("="):
                md_lines.append(line)
        return "\n".join(md_lines)

# ==================== 使用示例 ====================

def create_example_data():
    """创建示例数据"""
    
    # 编译结果示例
    compilation_results = [
        CompilationResult(
            success=True,
            attempt_id="attempt_001",
            duration_ms=1250.5,
            output_size_kb=2450.2
        ),
        CompilationResult(
            success=False,
            attempt_id="attempt_002",
            duration_ms=850.3,
            error_message="MemoryError: Out of memory while processing image",
            output_size_kb=0.0
        ),
        CompilationResult(
            success=True,
            attempt_id="attempt_003",
            duration_ms=980.7,
            output_size_kb=1875.6
        ),
        CompilationResult(
            success=True,
            attempt_id="attempt_004",
            duration_ms=1120.9,
            output_size_kb=2100.3
        )
    ]
    
    # 文本数据示例
    frames_text = [
        "演讲吸引力评估系统",
        "开场钩子分数(OHS)计算",
        "留存分数(RS)包含三个指标",
        "认知负载控制(CLC)优化"
    ]
    
    paras_text = [
        "今天介绍演讲吸引力评估系统",
        "开场钩子分数衡量前几页的吸引力",
        "留存分数包含刺激频率、最大平淡度和节奏分数",
        "认知负载控制通过知识点关联降低理解成本"
    ]
    
    refs_text = [
        "演讲材料评估系统设计",
        "开场钩子分数(OHS)计算方法",
        "留存分数(RS)由SF、MP、RR组成",
        "认知负载控制(CLC)管理信息密度"
    ]
    
    # 图像数据示例
    source_figures = [
        FigureInfo(
            figure_id="fig1",
            source_path="/docs/images/system_arch.png",
            figure_type="diagram",
            size_kb=450.5,
            caption="系统架构图"
        ),
        FigureInfo(
            figure_id="fig2",
            source_path="/docs/images/ohs_formula.png",
            figure_type="chart",
            size_kb=320.2,
            caption="OHS计算公式"
        ),
        FigureInfo(
            figure_id="fig3",
            source_path="/docs/images/rs_components.jpg",
            figure_type="chart",
            size_kb=280.7,
            caption="RS组成要素"
        )
    ]
    
    slide_figures = [
        FigureInfo(
            figure_id="slide_fig1",
            source_path="/slides/images/system_arch.png",
            figure_type="diagram",
            size_kb=420.8,
            caption="系统架构设计"
        ),
        FigureInfo(
            figure_id="slide_fig2",
            source_path="/slides/images/ohs_formula.png",
            figure_type="chart",
            size_kb=315.3,
            caption="OHS计算公式"
        )
    ]
    
    return compilation_results, frames_text, paras_text, refs_text, source_figures, slide_figures

def main():
    """主函数示例"""
    print("可靠性评估系统示例")
    print("-" * 40)
    
    # 创建评估器
    config = {
        "text_metrics": {
            "rouge1_weight": 0.25,
            "rouge2_weight": 0.20,
            "rougeL_weight": 0.20,
            "rougeS_weight": 0.10,
            "jaccard_weight": 0.15,
            "cosine_weight": 0.10
        },
        "reliability_weights": {
            "system_stability": 0.3,
            "textual_fidelity": 0.4,
            "visual_fidelity": 0.3
        }
    }
    
    evaluator = ReliabilityEvaluator(config)
    
    # 创建示例数据
    compilation_results, frames_text, paras_text, refs_text, source_figures, slide_figures = create_example_data()
    
    # 执行综合评估
    results = evaluator.comprehensive_evaluate(
        compilation_results=compilation_results,
        frames_text=frames_text,
        paras_text=paras_text,
        refs_text=refs_text,
        source_figures=source_figures,
        slide_figures=slide_figures
    )
    
    # 生成报告
    report = evaluator.generate_reliability_report(results)
    print(report)
    
    # 测试单个函数
    print("\n" + "=" * 60)
    print("单个指标测试:")
    print("-" * 60)
    
    # 测试ROUGE计算
    test_candidate = "深度学习模型在自然语言处理中的应用"
    test_reference = "深度学习在自然语言处理领域的应用模型"
    
    rouge1 = calculate_rouge_n(test_candidate, test_reference, 1)
    rouge2 = calculate_rouge_n(test_candidate, test_reference, 2)
    rougeL = calculate_rouge_l(test_candidate, test_reference)
    
    print(f"测试文本1: '{test_candidate}'")
    print(f"测试文本2: '{test_reference}'")
    print(f"ROUGE-1 F1: {rouge1['f1']:.3f}")
    print(f"ROUGE-2 F1: {rouge2['f1']:.3f}")
    print(f"ROUGE-L F1: {rougeL['f1']:.3f}")
    
    # 测试Jaccard相似度
    jaccard = calculate_jaccard_similarity(test_candidate, test_reference)
    print(f"Jaccard相似度: {jaccard:.3f}")
    
    # 保存结果
    import json
    with open("reliability_results.json", "w", encoding="utf-8") as f:
        # 自定义序列化函数
        def default_serializer(obj):
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            elif isinstance(obj, tuple):
                return list(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        
        json.dump(results, f, ensure_ascii=False, indent=2, default=default_serializer)
    
    print("\n结果已保存至 reliability_results.json")

if __name__ == "__main__":
    main()