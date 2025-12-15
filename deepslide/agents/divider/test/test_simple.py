import sys
import os
import json
import logging
from pathlib import Path

# 设置项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

# 创建测试输出目录
TEST_OUTPUT_DIR = ROOT_DIR / "tests" / "output"
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(TEST_OUTPUT_DIR / "divider_tests.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("divider_test")

from divider import Divider
from semantic_splitter import SemanticSplitter


def get_test_latex_content() -> str:
    """获取测试用的LaTeX内容（内置小示例 + 真实文件备选）"""
    # 内置小示例
    builtin_example = r"""
\section{机器学习概述}
机器学习是人工智能的核心分支，使计算机能从数据中学习。本节介绍基本概念。

\subsection{监督学习}
监督学习使用带标签的数据进行训练。常见算法包括：
\begin{itemize}
    \item 线性回归
    \item 逻辑回归
    \item 支持向量机
\end{itemize}

\subsection{无监督学习}
无监督学习从无标签数据中发现模式，包括聚类($k$-means)和降维(PCA)。

\section{深度学习}
深度学习使用多层神经网络，在图像和语音识别中表现出色。

\subsection{卷积神经网络}
CNN专门用于图像处理，通过卷积层提取特征。公式：$y = \sigma(Wx + b)$

\section{应用案例}
机器学习在医疗、金融等领域有广泛应用。例如：
\begin{itemize}
    \item 医疗诊断
    \item 金融欺诈检测
    \item 推荐系统
\end{itemize}
"""
    
    # 尝试加载真实论文（如果存在）
    real_paper_path = ROOT_DIR / "tests" / "samples" / "2511.22582v1" / "MergeConstraintsSM.tex"
    if real_paper_path.exists():
        logger.info(f"使用真实论文测试: {real_paper_path.relative_to(ROOT_DIR)}")
        with open(real_paper_path, "r", encoding="utf-8") as f:
            return f.read()
    
    logger.warning(f"真实论文文件不存在，使用内置示例: {real_paper_path.relative_to(ROOT_DIR)}")
    return builtin_example


def test_planner_instructions():
    """测试Planner指令接口"""
    print("=" * 70)
    print("测试Planner指令接口")
    print("=" * 70)
    
    # 创建划分器
    divider = Divider(strategy="hybrid")
    
    # 获取测试内容
    test_latex = get_test_latex_content()
    print(f"测试LaTeX长度: {len(test_latex)} 字符\n")
    
    # 测试1：基本指令（混合策略）
    print("测试1：基本指令（混合策略）")
    instructions = {
        "target_slide_count": 8,
        "min_content_length": 50,
        "max_depth": 3,
        "focus_points": ["机器学习", "深度学习", "应用"],
        "special_requirements": "强调实际应用"
    }
    
    chapters, feedback = divider.divide(test_latex, instructions)
    
    print(f"状态: {feedback.get('status')}")
    print(f"划分方法: {feedback.get('division_method')}")
    print(f"生成章节数: {feedback.get('total_chapters')}")
    
    print("\n章节摘要（前5个）:")
    for ch_info in feedback.get("chapters_summary", [])[:5]:
        print(f"  {ch_info['index']}. [{ch_info['level']}级] {ch_info['title']}")
        print(f"      重要性: {ch_info['importance']:.2f}, 长度: {ch_info['length']}, 标签: {ch_info.get('tags', [])}")
    
    print(f"\n统计信息:")
    stats = feedback.get("statistics", {})
    print(f"  平均长度: {stats.get('avg_chapter_length', 0):.1f}")
    print(f"  层级分布: {stats.get('level_distribution', {})}")
    print(f"  重点覆盖: {stats.get('focus_points_covered', 0)}/{stats.get('focus_points_total', 0)}")
    
    # 显示警告和建议
    warnings = feedback.get("warnings", [])
    if warnings:
        print(f"\n警告 ({len(warnings)}):")
        for i, w in enumerate(warnings, 1):
            print(f"  {i}. ⚠ {w}")
    
    suggestions = feedback.get("suggestions", [])
    if suggestions:
        print(f"\n建议 ({len(suggestions)}):")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. 💡 {s}")
    
    # 保存测试1结果
    output_file1 = TEST_OUTPUT_DIR / "planner_test_1.json"
    with open(output_file1, "w", encoding="utf-8") as f:
        json.dump({
            "instructions": instructions,
            "chapters": [ch.to_dict(include_content=True) for ch in chapters],
            "feedback": feedback
        }, f, ensure_ascii=False, indent=2)
    print(f"\n测试1结果已保存到: {output_file1.relative_to(ROOT_DIR)}")
    
    # 测试2：语义划分指令
    print("\n" + "-" * 70)
    print("测试2：语义划分策略")
    
    instructions2 = {
        "division_strategy": "semantic",
        "target_slide_count": 5,
        "min_content_length": 100,
        "max_content_length": 500,
        "focus_points": ["神经网络", "应用"],
        "special_requirements": "生成简洁的章节"
    }
    
    chapters2, feedback2 = divider.divide(test_latex, instructions2)
    
    print(f"划分方法: {feedback2.get('division_method')}")
    print(f"生成章节数: {len(chapters2)}")
    
    print("\n生成的章节（前5个）:")
    for i, ch in enumerate(chapters2[:5], 1):
        print(f"  {i}. [{ch.level}级] {ch.title}")
        print(f"      内容预览: {ch.content[:80]}...")
        if ch.tags:
            print(f"      标签: {list(ch.tags)}")
        print(f"      重要性: {ch.importance:.2f}")
    
    # 保存测试2结果
    output_file2 = TEST_OUTPUT_DIR / "planner_test_2.json"
    with open(output_file2, "w", encoding="utf-8") as f:
        json.dump({
            "instructions": instructions2,
            "chapters": [ch.to_dict(include_content=True) for ch in chapters2],
            "feedback": feedback2
        }, f, ensure_ascii=False, indent=2)
    print(f"\n测试2结果已保存到: {output_file2.relative_to(ROOT_DIR)}")
    
    # 测试3：结构划分指令
    print("\n" + "-" * 70)
    print("测试3：结构划分策略")
    
    instructions3 = {
        "division_strategy": "structural",
        "target_slide_count": 10,
        "max_depth": 2,  # 只提取到section级别
        "min_content_length": 30
    }
    
    chapters3, feedback3 = divider.divide(test_latex, instructions3)
    
    print(f"划分方法: {feedback3.get('division_method')}")
    print(f"生成章节数: {len(chapters3)}")
    
    print("\n生成的章节（前5个）:")
    for i, ch in enumerate(chapters3[:5], 1):
        print(f"  {i}. [{ch.level}级] {ch.title}")
        print(f"      内容长度: {len(ch.content)}")
    
    # 保存测试3结果
    output_file3 = TEST_OUTPUT_DIR / "planner_test_3.json"
    with open(output_file3, "w", encoding="utf-8") as f:
        json.dump({
            "instructions": instructions3,
            "chapters": [ch.to_dict(include_content=True) for ch in chapters3],
            "feedback": feedback3
        }, f, ensure_ascii=False, indent=2)
    print(f"\n测试3结果已保存到: {output_file3.relative_to(ROOT_DIR)}")
    
    return chapters, feedback


def test_with_real_file(latex_file: str):
    """使用真实文件测试"""
    print("\n" + "=" * 70)
    print(f"使用真实文件测试: {Path(latex_file).name}")
    
    # 确保文件存在
    file_path = Path(latex_file)
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path.absolute()}")
        print(f"错误: 文件不存在: {file_path}")
        return None, None
    
    # 读取文件
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"文件长度: {len(content)} 字符")
    except Exception as e:
        logger.error(f"读取文件失败: {str(e)}")
        print(f"错误: 读取文件失败 - {str(e)}")
        return None, None
    
    # 创建划分器
    divider = Divider(strategy="hybrid")
    
    # Planner指令（针对学术论文）
    instructions = {
        "target_slide_count": 20,
        "min_content_length": 150,
        "max_depth": 4,
        "focus_points": ["方法", "结果", "讨论", "实验", "conclusion"],
        "special_requirements": "保持学术严谨性，区分方法和结果"
    }
    
    print(f"\nPlanner指令: {instructions}")
    
    # 执行划分
    try:
        chapters, feedback = divider.divide(content, instructions)
    except Exception as e:
        logger.exception(f"划分过程出错: {str(e)}")
        print(f"划分失败: {str(e)}")
        return None, None
    
    print(f"\n划分结果:")
    print(f"  状态: {feedback.get('status')}")
    print(f"  方法: {feedback.get('division_method')}")
    print(f"  章节数: {len(chapters)}")
    
    # 显示章节结构
    print(f"\n章节结构 (前15个):")
    for i, ch in enumerate(chapters[:15], 1):
        priority = "★" if ch.importance > 0.8 else " "
        tags = f"[{', '.join(list(ch.tags)[:2])}]" if ch.tags else ""
        print(f"  {i:2d}. {priority} [{ch.level}级] {ch.title} {tags}")
        if ch.importance > 0.8:
            print(f"        重要性: {ch.importance:.2f}, 长度: {len(ch.content)}")
    
    # 保存详细结果
    output_file = TEST_OUTPUT_DIR / f"{file_path.stem}_planner_output.json"
    
    output_data = {
        "input_file": str(file_path.relative_to(ROOT_DIR)),
        "planner_instructions": instructions,
        "feedback": feedback,
        "chapters": [ch.to_dict(include_content=True) for ch in chapters]
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到: {output_file.relative_to(ROOT_DIR)}")
    
    # 显示Divider状态
    status = divider.get_status()
    print(f"\nDivider状态:")
    print(f"  策略: {status['strategy']}")
    print(f"  总划分次数: {status['total_divisions']}")
    print(f"  语义分割器就绪: {status['semantic_splitter_ready']}")
    print(f"  最后划分时间: {status['last_division_time']}")
    
    return chapters, feedback


def test_camel_ai_compatibility():
    """测试CAMEL-AI兼容性（使用规则回退）"""
    print("\n" + "=" * 70)
    print("测试CAMEL-AI兼容性（使用规则回退）")
    print("=" * 70)
    
    # 创建CAMEL-AI分割器（实际会回退到规则）
    try:
        splitter = SemanticSplitter(strategy="camel_ai")
        print("✅ CAMEL-AI分割器初始化成功（将回退到规则分割）")
    except Exception as e:
        logger.warning(f"CAMEL-AI初始化失败，使用纯规则分割: {str(e)}")
        splitter = SemanticSplitter(strategy="rule_based")
        print("⚠ CAMEL-AI初始化失败，使用纯规则分割")
    
    test_text = """
    机器学习是人工智能的重要分支。它使计算机能够从数据中学习并做出预测，而无需显式编程。
    
    监督学习是最常见的机器学习类型。在监督学习中，算法从标记的训练数据中学习。每个训练样本都包含输入和期望的输出。常见算法包括线性回归、逻辑回归和支持向量机。
    
    无监督学习从未标记的数据中寻找模式。常见的无监督学习任务包括聚类（如k-means）和降维（如PCA）。这些技术在探索性数据分析中非常有用。
    
    深度学习是机器学习的一个子领域。它使用多层神经网络来学习数据的层次表示。深度学习在计算机视觉、自然语言处理和语音识别等领域取得了突破性进展。
    
    强化学习涉及智能体通过与环境互动来学习。智能体根据行动获得的奖励来调整其策略。强化学习在游戏AI和机器人控制中表现出色。
    
    机器学习在各个领域都有广泛应用，包括医疗诊断、金融预测、自动驾驶和推荐系统。随着数据量的增长，机器学习的重要性将继续增加。
    """
    
    params = {
        "target_chunks": 4,
        "min_chunk_size": 100,
        "max_chunk_size": 400,
        "focus_points": ["神经网络", "强化学习", "应用"],
        "emphasis_on": "key_points"
    }
    
    print(f"测试语义分割器（策略: {splitter.strategy}）")
    print(f"文本长度: {len(test_text)}")
    print(f"参数: {params}")
    
    # 执行分割
    chapters = splitter.split_text(test_text, params)
    
    print(f"\n生成的章节数: {len(chapters)}")
    for i, ch in enumerate(chapters, 1):
        print(f"  {i}. [{ch.level}级] {ch.title}")
        print(f"      内容预览: {ch.content[:100]}...")
        if ch.tags:
            print(f"      标签: {list(ch.tags)}")
        print(f"      重要性: {ch.importance:.2f}")
        print()
    
    # 保存结果
    output_file = TEST_OUTPUT_DIR / "camel_ai_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "strategy": splitter.strategy,
            "input_params": params,
            "chapters": [ch.to_dict(include_content=True) for ch in chapters]
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\nCAMEL-AI测试结果已保存到: {output_file.relative_to(ROOT_DIR)}")
    print("注意：由于环境限制，实际使用的是规则分割策略")


if __name__ == "__main__":
    # 检查DEEPSEEK_API_KEY
    if not os.getenv('DEEPSEEK_API_KEY'):
        logger.warning("DEEPSEEK_API_KEY 未设置，CAMEL-AI功能将不可用")
        print("⚠ 警告: DEEPSEEK_API_KEY 未设置，CAMEL-AI功能将不可用")
    
    print(f"项目根目录: {ROOT_DIR}")
    print(f"测试输出目录: {TEST_OUTPUT_DIR.relative_to(ROOT_DIR)}")
    
    if len(sys.argv) > 1:
        # 使用提供的文件测试
        latex_file = sys.argv[1]
        if not Path(latex_file).exists():
            print(f"错误: 文件不存在 - {latex_file}")
            sys.exit(1)
        test_with_real_file(latex_file)
    else:
        # 运行完整测试套件
        print("运行完整测试套件...")
        
        # 1. 测试Planner指令接口
        print("\n" + "="*80)
        print("1. 测试Planner指令接口")
        test_planner_instructions()
        
        # 2. 测试CAMEL-AI兼容性
        print("\n" + "="*80)
        print("2. 测试CAMEL-AI兼容性")
        # test_camel_ai_compatibility()
        
        # 3. 使用内置示例文件测试
        print("\n" + "="*80)
        print("3. 使用内置示例文件测试")
        sample_file = ROOT_DIR / "tests" / "samples" / "sample_paper.tex"
        if not sample_file.exists():
            # 创建示例文件
            sample_content = r"""
\documentclass{article}
\title{深度学习在医疗影像分析中的应用}
\author{张三, 李四}
\begin{document}
\maketitle

\section{引言}
医学影像分析是人工智能在医疗领域的重要应用。深度学习技术在X光、CT和MRI图像分析中展现出巨大潜力。本论文综述了最新进展。

\section{相关工作}
早期方法使用传统机器学习，如SVM和随机森林。近年来，卷积神经网络(CNN)成为主流。U-Net架构在医学图像分割中特别有效。

\section{方法}
\subsection{数据预处理}
我们收集了10,000张标注的X光片。数据增强包括旋转、翻转和调整对比度。

\subsection{模型架构}
使用改进的ResNet-50作为骨干网络。添加注意力机制提升关键区域的识别能力。损失函数结合交叉熵和Dice系数。

\section{实验}
\subsection{数据集}
在三个公开数据集上评估：CheXpert, MIMIC-CXR, 和本地医院数据集。

\subsection{结果}
我们的方法在准确率上达到94.5\%，比基线高3.2\%。在病灶定位任务中，IoU达到0.87。

\section{讨论}
深度学习模型在小型数据集上容易过拟合。我们通过迁移学习和正则化缓解此问题。计算资源需求仍是部署挑战。

\section{结论}
本文展示了深度学习在医疗影像分析中的有效性。未来工作将探索联邦学习解决数据隐私问题，并开发更轻量级模型用于移动设备。
\end{document}
"""
            sample_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sample_file, "w", encoding="utf-8") as f:
                f.write(sample_content)
            print(f"创建示例文件: {sample_file.relative_to(ROOT_DIR)}")
        
        test_with_real_file(str(sample_file))
    
    print("\n" + "="*80)
    print("所有测试完成！结果保存在:")
    print(f"  {TEST_OUTPUT_DIR.relative_to(ROOT_DIR)}")
    print("="*80)