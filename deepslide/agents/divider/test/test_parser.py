# test_latex_parser.py
"""
测试 LaTeX 解析器
运行: python test_latex_parser.py
"""

from latex_parser import LatexParser

# 测试用的 LaTeX 文本（包含典型场景）
TEST_LATEX = r"""
\documentclass{article}
\usepackage{amsmath}

% 这是文档前导注释
\title{机器学习基础}
\author{张三}

\begin{document}

\section{Introduction} % 引言部分
This is the introduction. 
We discuss \textbf{fundamental concepts} and $E = mc^2$.

\section[Related Work]{Related Work (Prior Studies)}
\label{sec:related}
Previous work includes:
\begin{itemize}
    \item Study A \cite{ref1} % 重要参考
    \item Study B with formula: $\int_0^\infty x^2 dx$
\end{itemize}

\subsection{Deep Learning Advances}
Recent breakthroughs in deep learning:
\begin{equation}
    y = \sigma(Wx + b)
\end{equation}
% 这是行内注释
This shows neural network activation.

\section{Conclusion and Future Work}
\textit{Summary}: We presented novel methods.
Future directions:
\begin{enumerate}
    \item Improve scalability
    \item Extend to video data
\end{enumerate}

% 文档结束注释
\end{document}
"""

def print_section(section: dict, index: int):
    """格式化打印章节信息"""
    print(f"\n{'='*50}")
    print(f"SECTION {index+1}: Level {section['level']} - '{section['title']}'")
    print(f"Raw Title: '{section['title_raw']}'")
    print(f"Command: '{section['command']}'")
    print(f"Position: start={section['start_char']}, end={section['end_char']} (length={section['end_char']-section['start_char']})")
    print("-"*50)
    print("Content (first 100 chars):")
    print(section['content'][:100] + ("..." if len(section['content']) > 100 else ""))
    print(f"Content length: {len(section['content'])} chars")

def test_parser():
    """测试解析器功能"""
    print("🔍 测试 LaTeX 解析器")
    print("="*60)
    
    parser = LatexParser()
    
    # 解析文档
    sections = parser.extract_sections(TEST_LATEX)
    
    # 打印统计信息
    print(f"\n📊 文档分析结果:")
    print(f"总章节数: {len(sections)}")
    print(f"层级分布: {parser.analyze_document_structure(TEST_LATEX)['level_distribution']}")
    
    # 详细打印每个章节
    for i, sec in enumerate(sections):
        print_section(sec, i)
    
    # 验证关键点（修复：避免f-string内使用反斜杠）
    print("\n✅ 关键验证:")
    if sections:
        first_sec = sections[0]
        print(f"1. 首章节位置: start={first_sec['start_char']} (应接近0)")
        print(f"2. 首章节标题: '{first_sec['title']}' (应为'Introduction')")
        has_formula = '$E = mc^2$' in first_sec['content']
        print(f"3. 首章节内容是否包含公式: {has_formula}")
        
        if len(sections) > 1:
            second_sec = sections[1]
            print(f"4. 次章节原始标题: '{second_sec['title_raw']}' (应包含'Prior Studies')")
            # 关键修复：不在f-string表达式内使用反斜杠
            has_label = '\\label' in second_sec['content']
            print(f"5. 次章节是否保留\\label: {has_label}")
    
    # 特殊测试：无章节文档
    print("\n\n🧪 测试无章节文档:")
    simple_text = "Just a simple text without any sections."
    simple_sections = parser.extract_sections(simple_text)
    print(f"无章节文档解析结果: {len(simple_sections)} 章节")
    if simple_sections:
        print(f"标题: '{simple_sections[0]['title']}', 内容长度: {len(simple_sections[0]['content'])}")

if __name__ == "__main__":
    test_parser()