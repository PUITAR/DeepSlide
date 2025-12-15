Slide/Speech 评测代码使用说明

目录
- attraction.py：吸引力法则（OHS、RS=SF/MP/RR、CLC）
- reliability.py：可靠性法则（ACSR、文本忠诚度、图片忠诚度）

示例

Python

from deepslide.eval.attraction import ohs, rs, clc
from deepslide.eval.reliability import acsr, textual_fidelity, visual_fidelity

frames = ["slide a", "slide b"]
paras = ["para a", "para b"]
refs = ["ref a", "ref b"]

def r_has_question(f, p):
    return ("?" in f) or ("?" in p)

def r_has_example(f, p):
    return ("example" in f) or ("例如" in p)

ohs_score = ohs(frames, paras, 1, [r_has_question, r_has_example])
rs_score = rs(frames, paras, [r_has_question, r_has_example])
clc_score = clc(len(frames), [(0,1), (1,1)], W=3)

acsr_score = acsr(8, 10)
text_score = textual_fidelity(frames, paras, refs)
vis_score = visual_fidelity(12, 9)

