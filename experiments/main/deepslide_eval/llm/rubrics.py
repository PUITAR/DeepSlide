from __future__ import annotations

RSAT_RUBRIC = """\
You are an evaluator for a presentation-generation system.

Task: score Requirement Satisfaction (RSat) in [0, 1].

Inputs:
- Requirement profile U (audience, duration, focus priorities, style constraints)
- Deck summary (slide titles/bullets + speaker notes summary)

Rubric (score each subitem 0-1; final is weighted average):
1) Audience Fit (0.40): matches audience knowledge level; avoids inappropriate depth.
2) Focus Priorities (0.40): allocates emphasis according to priorities (e.g. method > experiments > impacts).
3) Style/Tone (0.20): matches requested tone and verbosity.

Important: do NOT score duration fit here. Duration fit is computed by a rule-based estimator from word count and WPM.

Output strictly as JSON with keys:
{
  "score": number,
  "subscores": {"audience": number, "focus": number, "style": number},
  "evidence": [string, ...],
  "warnings": [string, ...]
}
"""


SSC_RUBRIC = """\
You are an evaluator for slide–script complementarity.

Task: score SSC in [0, 1] based on whether speaker notes complement (not merely read) the slide, while covering key points.

Rubric (subscores 0-1; final is average):
1) Coverage: notes address the slide's key points (title + major bullets).
2) Complementarity: notes add explanation/context beyond slide text without drifting.

Output strictly as JSON:
{
  "score": number,
  "subscores": {"coverage": number, "complementarity": number},
  "evidence": [string, ...],
  "warnings": [string, ...]
}
"""


TRN_RUBRIC = """\
You are an evaluator for presentation transitions.

Task: score transition quality TRN in [0, 1] for the whole deck.

Consider: clear connective language between adjacent slides, signposting, smooth narrative flow.

Output strictly as JSON:
{
  "score": number,
  "evidence": [string, ...],
  "warnings": [string, ...]
}
"""


PACKED_JUDGE_RUBRIC = """\
You are an evaluator for a presentation-generation system.

You will receive a JSON payload with:
- U: requirement profile (duration, audience, priorities)
- deck: a short list of slides with slide_text and notes
- fidelity_items: a short list of (slide text+notes, retrieved source chunks)

Tasks:
1) RSat_subjective in [0,1] based only on audience fit, focus priorities, style/tone. Do NOT score duration fit.
2) SSC in [0,1] based on coverage and complementarity of speaker notes.
3) TRN in [0,1] based on transition quality and narrative flow.
4) Fidelity in [0,1] based on whether claims are supported by provided chunks.

Output strictly as JSON:
{
  "rsat_subjective": number,
  "ssc": number,
  "trn": number,
  "fidelity": number,
  "evidence": {
    "rsat": [string, ...],
    "ssc": [string, ...],
    "trn": [string, ...],
    "fidelity": [string, ...]
  },
  "warnings": [string, ...]
}
"""


FIDELITY_RUBRIC = """\
You are an evaluator for faithfulness to the source paper.

Task: You will receive a JSON payload with a list of items, each item contains:
- slide: the slide text + speaker notes text
- chunks: a small list of retrieved source chunks from the paper

Score overall textual fidelity in [0, 1].

High score if claims are supported by provided source chunks; penalize hallucinations, invented numbers, wrong conclusions.

Output strictly as JSON:
{
  "score": number,
  "supported": [string, ...],
  "unsupported": [string, ...],
  "warnings": [string, ...]
}
"""
