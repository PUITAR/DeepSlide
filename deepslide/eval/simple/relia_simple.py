import math

# ==================== 系统稳定度 ====================
def calculate_acsr(success, attempts):
    """
    计算平均编译通过成功率
    Args:
        success: 成功次数
        attempts: 总尝试次数
    Returns:
        成功率 (0.0 - 1.0)
    """
    if attempts <= 0:
        return 0.0
    return min(1.0, max(0.0, float(success) / float(attempts)))

# ==================== 文本相似度基础函数 ====================
def _tokenize(text):
    """简单分词"""
    if not text:
        return []
    return [word for word in text.lower().split() if word]

def _rouge1(candidate, reference):
    """计算ROUGE-1召回率"""
    if not candidate or not reference:
        return 0.0
    
    cand_words = set(_tokenize(candidate))
    ref_words = set(_tokenize(reference))
    
    if not ref_words:
        return 0.0
    
    # 计算重叠
    overlap = len(cand_words & ref_words)
    return overlap / len(ref_words)

def _jaccard(candidate, reference):
    """计算Jaccard相似度"""
    if not candidate or not reference:
        return 0.0
    
    cand_words = set(_tokenize(candidate))
    ref_words = set(_tokenize(reference))
    
    if not cand_words and not ref_words:
        return 1.0
    if not cand_words or not ref_words:
        return 0.0
    
    intersection = len(cand_words & ref_words)
    union = len(cand_words | ref_words)
    
    return intersection / union

# ==================== 文本忠诚度 ====================
def calculate_textual_fidelity(frames_text, paras_text, refs_text, w_rouge=0.5, w_jaccard=0.5):
    """
    计算文本忠诚度
    Args:
        frames_text: 幻灯片文本列表
        paras_text: 演讲稿文本列表
        refs_text: 参考文本列表
        w_rouge: ROUGE权重
        w_jaccard: Jaccard权重
    Returns:
        综合文本忠诚度分数 (0.0 - 1.0)
    """
    # 检查输入
    if not frames_text or not paras_text or not refs_text:
        return 0.0
    
    n = min(len(frames_text), len(paras_text), len(refs_text))
    if n <= 0:
        return 0.0
    
    total_rouge = 0.0
    total_jaccard = 0.0
    
    for i in range(n):
        # 计算ROUGE-1
        rouge_para = _rouge1(paras_text[i], refs_text[i])
        rouge_frame = _rouge1(frames_text[i], refs_text[i])
        total_rouge += (rouge_para + rouge_frame) / 2
        
        # 计算Jaccard
        jaccard_para = _jaccard(paras_text[i], refs_text[i])
        jaccard_frame = _jaccard(frames_text[i], refs_text[i])
        total_jaccard += (jaccard_para + jaccard_frame) / 2
    
    # 平均分数
    avg_rouge = total_rouge / n
    avg_jaccard = total_jaccard / n
    
    # 加权综合
    return w_rouge * avg_rouge + w_jaccard * avg_jaccard

# ==================== 视觉忠诚度 ====================
def calculate_visual_fidelity(source_fig_count, slide_fig_count):
    """
    计算视觉忠诚度（图像保留比例）
    Args:
        source_fig_count: 源文档图像数量
        slide_fig_count: 幻灯片图像数量
    Returns:
        图像保留比例 (0.0 - 1.0)
    """
    if source_fig_count <= 0:
        return 0.0 if slide_fig_count == 0 else 1.0
    
    return min(1.0, max(0.0, float(slide_fig_count) / float(source_fig_count)))

# ==================== 综合可靠性评估 ====================
class SimpleReliabilityEvaluator:
    """简化版可靠性评估器"""
    
    def __init__(self, weights=None):
        """
        初始化评估器
        Args:
            weights: 权重配置，包含三个部分
                - text_fidelity: 文本忠诚度权重
                - visual_fidelity: 视觉忠诚度权重
                - system_stability: 系统稳定度权重
        """
        if weights is None:
            weights = {
                'text_fidelity': 0.4,
                'visual_fidelity': 0.3,
                'system_stability': 0.3
            }
        self.weights = weights
    
    def evaluate(self, 
                 frames_text=None, 
                 paras_text=None, 
                 refs_text=None,
                 source_fig_count=0,
                 slide_fig_count=0,
                 success_count=0,
                 total_attempts=0):
        """
        综合评估
        Args:
            frames_text: 幻灯片文本列表
            paras_text: 演讲稿文本列表
            refs_text: 参考文本列表
            source_fig_count: 源文档图像数量
            slide_fig_count: 幻灯片图像数量
            success_count: 成功编译次数
            total_attempts: 总编译尝试次数
        Returns:
            评估结果字典
        """
        results = {
            'scores': {},
            'overall': 0.0,
            'available_metrics': []
        }
        
        total_weight = 0.0
        overall_score = 0.0
        
        # 1. 文本忠诚度
        if frames_text is not None and paras_text is not None and refs_text is not None:
            text_score = calculate_textual_fidelity(frames_text, paras_text, refs_text)
            results['scores']['text_fidelity'] = text_score
            results['available_metrics'].append('text_fidelity')
            
            weight = self.weights.get('text_fidelity', 0.4)
            overall_score += text_score * weight
            total_weight += weight
        
        # 2. 视觉忠诚度
        if source_fig_count > 0 or slide_fig_count > 0:
            visual_score = calculate_visual_fidelity(source_fig_count, slide_fig_count)
            results['scores']['visual_fidelity'] = visual_score
            results['available_metrics'].append('visual_fidelity')
            
            weight = self.weights.get('visual_fidelity', 0.3)
            overall_score += visual_score * weight
            total_weight += weight
        
        # 3. 系统稳定度
        if total_attempts > 0:
            stability_score = calculate_acsr(success_count, total_attempts)
            results['scores']['system_stability'] = stability_score
            results['available_metrics'].append('system_stability')
            
            weight = self.weights.get('system_stability', 0.3)
            overall_score += stability_score * weight
            total_weight += weight
        
        # 计算总体分数
        if total_weight > 0:
            results['overall'] = overall_score / total_weight
        else:
            results['overall'] = 0.0
        
        return results

# ==================== 使用示例 ====================
def test_simple_evaluator():
    """测试简化版评估器"""
    print("=" * 50)
    print("简化版可靠性评估测试")
    print("=" * 50)
    
    # 创建评估器
    evaluator = SimpleReliabilityEvaluator()
    
    # 测试数据
    frames_text = [
        "演讲吸引力评估系统",
        "开场钩子分数(OHS)计算",
        "留存分数(RS)包含三个指标"
    ]
    
    paras_text = [
        "今天介绍演讲吸引力评估系统",
        "开场钩子分数衡量前几页的吸引力",
        "留存分数包含刺激频率、最大平淡度和节奏分数"
    ]
    
    refs_text = [
        "演讲材料评估系统设计",
        "开场钩子分数(OHS)计算方法",
        "留存分数(RS)由SF、MP、RR组成"
    ]
    
    source_fig_count = 5
    slide_fig_count = 3
    
    success_count = 8
    total_attempts = 10
    
    # 执行评估
    results = evaluator.evaluate(
        frames_text=frames_text,
        paras_text=paras_text,
        refs_text=refs_text,
        source_fig_count=source_fig_count,
        slide_fig_count=slide_fig_count,
        success_count=success_count,
        total_attempts=total_attempts
    )
    
    # 打印结果
    print(f"综合可靠性分数: {results['overall']:.3f}")
    print(f"可用指标: {results['available_metrics']}")
    
    print("\n详细分数:")
    for metric, score in results['scores'].items():
        print(f"  {metric}: {score:.3f}")
    
    # 测试单个函数
    print("\n" + "-" * 50)
    print("单个函数测试:")
    
    # 测试文本相似度
    text1 = "深度学习在自然语言处理中的应用"
    text2 = "自然语言处理中的深度学习模型"
    
    print(f"\n文本1: '{text1}'")
    print(f"文本2: '{text2}'")
    print(f"ROUGE-1: {_rouge1(text1, text2):.3f}")
    print(f"Jaccard: {_jaccard(text1, text2):.3f}")
    
    # 测试系统稳定度
    print(f"\n系统稳定度 (8/10): {calculate_acsr(8, 10):.3f}")
    
    # 测试视觉忠诚度
    print(f"视觉忠诚度 (3/5): {calculate_visual_fidelity(5, 3):.3f}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    test_simple_evaluator()