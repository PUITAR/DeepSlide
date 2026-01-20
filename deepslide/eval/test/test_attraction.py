import math
import logging
from typing import List, Dict, Tuple, Callable, Optional, Any
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== 数据结构定义 ====================

@dataclass
class SlideFrame:
    """幻灯片帧数据结构"""
    content: str  # 文本内容
    slide_type: str  # 类型：title, bullet, image, comparison, quote, etc.
    has_image: bool = False
    has_bullet: bool = False
    bullet_count: int = 0
    word_count: int = 0
    visual_complexity: float = 0.0  # 0-1，视觉复杂度
    contrast_ratio: float = 0.0  # 对比度
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        # 自动计算字数
        if self.word_count == 0 and self.content:
            self.word_count = len(self.content.split())

@dataclass
class SpeechParagraph:
    """演讲稿段落数据结构"""
    text: str  # 文本内容
    duration_sec: float = 0.0  # 预计讲述时长
    word_count: int = 0
    emotional_tone: float = 0.0  # -1到1，情感基调
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        # 自动计算字数
        if self.word_count == 0 and self.text:
            self.word_count = len(self.text.split())

@dataclass
class KnowledgeNode:
    """知识点节点"""
    id: int
    content: str
    frame_idx: int  # 对应的幻灯片索引
    para_idx: int  # 对应的段落索引

# ==================== 规则函数定义 ====================

class RuleLibrary:
    """规则函数库"""
    
    @staticmethod
    def has_problem_statement(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否包含问题陈述/痛点"""
        problem_keywords = ["问题", "痛点", "挑战", "困难", "为什么", "如何解决", "矛盾", "难点"]
        text = para.text + " " + frame.content
        return any(keyword in text for keyword in problem_keywords)
    
    @staticmethod
    def has_personal_story(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否包含个人故事/案例"""
        story_indicators = ["我", "我们", "案例", "故事", "经历", "当时", "记得", "曾经", "亲自"]
        
        # 检查第一人称
        first_person = ["我", "我们", "本人", "笔者", "我的"]
        has_first_person = any(pronoun in para.text for pronoun in first_person)
        
        # 检查故事性词汇
        has_story_words = any(indicator in para.text for indicator in story_indicators)
        
        # 检查是否有时间叙事
        time_words = ["去年", "今年", "当时", "昨天", "最近", "以前", "上周", "上个月"]
        has_time_narrative = any(word in para.text for word in time_words)
        
        return has_first_person or has_story_words or has_time_narrative
    
    @staticmethod
    def has_visual_impact(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否有强烈的视觉冲击"""
        # 幻灯片有图片
        if frame.has_image:
            return True
        
        # 幻灯片视觉复杂度适中（不是纯文字也不是太花哨）
        if 0.3 <= frame.visual_complexity <= 0.7:
            return True
        
        # 高对比度
        if frame.contrast_ratio > 0.7:
            return True
        
        # 有图表或数据可视化
        chart_keywords = ["图表", "图", "数据", "统计", "趋势", "柱状图", "饼图", "折线图"]
        if any(keyword in frame.content for keyword in chart_keywords):
            return True
        
        return False
    
    @staticmethod
    def has_question_interaction(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否包含提问或互动"""
        # 直接提问
        question_indicators = ["？", "?", "吗", "呢", "如何", "什么", "为什么", "怎样", "哪个"]
        if any(indicator in para.text for indicator in question_indicators):
            return True
        
        # 反问句
        rhetorical_indicators = ["难道", "不是吗", "对不对", "是不是", "可否"]
        if any(indicator in para.text for indicator in rhetorical_indicators):
            return True
        
        # 互动邀请
        interaction_indicators = ["请思考", "想象一下", "假设", "考虑", "请想象", "试想"]
        if any(indicator in para.text for indicator in interaction_indicators):
            return True
        
        # 直接称呼听众
        audience_indicators = ["你", "你们", "大家", "各位", "听众", "观众"]
        if any(indicator in para.text for indicator in audience_indicators):
            return True
        
        return False
    
    @staticmethod
    def has_data_impact(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否有数据冲击"""
        # 检查百分比、数字
        import re
        # 匹配百分比、倍数、具体数字
        number_patterns = [
            r'\d+%',  # 百分比
            r'\d+\.\d+%',  # 小数百分比
            r'\d+倍',  # 倍数
            r'\d+次',  # 次数
            r'\d+个',  # 个数
            r'\d+\.\d+',  # 小数
            r'\b\d+\b',  # 整数
        ]
        
        for pattern in number_patterns:
            if re.search(pattern, para.text):
                return True
        
        # 检查数据相关词汇
        data_keywords = ["数据", "统计", "调查", "研究", "分析", "报告", "结果", "显示", "表明"]
        if any(keyword in para.text for keyword in data_keywords):
            return True
        
        return False
    
    @staticmethod
    def has_contrast_comparison(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否有对比/反差"""
        contrast_keywords = ["对比", "vs", "VS", "不同", "差异", "相反", "但是", "然而", "可是", "却", "而"]
        if any(keyword in para.text for keyword in contrast_keywords):
            return True
        
        # 幻灯片类型为对比
        if frame.slide_type == "comparison":
            return True
        
        # 检查对比结构
        text_lower = para.text.lower()
        if "vs" in text_lower or "versus" in text_lower:
            return True
        
        return False
    
    @staticmethod
    def has_call_to_action(frame: SlideFrame, para: SpeechParagraph) -> bool:
        """是否有行动号召"""
        action_keywords = ["行动", "建议", "应该", "需要", "立即", "现在", "一起", "让我们", "请", "务必", "赶快"]
        if any(keyword in para.text for keyword in action_keywords):
            return True
        
        # 祈使句或强烈语气
        if para.text.endswith("吧") or para.text.endswith("！") or para.text.endswith("!"):
            return True
        
        # 未来导向的语句
        future_indicators = ["将会", "未来", "明天", "接下来", "下一步", "以后"]
        if any(indicator in para.text for indicator in future_indicators):
            return True
        
        return False

# ==================== 核心计算函数 ====================

def _bool_seq(frames: List[SlideFrame], paras: List[SpeechParagraph], 
              rule_fns: List[Callable]) -> List[int]:
    """生成刺激序列"""
    if not frames or not paras:
        return []
    
    n = min(len(frames), len(paras))
    s = []
    
    for k in range(n):
        v = 0
        for fn in rule_fns:
            try:
                if fn(frames[k], paras[k]):
                    v = 1
                    break
            except Exception as e:
                logger.warning(f"规则 {fn.__name__ if hasattr(fn, '__name__') else fn} 执行失败: {e}")
                continue
        s.append(v)
    
    return s

def calculate_ohs(frames: List[SlideFrame], paras: List[SpeechParagraph], 
                  m: int, rule_fns: List[Callable], 
                  weights: Optional[List[float]] = None) -> float:
    """计算开场钩子分数"""
    if m <= 0 or not frames or not paras:
        return 0.0
    
    m = min(m, len(frames), len(paras))
    
    # 默认权重：问题陈述权重最高
    if weights is None:
        if len(rule_fns) == 7:  # 如果使用完整规则库
            weights = [0.3, 0.2, 0.15, 0.1, 0.1, 0.1, 0.05]  # 总和为1
        else:
            weights = [1.0 / max(1, len(rule_fns))] * len(rule_fns)
    
    # 归一化权重
    total_weight = sum(weights)
    if abs(total_weight - 1.0) > 0.001:
        weights = [w/total_weight for w in weights]
    
    total_score = 0.0
    rules_triggered = [0] * len(rule_fns)  # 记录每个规则触发的次数
    
    for k in range(m):
        for i, fn in enumerate(rule_fns):
            try:
                if fn(frames[k], paras[k]):
                    total_score += weights[i]
                    rules_triggered[i] += 1
                    break  # 每帧只计算一个规则（最高优先级）
            except Exception:
                continue
    
    # 记录诊断信息
    logger.debug(f"OHS诊断: 前{m}帧中规则触发情况: {rules_triggered}")
    
    return total_score

def calculate_sf(frames: List[SlideFrame], paras: List[SpeechParagraph], 
                 rule_fns: List[Callable]) -> int:
    """计算刺激频率"""
    s = _bool_seq(frames, paras, rule_fns)
    return sum(s)

def calculate_mp(frames: List[SlideFrame], paras: List[SpeechParagraph], 
                 rule_fns: List[Callable]) -> int:
    """计算最大平淡度"""
    s = _bool_seq(frames, paras, rule_fns)
    
    if not s:
        return 0
    
    max_plain = 0
    current_plain = 0
    
    for v in s:
        if v == 0:  # 平淡帧
            current_plain += 1
            max_plain = max(max_plain, current_plain)
        else:  # 刺激帧
            current_plain = 0
    
    return max_plain

def _autocorrelation(s: List[int], L: int) -> float:
    """计算自相关函数"""
    n = len(s)
    if n == 0 or L <= 0 or L >= n:
        return 0.0
    
    mean = sum(s) / float(n)
    numerator = 0.0
    denominator = 0.0
    
    for k in range(n - L):
        numerator += (s[k] - mean) * (s[k + L] - mean)
    
    for k in range(n):
        denominator += (s[k] - mean) * (s[k] - mean)
    
    if denominator == 0.0:
        return 0.0
    
    return numerator / denominator

def calculate_rr(frames: List[SlideFrame], paras: List[SpeechParagraph], 
                 rule_fns: List[Callable]) -> float:
    """计算节奏分数"""
    s = _bool_seq(frames, paras, rule_fns)
    
    if len(s) < 3:  # 太短的序列无法计算节奏
        return 0.5  # 返回中间值
    
    rho_2 = _autocorrelation(s, 2)  # 周期为2的相关性
    rho_1 = _autocorrelation(s, 1)  # 相邻相关性
    
    # 原始公式
    period_score = (rho_2 + 1.0) / 2.0  # 映射到[0,1]
    alternation_score = (1.0 - rho_1) / 2.0  # 映射到[0,1]
    
    rhythm_score = 0.5 * (period_score + alternation_score)
    
    logger.debug(f"节奏分析: rho(1)={rho_1:.3f}, rho(2)={rho_2:.3f}, 分数={rhythm_score:.3f}")
    
    return rhythm_score

def calculate_rs(frames: List[SlideFrame], paras: List[SpeechParagraph], 
                 rule_fns: List[Callable], 
                 w_sf: float = 0.4, w_mp: float = 0.3, w_rr: float = 0.3) -> float:
    """计算留存分数"""
    if not frames or not paras:
        return 0.0
    
    n = max(1, min(len(frames), len(paras)))
    
    # 计算各分量
    sf_score = calculate_sf(frames, paras, rule_fns)
    mp_score = calculate_mp(frames, paras, rule_fns)
    rr_score = calculate_rr(frames, paras, rule_fns)
    
    # 归一化处理
    sf_norm = sf_score / n  # 刺激频率归一化到[0,1]
    mp_norm = 1.0 - (mp_score / n)  # 最大平淡度归一化（越小越好）
    
    # 综合分数
    rs_score = w_sf * sf_norm + w_mp * mp_norm + w_rr * rr_score
    
    # 记录诊断信息
    logger.debug(f"RS诊断: SF={sf_score}({sf_norm:.3f}), MP={mp_score}({mp_norm:.3f}), "
                f"RR={rr_score:.3f}, 总分={rs_score:.3f}")
    
    return rs_score

def calculate_clc(knowledge_nodes: List[KnowledgeNode], 
                 edges: List[Tuple[int, int]], 
                 W: int = 3, 
                 w_lcr: float = 0.5, w_ars: float = 0.5) -> float:
    """计算认知负载控制分数"""
    if not edges or not knowledge_nodes:
        return 0.0
    
    n = len(knowledge_nodes)
    total_edges = float(len(edges))
    
    # 创建索引映射
    node_to_idx = {node.id: i for i, node in enumerate(knowledge_nodes)}
    
    acc_span = 0.0
    acc_local = 0.0
    
    for src_id, tgt_id in edges:
        if src_id in node_to_idx and tgt_id in node_to_idx:
            src_idx = node_to_idx[src_id]
            tgt_idx = node_to_idx[tgt_id]
            span = abs(src_idx - tgt_idx)
            acc_span += span
            
            if span <= W:
                acc_local += 1.0
        else:
            logger.warning(f"知识点边({src_id}, {tgt_id})引用了不存在的节点")
    
    # 计算指标
    ars = acc_span / total_edges if total_edges > 0 else 0.0
    ars_norm = ars / float(max(1, n - 1))  # 归一化到[0,1]
    lcr = acc_local / total_edges if total_edges > 0 else 0.0
    
    # CLC分数
    clc_score = (w_lcr * lcr + w_ars * (1.0 - ars_norm)) / (w_lcr + w_ars)
    
    logger.debug(f"CLC诊断: LCR={lcr:.3f}, ARS={ars:.2f}(归一化={ars_norm:.3f}), 总分={clc_score:.3f}")
    
    return clc_score

# ==================== 可靠性法则函数 ====================

def calculate_rouge_score(generated: str, reference: str, n: int = 1) -> float:
    """计算ROUGE-N分数（简化版）"""
    # 在实际应用中，应使用rouge-score库
    # 这里提供简化实现
    
    def get_ngrams(text, n):
        if not text:
            return []
        words = text.split()
        if len(words) < n:
            return []
        return [' '.join(words[i:i+n]) for i in range(len(words)-n+1)]
    
    if not generated or not reference:
        return 0.0
    
    gen_ngrams = get_ngrams(generated, n)
    ref_ngrams = get_ngrams(reference, n)
    
    if not gen_ngrams or not ref_ngrams:
        return 0.0
    
    # 计算重叠
    overlap = len(set(gen_ngrams) & set(ref_ngrams))
    precision = overlap / len(gen_ngrams) if gen_ngrams else 0.0
    recall = overlap / len(ref_ngrams) if ref_ngrams else 0.0
    
    # F1分数
    if precision + recall == 0:
        return 0.0
    
    f1 = 2 * precision * recall / (precision + recall)
    return f1

def calculate_text_fidelity(frames: List[SlideFrame], paras: List[SpeechParagraph],
                           reference_frames: List[SlideFrame], 
                           reference_paras: List[SpeechParagraph]) -> Dict[str, float]:
    """计算文本忠诚度"""
    if not frames or not paras or not reference_frames or not reference_paras:
        return {"overall": 0.0, "rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}
    
    n = min(len(frames), len(paras), len(reference_frames), len(reference_paras))
    
    rouge1_scores = []
    rouge2_scores = []
    rougeL_scores = []
    
    for i in range(n):
        # 幻灯片内容忠诚度
        frame_score1 = calculate_rouge_score(frames[i].content, reference_frames[i].content, 1)
        frame_score2 = calculate_rouge_score(frames[i].content, reference_frames[i].content, 2)
        
        # 演讲稿忠诚度
        para_score1 = calculate_rouge_score(paras[i].text, reference_paras[i].text, 1)
        para_score2 = calculate_rouge_score(paras[i].text, reference_paras[i].text, 2)
        
        # ROUGE-L简化实现（使用最长公共子序列的比例）
        def lcs_length(a, b):
            """计算最长公共子序列长度"""
            m, n = len(a), len(b)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if a[i-1] == b[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
            return dp[m][n]
        
        # 对幻灯片内容
        frame_words = frames[i].content.split()
        ref_frame_words = reference_frames[i].content.split()
        frame_lcs = lcs_length(frame_words, ref_frame_words)
        frame_scoreL = frame_lcs / max(len(ref_frame_words), 1) if ref_frame_words else 0.0
        
        # 对演讲稿
        para_words = paras[i].text.split()
        ref_para_words = reference_paras[i].text.split()
        para_lcs = lcs_length(para_words, ref_para_words)
        para_scoreL = para_lcs / max(len(ref_para_words), 1) if ref_para_words else 0.0
        
        rouge1_scores.append((frame_score1 + para_score1) / 2)
        rouge2_scores.append((frame_score2 + para_score2) / 2)
        rougeL_scores.append((frame_scoreL + para_scoreL) / 2)
    
    # 平均分数
    avg_rouge1 = sum(rouge1_scores) / n if rouge1_scores else 0.0
    avg_rouge2 = sum(rouge2_scores) / n if rouge2_scores else 0.0
    avg_rougeL = sum(rougeL_scores) / n if rougeL_scores else 0.0
    
    # 综合分数（权重可调）
    overall_score = 0.4 * avg_rouge1 + 0.3 * avg_rouge2 + 0.3 * avg_rougeL
    
    return {
        "overall": overall_score,
        "rouge1": avg_rouge1,
        "rouge2": avg_rouge2,
        "rougeL": avg_rougeL
    }

def calculate_visual_fidelity(frames: List[SlideFrame], 
                             reference_frames: List[SlideFrame]) -> float:
    """计算视觉忠诚度（简化版）"""
    if not frames or not reference_frames:
        return 0.0
    
    n = min(len(frames), len(reference_frames))
    
    matches = 0.0
    for i in range(n):
        # 简单比较：是否有图像、类型是否匹配
        if frames[i].has_image == reference_frames[i].has_image:
            matches += 0.3
        
        if frames[i].slide_type == reference_frames[i].slide_type:
            matches += 0.4
        
        # 内容关键词匹配
        frame_words = frames[i].content.split()[:10]
        ref_words = reference_frames[i].content.split()[:10]
        
        if frame_words and ref_words:
            common_words = set(frame_words) & set(ref_words)
            keyword_match = len(common_words) / max(len(set(ref_words)), 1)
            matches += 0.3 * keyword_match
    
    return matches / n if n > 0 else 0.0

# ==================== 评估器主类 ====================

class PresentationEvaluator:
    """演讲材料综合评估器"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 加载规则
        self.rule_fns = self._load_rules()
        self.rule_weights = self._load_weights()
        
        # 评估历史
        self.history = []
    
    def _load_rules(self) -> List[Callable]:
        """加载规则函数"""
        rule_library = RuleLibrary()
        
        # 默认规则集
        default_rules = [
            rule_library.has_problem_statement,
            rule_library.has_personal_story,
            rule_library.has_visual_impact,
            rule_library.has_question_interaction,
            rule_library.has_data_impact,
            rule_library.has_contrast_comparison,
            rule_library.has_call_to_action
        ]
        
        # 可根据配置选择规则子集
        if "selected_rules" in self.config:
            selected = self.config["selected_rules"]
            return [rule for rule in default_rules if rule.__name__ in selected]
        
        return default_rules
    
    def _load_weights(self) -> List[float]:
        """加载规则权重"""
        if "rule_weights" in self.config:
            return self.config["rule_weights"]
        
        # 默认权重
        return [0.25, 0.2, 0.15, 0.12, 0.1, 0.1, 0.08]
    
    def evaluate(self, 
                 frames: List[SlideFrame], 
                 paras: List[SpeechParagraph],
                 reference_frames: Optional[List[SlideFrame]] = None,
                 reference_paras: Optional[List[SpeechParagraph]] = None,
                 knowledge_graph: Optional[Tuple[List[KnowledgeNode], List[Tuple[int, int]]]] = None) -> Dict:
        """综合评估演讲材料"""
        
        results = {
            "attractiveness": {},
            "reliability": {},
            "diagnosis": {},
            "suggestions": []
        }
        
        # ===== 吸引力评估 =====
        logger.info("开始吸引力评估...")
        
        # OHS (开场钩子分数)
        ohs_score = calculate_ohs(frames, paras, m=3, rule_fns=self.rule_fns, weights=self.rule_weights)
        results["attractiveness"]["ohs"] = ohs_score
        
        # RS (留存分数)
        rs_score = calculate_rs(frames, paras, self.rule_fns)
        results["attractiveness"]["rs"] = rs_score
        
        # 分量分数
        sf_score = calculate_sf(frames, paras, self.rule_fns)
        mp_score = calculate_mp(frames, paras, self.rule_fns)
        rr_score = calculate_rr(frames, paras, self.rule_fns)
        
        results["attractiveness"]["sf"] = sf_score
        results["attractiveness"]["mp"] = mp_score
        results["attractiveness"]["rr"] = rr_score
        
        # CLC (认知负载控制分数)
        if knowledge_graph:
            nodes, edges = knowledge_graph
            clc_score = calculate_clc(nodes, edges)
            results["attractiveness"]["clc"] = clc_score
        
        # ===== 可靠性评估 =====
        if reference_frames and reference_paras:
            logger.info("开始可靠性评估...")
            
            # 文本忠诚度
            text_fidelity = calculate_text_fidelity(frames, paras, reference_frames, reference_paras)
            results["reliability"]["text_fidelity"] = text_fidelity
            
            # 视觉忠诚度
            visual_fidelity = calculate_visual_fidelity(frames, reference_frames)
            results["reliability"]["visual_fidelity"] = visual_fidelity
        
        # ===== 诊断分析 =====
        results["diagnosis"] = self._diagnose_problems(frames, paras)
        
        # ===== 生成建议 =====
        results["suggestions"] = self._generate_suggestions(results)
        
        # 保存历史
        self.history.append({
            "timestamp": datetime.now(),
            "results": results
        })
        
        return results
    
    def _diagnose_problems(self, frames: List[SlideFrame], 
                          paras: List[SpeechParagraph]) -> Dict:
        """诊断具体问题"""
        bool_seq = _bool_seq(frames, paras, self.rule_fns)
        
        if not bool_seq:
            return {"error": "无有效数据"}
        
        n = len(bool_seq)
        
        # 找到所有平淡段落
        plain_segments = []
        current_start = None
        current_length = 0
        
        for i, v in enumerate(bool_seq):
            if v == 0:  # 平淡
                if current_start is None:
                    current_start = i
                    current_length = 1
                else:
                    current_length += 1
            else:  # 刺激
                if current_start is not None and current_length >= 2:
                    plain_segments.append((current_start, current_length))
                current_start = None
                current_length = 0
        
        # 处理最后一个段落
        if current_start is not None and current_length >= 2:
            plain_segments.append((current_start, current_length))
        
        # 找到最长的平淡段落
        max_plain = max(plain_segments, key=lambda x: x[1]) if plain_segments else (0, 0)
        
        # 刺激分布
        stimulus_indices = [i for i, v in enumerate(bool_seq) if v == 1]
        
        # 计算刺激间隔
        stimulus_intervals = []
        if len(stimulus_indices) > 1:
            for i in range(1, len(stimulus_indices)):
                stimulus_intervals.append(stimulus_indices[i] - stimulus_indices[i-1])
        
        return {
            "total_slides": n,
            "stimulus_count": sum(bool_seq),
            "stimulus_ratio": sum(bool_seq) / n if n > 0 else 0,
            "plain_segments": plain_segments,
            "max_plain_segment": max_plain,
            "stimulus_indices": stimulus_indices,
            "stimulus_intervals": stimulus_intervals,
            "bool_sequence": bool_seq
        }
    
    def _generate_suggestions(self, results: Dict) -> List[str]:
        """根据评估结果生成改进建议"""
        suggestions = []
        
        # OHS相关建议
        ohs_score = results["attractiveness"].get("ohs", 0)
        if ohs_score < 0.6:
            suggestions.append(f"开场吸引力不足(得分:{ohs_score:.2f}/1.0)。建议前3页中加入：1)明确的问题陈述 2)个人相关故事 3)强烈对比")
        
        # RS相关建议
        rs_score = results["attractiveness"].get("rs", 0)
        mp_score = results["attractiveness"].get("mp", 0)
        
        if rs_score < 0.5:
            suggestions.append(f"整体留存率偏低(得分:{rs_score:.2f}/1.0)。建议增加刺激点频率，每3-5页加入一个亮点")
        
        if mp_score >= 3:
            diagnosis = results["diagnosis"]
            max_plain = diagnosis.get("max_plain_segment", (0, 0))
            suggestions.append(f"存在连续{mp_score}页平淡内容(从第{max_plain[0]+1}页开始)。建议在此处加入互动、案例或视觉冲击")
        
        # CLC相关建议
        clc_score = results["attractiveness"].get("clc", 1.0)
        if clc_score < 0.6:
            suggestions.append("知识点关联跨度较大，听众理解成本高。建议增加知识点间的回顾与呼应")
        
        # 可靠性建议
        if "reliability" in results:
            text_fid = results["reliability"].get("text_fidelity", {}).get("overall", 1.0)
            if text_fid < 0.7:
                suggestions.append(f"文本忠诚度偏低({text_fid:.2f}/1.0)，部分内容可能偏离原始材料。建议检查关键信息的准确性")
        
        # 通用建议
        if not suggestions:  # 如果分数都很好
            suggestions.append("当前材料质量良好，保持现有结构。可考虑：1)增加一个令人印象深刻的结尾 2)加入一个互动问答环节")
        elif len(suggestions) < 3:
            suggestions.append("此外，建议检查演讲的时长分配，确保重点内容有足够的时间展开。")
        
        return suggestions
    
    def generate_report(self, results: Dict, format: str = "text") -> str:
        """生成评估报告"""
        report_lines = []
        
        report_lines.append("=" * 60)
        report_lines.append("演讲材料评估报告")
        report_lines.append("=" * 60)
        
        # 吸引力部分
        report_lines.append("\n【吸引力评估】")
        att = results["attractiveness"]
        report_lines.append(f"开场钩子分数 (OHS): {att.get('ohs', 0):.3f}/1.0")
        report_lines.append(f"留存分数 (RS): {att.get('rs', 0):.3f}/1.0")
        report_lines.append(f"  刺激频率 (SF): {att.get('sf', 0)}次")
        report_lines.append(f"  最大平淡度 (MP): {att.get('mp', 0)}页")
        report_lines.append(f"  节奏分数 (RR): {att.get('rr', 0):.3f}/1.0")
        if 'clc' in att:
            report_lines.append(f"认知负载控制 (CLC): {att['clc']:.3f}/1.0")
        
        # 可靠性部分
        if "reliability" in results:
            report_lines.append("\n【可靠性评估】")
            rel = results["reliability"]
            if "text_fidelity" in rel:
                tf = rel["text_fidelity"]
                report_lines.append(f"文本忠诚度: {tf.get('overall', 0):.3f}/1.0")
                report_lines.append(f"  ROUGE-1: {tf.get('rouge1', 0):.3f}")
                report_lines.append(f"  ROUGE-2: {tf.get('rouge2', 0):.3f}")
                report_lines.append(f"  ROUGE-L: {tf.get('rougeL', 0):.3f}")
            
            if "visual_fidelity" in rel:
                report_lines.append(f"视觉忠诚度: {rel['visual_fidelity']:.3f}/1.0")
        
        # 诊断部分
        report_lines.append("\n【诊断分析】")
        diag = results["diagnosis"]
        report_lines.append(f"总页数: {diag.get('total_slides', 0)}")
        report_lines.append(f"刺激点数量: {diag.get('stimulus_count', 0)}")
        report_lines.append(f"刺激比例: {diag.get('stimulus_ratio', 0):.1%}")
        
        plain_segs = diag.get('plain_segments', [])
        if plain_segs:
            report_lines.append(f"平淡段落: {len(plain_segs)}处")
            for start, length in plain_segs[:3]:  # 显示最多3处
                report_lines.append(f"  - 第{start+1}页开始，连续{length}页")
        
        stimulus_intervals = diag.get('stimulus_intervals', [])
        if stimulus_intervals:
            avg_interval = sum(stimulus_intervals) / len(stimulus_intervals)
            report_lines.append(f"刺激点平均间隔: {avg_interval:.1f}页")
        
        # 建议部分
        report_lines.append("\n【改进建议】")
        suggestions = results.get("suggestions", [])
        if suggestions:
            for i, suggestion in enumerate(suggestions, 1):
                report_lines.append(f"{i}. {suggestion}")
        else:
            report_lines.append("无具体建议，材料质量良好。")
        
        report_lines.append("\n" + "=" * 60)
        
        if format == "markdown":
            return self._format_markdown(report_lines)
        
        return "\n".join(report_lines)
    
    def _format_markdown(self, lines: List[str]) -> str:
        """格式化为Markdown"""
        md_lines = []
        for line in lines:
            if line.startswith("【"):
                md_lines.append(f"## {line[1:-1]}")
            elif line.startswith("  -"):
                md_lines.append(line)
            elif line.startswith("  "):
                md_lines.append(line)
            elif ":" in line and not line.startswith("="):
                parts = line.split(":", 1)
                md_lines.append(f"**{parts[0]}**:{parts[1]}")
            elif not line.startswith("="):
                md_lines.append(line)
        return "\n".join(md_lines)

# ==================== 使用示例 ====================

def create_example_presentation():
    """创建示例演讲材料"""
    
    # 幻灯片帧
    frames = [
        SlideFrame(
            content="为什么你的演讲总是让人犯困？",
            slide_type="title",
            visual_complexity=0.2,
            contrast_ratio=0.8
        ),
        SlideFrame(
            content="数据揭示：85%的商务演讲无法有效传达核心信息",
            slide_type="bullet",
            has_bullet=True,
            bullet_count=1,
            visual_complexity=0.3
        ),
        SlideFrame(
            content="传统PPT vs 短视频式PPT",
            slide_type="comparison",
            has_image=True,
            visual_complexity=0.6,
            contrast_ratio=0.7
        ),
        SlideFrame(
            content="吸引力法则三大指标",
            slide_type="title",
            visual_complexity=0.3
        ),
        SlideFrame(
            content="1. 开场钩子(OHS) - 前3秒抓住注意力\n2. 留存分数(RS) - 保持观众关注\n3. 认知负载(CLC) - 控制信息密度",
            slide_type="bullet",
            has_bullet=True,
            bullet_count=3,
            visual_complexity=0.5
        ),
        SlideFrame(
            content="节奏分数(RR)的计算原理",
            slide_type="bullet",
            has_bullet=True,
            visual_complexity=0.4
        ),
        SlideFrame(
            content="现在就开始优化你的演讲吧！",
            slide_type="quote",
            visual_complexity=0.2,
            contrast_ratio=0.9
        )
    ]
    
    # 演讲稿段落
    paras = [
        SpeechParagraph(
            text="大家好，今天我们来聊聊一个让人头疼的问题：为什么精心准备的演讲，听众却在刷手机？",
            duration_sec=10
        ),
        SpeechParagraph(
            text="根据我们最新的调研数据，85%的商务演讲都无法有效传达核心信息，这意味着大量的沟通成本被浪费了。",
            duration_sec=12
        ),
        SpeechParagraph(
            text="左边是传统的信息过载式PPT，右边是借鉴短视频思路的新式PPT。去年我在谷歌演讲时，就采用了这种对比方式，效果提升了40%。",
            duration_sec=15
        ),
        SpeechParagraph(
            text="那么，如何科学地评估和提升演讲吸引力呢？我们提出了三大核心指标。",
            duration_sec=8
        ),
        SpeechParagraph(
            text="首先是开场钩子，就像短视频的前3秒，必须抓住注意力。然后是留存分数，衡量你能保持观众关注多久。最后是认知负载控制，确保信息密度适中。",
            duration_sec=18
        ),
        SpeechParagraph(
            text="节奏分数的计算基于刺激点的周期性分布。理想的演讲应该像心跳一样，有规律地起伏，避免长时间平淡。",
            duration_sec=14
        ),
        SpeechParagraph(
            text="现在就用这些指标优化你的下一次演讲吧！让我们一起告别无聊的演示。",
            duration_sec=10
        )
    ]
    
    # 参考材料（简化）
    reference_frames = [SlideFrame(content=f.content, slide_type=f.slide_type, 
                                  has_image=f.has_image, has_bullet=f.has_bullet) 
                       for f in frames]
    reference_paras = [SpeechParagraph(text=p.text, duration_sec=p.duration_sec) 
                      for p in paras]
    
    # 知识点图谱（简化）
    knowledge_nodes = [
        KnowledgeNode(id=1, content="演讲问题现状", frame_idx=0, para_idx=0),
        KnowledgeNode(id=2, content="数据支撑", frame_idx=1, para_idx=1),
        KnowledgeNode(id=3, content="解决方案对比", frame_idx=2, para_idx=2),
        KnowledgeNode(id=4, content="吸引力法则", frame_idx=3, para_idx=3),
        KnowledgeNode(id=5, content="三大指标", frame_idx=4, para_idx=4),
        KnowledgeNode(id=6, content="节奏原理", frame_idx=5, para_idx=5),
        KnowledgeNode(id=7, content="行动号召", frame_idx=6, para_idx=6)
    ]
    
    edges = [
        (4, 1),  # 吸引力法则 -> 演讲问题现状
        (4, 2),  # 吸引力法则 -> 数据支撑
        (5, 4),  # 三大指标 -> 吸引力法则
        (6, 5),  # 节奏原理 -> 三大指标
        (7, 4)   # 行动号召 -> 吸引力法则
    ]
    
    return frames, paras, reference_frames, reference_paras, (knowledge_nodes, edges)

def main():
    """主函数示例"""
    print("演讲材料评估系统示例")
    print("-" * 40)
    
    # 创建评估器
    evaluator = PresentationEvaluator()
    
    # 创建示例数据
    frames, paras, ref_frames, ref_paras, knowledge_graph = create_example_presentation()
    
    # 执行评估
    results = evaluator.evaluate(
        frames=frames,
        paras=paras,
        reference_frames=ref_frames,
        reference_paras=ref_paras,
        knowledge_graph=knowledge_graph
    )
    
    # 生成报告
    report = evaluator.generate_report(results)
    print(report)
    
    # 保存结果（可选）
    import json
    with open("evaluation_results.json", "w", encoding="utf-8") as f:
        # 自定义序列化函数
        def default_serializer(obj):
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            elif isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        
        json.dump(results, f, ensure_ascii=False, indent=2, default=default_serializer)
    
    print("\n结果已保存至 evaluation_results.json")
    
    # 打印规则触发情况
    print("\n规则触发测试:")
    rule_lib = RuleLibrary()
    for i, (frame, para) in enumerate(zip(frames, paras)):
        print(f"\n第{i+1}页:")
        for rule_name in ["has_problem_statement", "has_personal_story", "has_visual_impact", 
                         "has_question_interaction", "has_data_impact", "has_contrast_comparison", 
                         "has_call_to_action"]:
            rule_func = getattr(rule_lib, rule_name)
            if rule_func(frame, para):
                print(f"  ✓ {rule_name}")

if __name__ == "__main__":
    main()