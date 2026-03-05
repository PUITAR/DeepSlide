
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class TemplateRequirements:
    """Hard checks to ensure narrative structures are genuinely different."""
    # The first node role must be one of these (enforces different openings).
    first_roles: List[str]
    # Minimal counts for specific roles (duplicates allowed).
    role_min_counts: Dict[str, int]
    # Ordering constraints: first occurrence of A must be before first occurrence of B.
    order_constraints: List[Tuple[str, str]]


@dataclass(frozen=True)
class NarrativeTemplate:
    """A template that enforces a genuinely different narrative structure."""
    template_id: str
    title_en: str
    one_liner: str
    # Allowed role names (the model should use these EXACT role tokens; duplicates allowed).
    roles: List[str]
    # Hard constraints / tips shown to the model.
    constraints: List[str]
    # Suggested edge-relation phrasing.
    edge_hints: List[str]
    # Programmatic requirements enforced by a validator.
    requirements: TemplateRequirements

    def prompt_block(self) -> str:
        roles_txt = ", ".join(self.roles + ["Extra"])
        cons_txt = "\n".join([f"- {c}" for c in self.constraints])
        edge_txt = "\n".join([f"- {e}" for e in self.edge_hints])
        # Keep requirements concise in the prompt (full checks happen in code).
        req_txt = "\n".join(
            [f"- first_roles: {', '.join(self.requirements.first_roles)}"]
            + [f"- min({k}) >= {v}" for k, v in self.requirements.role_min_counts.items()]
            + [f"- order: {a} before {b}" for a, b in self.requirements.order_constraints]
        )
        return (
            f"Template ID: {self.template_id}\n"
            f"Template Name: {self.title_en}\n"
            f"One-line goal: {self.one_liner}\n"
            f"Allowed role tokens (duplicates allowed; use Extra if needed): {roles_txt}\n"
            f"Constraints:\n{cons_txt}\n"
            f"Edge hints:\n{edge_txt}\n"
            f"Structural requirements:\n{req_txt}\n"
        )


TEMPLATES: Dict[str, NarrativeTemplate] = {
    "postmortem": NarrativeTemplate(
        template_id="postmortem",
        title_en="Postmortem (Incident Review)",
        one_liner="Explain it like an incident postmortem: impact → timeline → root cause → fix → action items.",
        roles=["Summary", "Impact", "Timeline", "RootCause", "Fix", "ActionItems"],
        constraints=[
            "Must include a clear timeline (Timeline).",
            "RootCause must explain key phenomena in Impact/Timeline.",
            "Must end with ActionItems (actionable improvements / lessons learned).",
        ],
        edge_hints=[
            "Causality (leads to / triggers)",
            "Evidence support (as shown by ...)",
            "Fix targets (to address ...)",
            "Postmortem takeaway (therefore we learned ...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Summary", "Impact"],
            role_min_counts={"Timeline": 1, "RootCause": 1, "Fix": 1, "ActionItems": 1},
            order_constraints=[("Impact", "RootCause"), ("RootCause", "Fix"), ("Fix", "ActionItems")],
        ),
    ),

    "in_medias_res": NarrativeTemplate(
        template_id="in_medias_res",
        title_en="In Medias Res (Suspense / Reverse Reveal)",
        one_liner="Start with the most striking result/anomaly, then flash back to reveal why it happens.",
        roles=["Hook", "MysteryQuestion", "FlashbackContext", "Clue", "Reveal", "ReturnToHook"],
        constraints=[
            "The opening must be Hook (the most gripping result/anomaly/counterintuitive point, grounded in the paper).",
            "Provide at least 2 Clues (progressive reveal).",
            "End with ReturnToHook that explains and closes the Hook.",
        ],
        edge_hints=[
            "Suspense push (this raises a question...)",
            "Clue progression (we further find...)",
            "Reveal (the key is...)",
            "Call-back (back to the opening...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Hook"],
            role_min_counts={"Clue": 2, "Reveal": 1, "ReturnToHook": 1},
            order_constraints=[("Hook", "Reveal"), ("Reveal", "ReturnToHook")],
        ),
    ),

    "pyramid_bluf": NarrativeTemplate(
        template_id="pyramid_bluf",
        title_en="Pyramid / BLUF (Bottom Line Up Front)",
        one_liner="Lead with the conclusion/claim, then support it with reasons and evidence.",
        roles=["BottomLine", "Reason", "Evidence", "Caveats"],
        constraints=[
            "The first node must be BottomLine (one-sentence conclusion).",
            "At least 2 Reason nodes (parallel reasons).",
            "Evidence must support the preceding Reason(s).",
            "Must end with Caveats (boundaries/limitations/trade-offs).",
        ],
        edge_hints=[
            "Top-down (the conclusion is supported by...)",
            "Parallel (in addition / also)",
            "Evidence (experiments show...)",
            "Boundary (does not hold when...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["BottomLine"],
            role_min_counts={"Reason": 2, "Evidence": 1, "Caveats": 1},
            order_constraints=[("BottomLine", "Reason"), ("Reason", "Evidence"), ("Evidence", "Caveats")],
        ),
    ),

    "imrad": NarrativeTemplate(
        template_id="imrad",
        title_en="Scientific IMRaD (Intro–Methods–Results–Discussion)",
        one_liner="Follow the scientific validation flow: problem/hypothesis → methods → results → discussion/implications.",
        roles=["Introduction", "Hypothesis", "Methods", "Results", "Discussion", "Implications"],
        constraints=[
            "Must include a testable Hypothesis.",
            "Results must include 1–2 key observations (grounded in the paper).",
            "Discussion must explain ‘why’, not merely restate results.",
        ],
        edge_hints=[
            "Propose (we hypothesize...)",
            "Validate (we test with... method)",
            "Result (we observe...)",
            "Explain (a possible reason is...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Introduction"],
            role_min_counts={"Hypothesis": 1, "Methods": 1, "Results": 1, "Discussion": 1},
            order_constraints=[("Hypothesis", "Methods"), ("Methods", "Results"), ("Results", "Discussion")],
        ),
    ),

    "faq_defense": NarrativeTemplate(
        template_id="faq_defense",
        title_en="FAQ / Defense (Adversarial Q&A)",
        one_liner="Each node answers a sharp question; structure is driven by audience doubts.",
        roles=["Q", "A", "Risks"],
        constraints=[
            "At least 3 rounds of Q/A (Q and A alternate).",
            "Questions must be sharp (why existing fails? why yours works? what’s the cost?).",
            "Must end with Risks (risks/boundaries/trade-offs).",
        ],
        edge_hints=[
            "Challenge (the audience may ask...)",
            "Response (the key is...)",
            "Evidence (for example...)",
            "Concession (the trade-off is...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Q"],
            role_min_counts={"Q": 3, "A": 3, "Risks": 1},
            order_constraints=[("Q", "A")],
        ),
    ),

    "myth_fact": NarrativeTemplate(
        template_id="myth_fact",
        title_en="Myth → Fact (Debunk & Reframe)",
        one_liner="State common myths, debunk with evidence, then present the correct framework and implications.",
        roles=["Myth", "WhyBelieved", "CounterEvidence", "CorrectModel", "Implication", "Takeaway"],
        constraints=[
            "At least 2 Myth nodes, each with corresponding CounterEvidence.",
            "CounterEvidence must be grounded in the paper (paper node + evidence).",
            "CorrectModel/Implication must provide a better understanding and actionable guidance.",
        ],
        edge_hints=[
            "Myth (common but wrong)",
            "Falsify (evidence shows...)",
            "Alternative explanation (more plausible is...)",
            "Implication (therefore we should...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Myth"],
            role_min_counts={"Myth": 2, "CounterEvidence": 2, "CorrectModel": 1, "Takeaway": 1},
            order_constraints=[("Myth", "CounterEvidence"), ("CounterEvidence", "CorrectModel"), ("CorrectModel", "Takeaway")],
        ),
    ),

    "heros_journey": NarrativeTemplate(
        template_id="heros_journey",
        title_en="Hero’s Journey (Research Journey)",
        one_liner="Tell it as a journey: goal → trials → ordeal/dilemma → misstep → breakthrough → return → reward.",
        roles=["Call", "Trials", "Ordeal", "FalseLead", "Breakthrough", "Return", "Reward"],
        constraints=[
            "Must include Trials/Ordeal (obstacles/dilemmas).",
            "Must include FalseLead (a wrong intuition / failed attempt / discarded route).",
            "Note: if FalseLead is not in the paper, mark it as bridge/rhetorical; do not present as paper fact.",
            "Breakthrough must correspond to the key method/insight in the paper.",
        ],
        edge_hints=[
            "Obstacle (however...)",
            "Trial & elimination (this path fails because...)",
            "Breakthrough (the key discovery is...)",
            "Payoff (therefore it brings...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Call"],
            role_min_counts={"Trials": 1, "Ordeal": 1, "FalseLead": 1, "Breakthrough": 1, "Reward": 1},
            order_constraints=[("Trials", "FalseLead"), ("FalseLead", "Breakthrough"), ("Breakthrough", "Reward")],
        ),
    ),

    "monroe": NarrativeTemplate(
        template_id="monroe",
        title_en="Monroe’s Motivated Sequence (Persuasive Call)",
        one_liner="Attention → Need → Satisfaction → Visualization → Action.",
        roles=["Attention", "Need", "Satisfaction", "Visualization", "Action"],
        constraints=[
            "Attention must be compelling (contrast/pain point/surprising fact) but cannot fabricate paper conclusions.",
            "Visualization must be concrete (adopt vs. not adopt outcomes) and cannot pretend to be paper results.",
            "Action must clearly state the next step request/recommendation.",
        ],
        edge_hints=[
            "Hook (imagine...)",
            "Pain point (the current issue is...)",
            "Solution (we propose...)",
            "Contrast (if... then...)",
            "Call to action (next we should...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Attention"],
            role_min_counts={"Need": 1, "Satisfaction": 1, "Visualization": 1, "Action": 1},
            order_constraints=[("Need", "Satisfaction"), ("Satisfaction", "Visualization"), ("Visualization", "Action")],
        ),
    ),

    "case_study": NarrativeTemplate(
        template_id="case_study",
        title_en="Case Study (Scenario-Driven)",
        one_liner="Use one end-to-end case: setting → problem → goals → user flow → solution → results → lessons.",
        roles=["CaseBackground", "CaseProblem", "Objectives", "UserFlow", "Solution", "Results", "Lessons"],
        constraints=[
            "Must include UserFlow: narrate a concrete task flow (Input → process → output/feedback); do not reduce to a paper-outline re-skin.",
            "Results may only cite results/comparisons that exist in the paper (paper + evidence).",
            "Lessons should extract transferable insights (bridge/rhetorical allowed).",
        ],
        edge_hints=[
            "Scenario (in ... settings)",
            "Problem (this causes ...)",
            "Flow (first... then... finally...)",
            "Effect (results show ...)",
            "Transfer (this implies ...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["CaseBackground"],
            role_min_counts={"UserFlow": 1, "Solution": 1, "Results": 1, "Lessons": 1},
            order_constraints=[("Objectives", "UserFlow"), ("UserFlow", "Solution"), ("Solution", "Results")],
        ),
    ),

    "hypothesis_elimination": NarrativeTemplate(
        template_id="hypothesis_elimination",
        title_en="Hypothesis Elimination (Detective Style)",
        one_liner="Propose multiple hypotheses and rule them out via tests, then identify the culprit and the fix.",
        roles=["Symptom", "Hypothesis", "Test", "Elimination", "Culprit", "Fix"],
        constraints=[
            "At least 2 Hypothesis nodes with corresponding Test nodes.",
            "Must include Elimination (the ruling-out process).",
            "Final Culprit must explain the Symptom.",
        ],
        edge_hints=[
            "Suspect (could it be...?)",
            "Test (we check/experiment...)",
            "Eliminate (therefore it’s not...)",
            "Identify (the real cause is...)",
            "Fix (the corresponding change is...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Symptom", "Hook"],
            role_min_counts={"Hypothesis": 2, "Test": 2, "Elimination": 1, "Culprit": 1, "Fix": 1},
            order_constraints=[("Hypothesis", "Test"), ("Test", "Elimination"), ("Elimination", "Culprit")],
        ),
    ),

    "design_review": NarrativeTemplate(
        template_id="design_review",
        title_en="Design Review (Requirements → Options → Trade-offs)",
        one_liner="Requirements/constraints → alternatives → trade-offs → decision → validation → risks.",
        roles=["Requirements", "Options", "Tradeoffs", "Decision", "Validation", "Risks"],
        constraints=[
            "Options must explicitly include at least 2 alternative directions (can be enumerated within one node).",
            "Tradeoffs must explain why other options are not chosen.",
            "Risks must state deployment/performance risks and boundaries.",
        ],
        edge_hints=[
            "Constraint (must satisfy...)",
            "Compare (in contrast...)",
            "Trade-off (cost/benefit)",
            "Decision (therefore choose...)",
            "Validate (experiments/analysis show...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Requirements", "Options"],
            role_min_counts={"Requirements": 1, "Options": 1, "Tradeoffs": 1, "Decision": 1, "Validation": 1, "Risks": 1},
            order_constraints=[("Options", "Tradeoffs"), ("Tradeoffs", "Decision"), ("Decision", "Validation")],
        ),
    ),

    "pipeline": NarrativeTemplate(
        template_id="pipeline",
        title_en="Pipeline / Source-Aligned (Follow the Paper)",
        one_liner="Follow the paper’s flow: background → problem → method → experiments → conclusion.",
        roles=["Background", "Problem", "Approach", "SystemOrAlgorithm", "Experiments", "Conclusion"],
        constraints=[
            "Must follow the paper’s order as closely as possible (advance by sections/paragraphs; avoid heavy reordering).",
            "Each node should correspond to one section/step (merging allowed, but do not shuffle arbitrarily).",
        ],
        edge_hints=[
            "Progression (next...)",
            "Method addresses problem (to solve...)",
            "Experimental validation (we evaluate...)",
            "Wrap-up (therefore...)",
        ],
        requirements=TemplateRequirements(
            first_roles=["Background"],
            role_min_counts={"Problem": 1, "Approach": 1, "Experiments": 1, "Conclusion": 1},
            order_constraints=[("Problem", "Approach"), ("Approach", "Experiments"), ("Experiments", "Conclusion")],
        ),
    ),
}

ALL_TEMPLATE_IDS: List[str] = list(TEMPLATES.keys())
