from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class TemplateRequirements:
    """Hard checks to ensure narrative structures are genuinely different."""
    # First node role must be one of these (enforces different openings).
    first_roles: List[str]
    # Minimal counts for specific roles (duplicates allowed).
    role_min_counts: Dict[str, int]
    # Ordering constraints: first occurrence of A must be before first occurrence of B.
    order_constraints: List[Tuple[str, str]]


@dataclass(frozen=True)
class NarrativeTemplate:
    """A template that enforces a genuinely different narrative structure."""
    template_id: str
    title_cn: str
    one_liner: str
    # Allowed role names (model should use these EXACT role tokens; duplicates allowed).
    roles: List[str]
    # Hard constraints / tips shown to the model.
    constraints: List[str]
    # Suggested edge relation language.
    edge_hints: List[str]
    # Programmatic requirements enforced by validator.
    requirements: TemplateRequirements

    def prompt_block(self) -> str:
        roles_txt = ", ".join(self.roles + ["Extra"])
        cons_txt = "\n".join([f"- {c}" for c in self.constraints])
        edge_txt = "\n".join([f"- {e}" for e in self.edge_hints])
        # Keep requirements concise in prompt (full checks happen in code).
        req_txt = "\n".join(
            [f"- first_roles: {', '.join(self.requirements.first_roles)}"]
            + [f"- min({k}) >= {v}" for k, v in self.requirements.role_min_counts.items()]
            + [f"- order: {a} before {b}" for a, b in self.requirements.order_constraints]
        )
        return (
            f"模板ID: {self.template_id}\n"
            f"模板名称: {self.title_cn}\n"
            f"一句话目的: {self.one_liner}\n"
            f"允许的角色(role)取值(可重复，必要时可用 Extra): {roles_txt}\n"
            f"约束(constraints):\n{cons_txt}\n"
            f"逻辑边建议(edge_hints):\n{edge_txt}\n"
            f"结构要求(requirements):\n{req_txt}\n"
        )


TEMPLATES: Dict[str, NarrativeTemplate] = {
    "postmortem": NarrativeTemplate(
        template_id="postmortem",
        title_cn="事故复盘式（Postmortem）",
        one_liner="像线上事故复盘一样讲清楚：影响—时间线—根因—修复—行动项。",
        roles=["Summary", "Impact", "Timeline", "RootCause", "Fix", "ActionItems"],
        constraints=[
            "必须包含清晰时间线（Timeline）。",
            "RootCause 必须解释 Impact/Timeline 中的关键现象。",
            "结尾必须给出 ActionItems（可执行改进/经验教训）。",
        ],
        edge_hints=["因果（导致/引发）", "证据支持（由…可知）", "修复针对（为了解决…）", "复盘总结（因此我们学到…）"],
        requirements=TemplateRequirements(
            first_roles=["Summary", "Impact"],
            role_min_counts={"Timeline": 1, "RootCause": 1, "Fix": 1, "ActionItems": 1},
            order_constraints=[("Impact", "RootCause"), ("RootCause", "Fix"), ("Fix", "ActionItems")],
        ),
    ),

    "in_medias_res": NarrativeTemplate(
        template_id="in_medias_res",
        title_cn="悬疑倒叙式（In medias res）",
        one_liner="先抛最亮眼结果/异常，再倒回去逐步揭示原因。",
        roles=["Hook", "MysteryQuestion", "FlashbackContext", "Clue", "Reveal", "ReturnToHook"],
        constraints=[
            "开头必须是 Hook（最抓人的结果/异常/反常识点，来自原文）。",
            "至少给出 2 个 Clue（逐步揭示）。",
            "结尾 ReturnToHook 回扣并解释 Hook。",
        ],
        edge_hints=["悬念推动（这引出一个问题…）", "线索递进（进一步发现…）", "揭示（关键在于…）", "回扣（回到开头…）"],
        requirements=TemplateRequirements(
            first_roles=["Hook"],
            role_min_counts={"Clue": 2, "Reveal": 1, "ReturnToHook": 1},
            order_constraints=[("Hook", "Reveal"), ("Reveal", "ReturnToHook")],
        ),
    ),

    "pyramid_bluf": NarrativeTemplate(
        template_id="pyramid_bluf",
        title_cn="结论先行式（Pyramid / BLUF）",
        one_liner="先给结论/主张，再用多个理由与证据支撑。",
        roles=["BottomLine", "Reason", "Evidence", "Caveats"],
        constraints=[
            "第一节点必须 BottomLine（一句话结论）。",
            "至少 2 个 Reason（并列理由）。",
            "Evidence 必须支撑前面的 Reason。",
            "最后必须 Caveats（边界/局限/代价）。",
        ],
        edge_hints=["总分（结论由…支撑）", "并列（此外/同时）", "证据（实验表明）", "边界（在…情况下不成立）"],
        requirements=TemplateRequirements(
            first_roles=["BottomLine"],
            role_min_counts={"Reason": 2, "Evidence": 1, "Caveats": 1},
            order_constraints=[("BottomLine", "Reason"), ("Reason", "Evidence"), ("Evidence", "Caveats")],
        ),
    ),

    "imrad": NarrativeTemplate(
        template_id="imrad",
        title_cn="科学实验式（IMRaD）",
        one_liner="按科研验证流程讲：问题/假设—方法—结果—讨论与意义。",
        roles=["Introduction", "Hypothesis", "Methods", "Results", "Discussion", "Implications"],
        constraints=[
            "必须出现可验证的 Hypothesis。",
            "Results 至少包含 1-2 个关键观察点（来自原文）。",
            "Discussion 必须解释‘为什么会这样’，不只是复述结果。",
        ],
        edge_hints=["提出（我们假设…）", "验证（我们用…方法测试）", "结果（观察到…）", "解释（原因可能是…）"],
        requirements=TemplateRequirements(
            first_roles=["Introduction"],
            role_min_counts={"Hypothesis": 1, "Methods": 1, "Results": 1, "Discussion": 1},
            order_constraints=[("Hypothesis", "Methods"), ("Methods", "Results"), ("Results", "Discussion")],
        ),
    ),

    "faq_defense": NarrativeTemplate(
        template_id="faq_defense",
        title_cn="质询答辩式（FAQ / Defense）",
        one_liner="每个节点回答一个尖锐问题，结构由听众疑问驱动。",
        roles=["Q", "A", "Risks"],
        constraints=[
            "至少 3 轮 Q/A（Q 与 A 交替）。",
            "问题要尖锐（为什么现有不行？凭什么你行？代价是什么？）。",
            "最后必须 Risks（风险/边界/代价）。",
        ],
        edge_hints=["质询（听众会问…）", "回应（关键在于…）", "举证（例如…）", "让步（代价是…）"],
        requirements=TemplateRequirements(
            first_roles=["Q"],
            role_min_counts={"Q": 3, "A": 3, "Risks": 1},
            order_constraints=[("Q", "A")],
        ),
    ),

    "myth_fact": NarrativeTemplate(
        template_id="myth_fact",
        title_cn="辟谣纠偏式（Myth → Fact）",
        one_liner="先指出常见误解，再用证据推翻，最后给出正确框架与启示。",
        roles=["Myth", "WhyBelieved", "CounterEvidence", "CorrectModel", "Implication", "Takeaway"],
        constraints=[
            "至少 2 个 Myth，且各自要有 CounterEvidence。",
            "CounterEvidence 必须来自原文（paper 节点+证据）。",
            "CorrectModel/Implication 给出‘更正确的理解与做法’。",
        ],
        edge_hints=["误解（常见但不对）", "证伪（证据显示…）", "替代解释（更合理的是…）", "启示（因此我们应该…）"],
        requirements=TemplateRequirements(
            first_roles=["Myth"],
            role_min_counts={"Myth": 2, "CounterEvidence": 2, "CorrectModel": 1, "Takeaway": 1},
            order_constraints=[("Myth", "CounterEvidence"), ("CounterEvidence", "CorrectModel"), ("CorrectModel", "Takeaway")],
        ),
    ),

    "heros_journey": NarrativeTemplate(
        template_id="heros_journey",
        title_cn="英雄之旅式（Hero’s Journey）",
        one_liner="把推进讲成旅程：目标—试炼—误入歧途/两难—突破—成果。",
        roles=["Call", "Trials", "Ordeal", "FalseLead", "Breakthrough", "Return", "Reward"],
        constraints=[
            "必须出现 Trials/Ordeal（障碍/两难）。",
            "必须出现 FalseLead（一次错误直觉/无效尝试/被排除路线）。"
            "注意：FalseLead 若原文没写，必须标为 bridge/rhetorical，不能冒充 paper 事实。",
            "Breakthrough 必须对应原文的关键方法/洞见。",
        ],
        edge_hints=["遭遇障碍（然而…）", "试错/排除（这条路不行，因为…）", "突破（关键发现…）", "回报（因此带来…）"],
        requirements=TemplateRequirements(
            first_roles=["Call"],
            role_min_counts={"Trials": 1, "Ordeal": 1, "FalseLead": 1, "Breakthrough": 1, "Reward": 1},
            order_constraints=[("Trials", "FalseLead"), ("FalseLead", "Breakthrough"), ("Breakthrough", "Reward")],
        ),
    ),

    "monroe": NarrativeTemplate(
        template_id="monroe",
        title_cn="强说服动员式（Monroe）",
        one_liner="抓注意—制造需求—给方案—描绘未来—号召行动。",
        roles=["Attention", "Need", "Satisfaction", "Visualization", "Action"],
        constraints=[
            "Attention 必须足够抓人（反常识/痛点/惊人对比），但不能编造论文结论。",
            "Visualization 必须具体（采用 vs 不采用的后果对比），且不能冒充 paper 实验结论。",
            "Action 明确下一步请求/建议。",
        ],
        edge_hints=["吸引（想象一下…）", "痛点（目前的问题是…）", "解决（我们提出…）", "对比（如果…那么…）", "号召（接下来我们需要…）"],
        requirements=TemplateRequirements(
            first_roles=["Attention"],
            role_min_counts={"Need": 1, "Satisfaction": 1, "Visualization": 1, "Action": 1},
            order_constraints=[("Need", "Satisfaction"), ("Satisfaction", "Visualization"), ("Visualization", "Action")],
        ),
    ),

    "case_study": NarrativeTemplate(
        template_id="case_study",
        title_cn="案例研究式（Case Study）",
        one_liner="用一个贯穿案例讲：场景—问题—目标—用户流程—方案—结果—启示。",
        roles=["CaseBackground", "CaseProblem", "Objectives", "UserFlow", "Solution", "Results", "Lessons"],
        constraints=[
            "必须有 UserFlow：用‘一次具体任务流程’串起来（Input→检索→输出/反馈），不要退化成论文大纲换皮。",
            "Results 只能引用原文存在的结果/对比（paper+evidence）。",
            "Lessons 提炼可迁移的经验（bridge/rhetorical 可用）。",
        ],
        edge_hints=["场景引入（在…情况下）", "问题定位（导致…）", "流程推进（首先…然后…最后…）", "效果（结果显示…）", "迁移（这意味着…）"],
        requirements=TemplateRequirements(
            first_roles=["CaseBackground"],
            role_min_counts={"UserFlow": 1, "Solution": 1, "Results": 1, "Lessons": 1},
            order_constraints=[("Objectives", "UserFlow"), ("UserFlow", "Solution"), ("Solution", "Results")],
        ),
    ),

    "hypothesis_elimination": NarrativeTemplate(
        template_id="hypothesis_elimination",
        title_cn="侦探破案式（Hypothesis Elimination）",
        one_liner="提出多个假设并逐个验证排除，锁定根因与修复。",
        roles=["Symptom", "Hypothesis", "Test", "Elimination", "Culprit", "Fix"],
        constraints=[
            "至少 2 个 Hypothesis + 对应的 Test。",
            "必须出现 Elimination（排除过程）。",
            "最终 Culprit 必须能解释 Symptom。",
        ],
        edge_hints=["提出怀疑（可能是…）", "验证（我们检查/实验…）", "排除（因此不是…）", "锁定（真正原因是…）", "修复（对应改动是…）"],
        requirements=TemplateRequirements(
            first_roles=["Symptom", "Hook"],
            role_min_counts={"Hypothesis": 2, "Test": 2, "Elimination": 1, "Culprit": 1, "Fix": 1},
            order_constraints=[("Hypothesis", "Test"), ("Test", "Elimination"), ("Elimination", "Culprit")],
        ),
    ),

    "design_review": NarrativeTemplate(
        template_id="design_review",
        title_cn="方案评审式（Design Review）",
        one_liner="需求约束—备选方案—取舍—决策—验证—风险。",
        roles=["Requirements", "Options", "Tradeoffs", "Decision", "Validation", "Risks"],
        constraints=[
            "Options 节点必须明确至少 2 个备选方向（可在一个节点里枚举）。",
            "Tradeoffs 必须解释为何不选其它方案。",
            "Risks 写明落地风险/性能风险/边界。",
        ],
        edge_hints=["约束（必须满足…）", "对比（相比之下…）", "取舍（代价/收益）", "决策（因此选择…）", "验证（实验/分析表明…）"],
        requirements=TemplateRequirements(
            first_roles=["Requirements", "Options"],
            role_min_counts={"Requirements": 1, "Options": 1, "Tradeoffs": 1, "Decision": 1, "Validation": 1, "Risks": 1},
            order_constraints=[("Options", "Tradeoffs"), ("Tradeoffs", "Decision"), ("Decision", "Validation")],
        ),
    ),

    "pipeline": NarrativeTemplate(
        template_id="pipeline",
        title_cn="流水线/系统式（Pipeline / Source-aligned）",
        one_liner="尽量贴合原文展开顺序：背景→问题→方法→实验→结论。",
        roles=["Background", "Problem", "Approach", "SystemOrAlgorithm", "Experiments", "Conclusion"],
        constraints=[
            "必须最大程度贴合原文顺序（按章节/段落推进，不要大幅重排）。",
            "每个节点尽量对应原文的一个 section/step（可合并但别乱序）。",
        ],
        edge_hints=["递进（接着…）", "方法对应问题（为了解决…）", "实验验证（我们评估…）", "总结（因此…）"],
        requirements=TemplateRequirements(
            first_roles=["Background"],
            role_min_counts={"Problem": 1, "Approach": 1, "Experiments": 1, "Conclusion": 1},
            order_constraints=[("Problem", "Approach"), ("Approach", "Experiments"), ("Experiments", "Conclusion")],
        ),
    ),
}

ALL_TEMPLATE_IDS: List[str] = list(TEMPLATES.keys())
