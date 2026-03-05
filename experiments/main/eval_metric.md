---
title: Dual-Leaderboard Evaluation Protocol for Presentation Agents
author: Yangming
date: 2026-02-08
---

# 0. Scope and Design Goals

This document defines a **two-leaderboard** evaluation protocol for presentation-generation agents:

- **Leaderboard A (Artifact Scoreboard)**: evaluates the quality of *static deliverables* (slides + script) in the traditional DOC2PPT setting.
- **Leaderboard B (Delivery Scoreboard)**: evaluates the quality of *end-to-end presentation delivery* (requirements → narrative control → synchronized slide+script → rehearsal readiness → optional dynamic attention choreography).

**Why two leaderboards?**  
A single scoreboard often conflates “pretty artifacts” with “ready-to-deliver presentations.” We explicitly separate them to (i) remain fair to strong static PPT systems, while (ii) accurately capturing systems that deliver a full talk process.

---

# 1. Notation and Evaluation Objects

## 1.1 Inputs

- Source document (paper / report / notes):  
  $\mathcal{T}=\{t_1,\ldots,t_n\}$, where $t_k$ is the *k-th knowledge frame* (a paragraph/section/figure/table chunk after preprocessing).
- Audience & requirement profile:  
  $\mathcal{U}$ contains:
  - target audience type $a$ (e.g., expert / investor / students),
  - target duration $D$ (seconds or minutes),
  - focus priorities $\pi$ (e.g., “method > experiments > impacts”),
  - style constraints $\sigma$ (tone, formality, verbosity, visuals),
  - optional constraints (forbidden topics, must-include items, etc.).

## 1.2 Outputs (system deliverables)

A system produces a presentation package:

- Slide sequence (static): $\mathcal{F}=\{f_1,\ldots,f_m\}$
- Script sequence aligned with slides: $\mathcal{P}=\{p_1,\ldots,p_m\}$
- Optional dynamic HTML with attention choreography: $\mathcal{H}$
- Optional audio narration: $\mathcal{A}$
- Optional *narrative plan / logic chain* candidates: $\mathcal{L}=\{\ell^{(1)},\ldots,\ell^{(B)}\}$ (often $B=4$)
- Optional time plan: per-slide budget $\mathbf{d}=\{d_1,\ldots,d_m\}$, $\sum_k d_k \approx D$
- Optional attention plan: per-slide focus segments  
  $\Phi=\{\phi_k\}_{k=1}^m$, where $\phi_k=\{(r_{k,j},\tau_{k,j})\}_j$ denotes region $r_{k,j}$ with time span $\tau_{k,j}$

> **Static-only systems** may not output $\mathcal{H},\mathcal{A},\mathcal{L},\mathbf{d},\Phi$. The protocol defines *fair fallback estimators* so they can still receive non-zero scores.

---

# 2. Dataset and Experimental Protocol

## 2.1 Benchmark instances

Each evaluation instance is a triple $(\mathcal{T},\mathcal{U},\mathcal{G})$:

- $\mathcal{T}$: source document
- $\mathcal{U}$: requirement profile (including audience + time)
- $\mathcal{G}$: optional ground-truth references:
  - human-authored outline or a set of keypoints,
  - figure/table “must-mention” annotations,
  - comprehension questions (for rehearsal/understanding tests)

## 2.2 Multi-run and stability

To measure stability, for each instance we run each system $R$ times (e.g., $R=5$) with different randomness/seeds:

- “Successful run” means the system produces **usable** $(\mathcal{F},\mathcal{P})$ (and optionally $\mathcal{H},\mathcal{A}$) without fatal errors (crash, invalid output, missing alignment, unreadable slides).

---

# 3. Leaderboard A — Artifact Scoreboard (traditional)

Leaderboard A emphasizes **static quality** of slides and script. It contains three metric groups:

1) **Stability** (can it reliably produce usable artifacts?)  
2) **Fidelity** (does it preserve source content?)  
3) **Artifact readability & aesthetics** (is it legible and well-designed?)

We compute each metric in $[0,1]$, then aggregate.

---

## 3.1 A1. System Stability — Average Compilation Success Rate (ACSR)

**Definition.** For each instance, let $s_r \in \{0,1\}$ indicate whether run $r$ succeeds.  
$$
ACSR = \frac{1}{R}\sum_{r=1}^{R} s_r.
$$

**Success criteria checklist** (example):
- Slides render without missing fonts/overlaps beyond threshold.
- Script is present for all slides ($|\mathcal{P}|=|\mathcal{F}|$).
- No broken media references.
- (If exporting PPT/PDF) file opens and pages count matches.

---

## 3.2 A2. Fidelity — Textual Fidelity and Visual Fidelity

### A2.1 Textual Fidelity $F_{\text{text}}$

We measure how well generated content matches the source $\mathcal{T}$.  
Let $t_k$ be the aligned source chunk for slide $k$ (alignment via retrieval over $\mathcal{T}$; see Section 6).

Compute two similarity families:
- lexical overlap (ROUGE)
- semantic similarity (BERTScore or embedding similarity)

Per-slide:
$$
F^{(k)}_{\text{rouge}} = \frac{1}{2}\big(\text{ROUGE}(p_k,t_k)+\text{ROUGE}(f_k,t_k)\big),
\quad
F^{(k)}_{\text{bert}} = \frac{1}{2}\big(\text{BERT}(p_k,t_k)+\text{BERT}(f_k,t_k)\big).
$$
Aggregate across slides:
$$
F_{\text{rouge}}=\frac{1}{m}\sum_{k=1}^m F^{(k)}_{\text{rouge}},
\quad
F_{\text{bert}}=\frac{1}{m}\sum_{k=1}^m F^{(k)}_{\text{bert}}.
$$
Final:
$$
F_{\text{text}} = w_R \cdot F_{\text{rouge}} + w_B \cdot F_{\text{bert}}, \quad (w_R+w_B=1).
$$

> Recommended: $w_R=w_B=0.5$ unless a domain requires stricter faithfulness.

### A2.2 Visual Fidelity $F_{\text{vis}}$

We evaluate whether important figures/tables from $\mathcal{T}$ are carried into slides.

Let $\mathcal{I}(\mathcal{T})$ be the set of figure/table items extracted from $\mathcal{T}$, and $\mathcal{I}(\mathcal{F})$ those present in slides.

$$
F_{\text{vis}}=\frac{|\mathcal{I}(\mathcal{T})\cap \mathcal{I}(\mathcal{F})|}{|\mathcal{I}(\mathcal{T})|}.
$$

Matching can be done by:
- identical image hashes (if re-used),
- caption similarity (embedding match),
- OCR on captions (optional).

---

## 3.3 A3. Readability & Aesthetics (static)

We avoid “beauty is subjective” by using a **hybrid**: automatic checks + a small human rubric.

### A3.1 Automatic Legibility Score $L$

Common failure modes: text overflow, excessive density, tiny fonts, low contrast, cluttered layout.

Define binary checks for each slide $k$:
- overflow indicator $o_k$ (1 if overflow detected)
- density indicator $d_k$ (1 if too many words/objects)
- min-font indicator $u_k$ (1 if min font < threshold)

Then:
$$
L = 1 - \frac{1}{m}\sum_{k=1}^m \big(\lambda_o o_k + \lambda_d d_k + \lambda_u u_k\big),
$$
clipped to $[0,1]$.

> Implementation notes:  
> - For PPT: extract bounding boxes and font sizes.  
> - For PDF: use text boxes if available; otherwise approximate via rendering + layout detection.

### A3.2 Human Aesthetic Rubric $A$

Each deck is rated by $J$ annotators (e.g., $J=3$) on 1–5 Likert scales:
- visual hierarchy (title / key points pop)
- alignment/spacing consistency
- visual balance (not cramped)
- stylistic coherence (fonts/colors consistent)

Normalize:
$$
A = \frac{\overline{a}-1}{4},
$$
where $\overline{a}$ is the average Likert score.

---

## 3.4 Artifact Score aggregation (Leaderboard A)

We define:
$$
S_{\text{Artifact}} = 
\alpha_{\text{stab}} \cdot ACSR
+ \alpha_{\text{fid}} \cdot \Big(\beta F_{\text{text}} + (1-\beta)F_{\text{vis}}\Big)
+ \alpha_{\text{read}} \cdot \Big(\gamma L + (1-\gamma)A\Big),
$$
with $\alpha_{\text{stab}}+\alpha_{\text{fid}}+\alpha_{\text{read}}=1$.

**Suggested default weights**:
- $\alpha_{\text{stab}}=0.25$
- $\alpha_{\text{fid}}=0.45$
- $\alpha_{\text{read}}=0.30$
- $\beta=0.7$, $\gamma=0.6$

> Rationale: fidelity matters for academic talks; readability matters but should not dominate.

---

# 4. Leaderboard B — Delivery Scoreboard (end-to-end talk delivery)

Leaderboard B evaluates whether a system delivers a **ready-to-present experience**, including requirements fit, narrative controllability, synchronized complementarity, time pacing, attention choreography (if any), and rehearsal readiness.

We compute each metric in $[0,1]$, then aggregate.

---

## 4.1 B1. Requirement Satisfaction (RSat)

**Goal.** Verify outputs match $\mathcal{U}$: audience level, style, priority focus, constraints, and duration.

We define a set of requirement checks $\mathcal{R}_{\text{Sat}}$ derived from $\mathcal{U}$.  
Each check $r_i$ yields a score $\in [0,1]$ (binary or graded).

$$
RSat = \sum_{i=1}^{|\mathcal{R}_{\text{Sat}}|} w_i \cdot r_i(\mathcal{F},\mathcal{P},\mathcal{U}),
\quad \sum_i w_i = 1.
$$

**How to compute $r_i$:**
- Hard constraints (must-include topic X): retrieval + mention detection (LLM judge allowed).
- Audience fit: LLM judge with explicit rubric (“for investors, avoid math-heavy details”).
- Style: classifier / LLM judge on tone and verbosity.
- Focus priorities: measure content allocation vs priority vector $\pi$ (Section 6 alignment).

**Fairness to static systems:** RSat is computable from $(\mathcal{F},\mathcal{P})$ alone.

---

## 4.2 B2. Narrative Diversity & Controllability (NDC)

This metric targets systems that output **multiple narrative candidates** and support **editable narrative plans**.

### B2.1 Diversity among candidates $Div(\mathcal{L})$

If a system outputs $B$ plans $\mathcal{L}=\{\ell^{(b)}\}$, compute average pairwise structural distance:
$$
Div = \frac{2}{B(B-1)}\sum_{b_1<b_2} \text{dist}(\ell^{(b_1)},\ell^{(b_2)}),
$$
normalized to $[0,1]$.

**dist** can combine:
- role-sequence edit distance (opening types differ),
- keypoint order difference,
- topic allocation divergence (KL divergence over topic histogram).

If a system outputs only one plan, set $Div = 0$ (not negative).

### B2.2 Controllability $Ctrl$

We evaluate whether user edits produce predictable changes without breaking constraints.

We define a standard edit set $\mathcal{E}$ (benchmarked user actions):
- reorder two sections
- increase time for “method” by +20%
- remove a subsection
- change audience from “expert” to “student”
- swap narrative style template

For each edit $e\in\mathcal{E}$, we check:
- whether the edited intent is reflected in the regenerated output (LLM judge + alignment stats)
- whether stability and duration constraints still hold

Let success indicator $c_e\in[0,1]$. Then:
$$
Ctrl=\frac{1}{|\mathcal{E}|}\sum_{e\in \mathcal{E}} c_e.
$$

**Fallback for static systems:**  
If a system does not support editable plans, we measure **implicit controllability** via prompt re-runs:
- apply the same edit as a prompt instruction and regenerate.
This yields non-zero but typically lower Ctrl.

### B2.3 Final NDC
$$
NDC = \eta \cdot Div + (1-\eta)\cdot Ctrl, \quad \eta \in [0,1].
$$
Suggested $\eta=0.4$.

---

## 4.3 B3. Slide–Script Complementarity (SSC)

**Goal.** Slide and script should be *complementary*: not “reading the slide,” but also not drifting away.

We use two components:

### B3.1 Redundancy score $Red$

Let $sim_k\in[0,1]$ be semantic similarity between slide text and script for slide $k$.  
Define a target interval $[l,u]$ (sweet spot), e.g., $[0.25,0.55]$.

$$
Red = \frac{1}{m}\sum_{k=1}^m \Big(1 - \frac{\min(|sim_k-l|,|sim_k-u|)}{\max(l,1-u)+\epsilon}\Big)_+,
$$
clipped to $[0,1]$. Intuition: best if similarity is inside the interval.

### B3.2 Coverage score $Cov$

Let $K_k$ be key visual/textual points in slide $k$ (title + bullets + detected figure/table key labels).  
Let $cov_k\in[0,1]$ be fraction of key points addressed by the script (LLM judge allowed).

$$
Cov = \frac{1}{m}\sum_{k=1}^m cov_k.
$$

### B3.3 Final SSC
$$
SSC=\frac{Red+Cov}{2}.
$$

---

## 4.4 B4. Temporal Delivery Quality (TDQ)

**Goal.** The talk fits the time budget and has reasonable pacing.

### B4.1 Total duration adherence $TDA$

Estimate spoken duration from script length:  
$\widehat{D} = \sum_k \text{words}(p_k) / \text{wpm}$, wpm default 140–160.

$$
TDA = \exp\Big(-\frac{|\widehat{D}-D|}{\tau}\Big),
$$
where $\tau$ controls tolerance (e.g., $\tau = 45$ seconds).

### B4.2 Per-slide pacing $PSP$

Let $\widehat{d}_k$ be estimated time for $p_k$. Penalize extreme imbalance:
$$
PSP = 1 - \frac{\text{std}(\{\widehat{d}_k\})}{\text{std}_{\max}+\epsilon},
$$
clipped to $[0,1]$. $\text{std}_{\max}$ can be set from dataset stats.

### B4.3 Transition quality $TRN$

Use LLM judge to rate whether slide-to-slide transitions have explicit connective language (setup → contrast → conclusion).  
Normalize Likert to $[0,1]$.

### B4.4 Final TDQ
$$
TDQ = \frac{TDA + PSP + TRN}{3}.
$$

**Fairness to static systems:** TDQ uses only script, no dynamic needed.

---

## 4.5 B5. Attention Choreography Quality (ACQ)

**Goal.** If the system provides dynamic guidance (focus/highlight/animations), it should guide attention to the right regions at the right time.

We define *attention alignment* between script and focus plan.

### B5.1 Focus–script alignment $FSA$

For each focus segment $(r_{k,j},\tau_{k,j})$, extract the script span $p_{k,j}$ spoken during $\tau_{k,j}$.  
Let $a_{k,j}\in[0,1]$ be LLM-judged alignment between $r_{k,j}$ (region content) and $p_{k,j}$ (spoken content).

$$
FSA = \frac{\sum_{k,j} |\tau_{k,j}| \cdot a_{k,j}}{\sum_{k,j} |\tau_{k,j}|}.
$$

### B5.2 Focus coverage $FCV$

Let $\mathcal{K}_k$ be the set of key regions in slide $k$ (figure subregions, table rows/cols, key bullets).  
Let $covered_k$ be the fraction of $\mathcal{K}_k$ that gets focused/highlighted at least once.

$$
FCV = \frac{1}{m}\sum_{k=1}^m covered_k.
$$

### B5.3 Distraction penalty $DSP$

Penalize overly frequent, long, or irrelevant effects:
- too many focus switches per minute,
- focus on non-informative decorative regions,
- mismatched highlights.

Let $pen \in [0,1]$ be total penalty; define:
$$
DSP = 1 - pen.
$$

### B5.4 Final ACQ
$$
ACQ = \frac{FSA + FCV + DSP}{3}.
$$

**Fair fallback for static systems (no $\Phi$)**  
We estimate an *implicit attention plan* from slide hierarchy:
- title and largest-font bullets are “primary regions,”
- figure captions and highlighted callouts are “secondary regions.”
Then compute FSA/FCV by aligning script to these regions.  
This yields a meaningful non-zero baseline.

---

## 4.6 B6. Rehearsal Readiness (RR)

**Goal.** How close is the output to “walk on stage and deliver”?

We define three components.

### B6.1 First-rehearsal success rate $FRS$

A rehearsal is successful if a user can play through the full sequence without:
- missing script segments,
- broken timings,
- focus desync / missing assets,
- unreadable slides

$$
FRS = \frac{\#\text{successful rehearsals}}{\#\text{attempted rehearsals}}.
$$

### B6.2 Preparation cost $PC$

Measure how much the user must edit before delivering:
- number of manual edits,
- total edited tokens/words,
- time-to-ready (if user study)

Normalize to $[0,1]$ via:
$$
PC = 1 - \frac{\text{edit\_cost}-\min}{\max-\min+\epsilon}.
$$

### B6.3 Listener comprehension $LC$

We prepare short quizzes/recall tasks per talk (5–10 items).  
$$
LC = \frac{\#\text{correct}}{\#\text{questions}}.
$$

### B6.4 Final RR
$$
RR = \frac{FRS + PC + LC}{3}.
$$

**Fairness note:**  
Static systems can still be rehearsed by humans, so they will get non-zero FRS/LC; however, without synchronized script/audio/focus, their preparation cost tends to be higher.

---

## 4.7 Delivery Score aggregation (Leaderboard B)

We include a small portion of Artifact fundamentals to avoid gaming with “flashy but wrong” delivery.

$$
S_{\text{Delivery}} =
\sum_{x\in\{RSat,NDC,SSC,TDQ,ACQ,RR\}} \omega_x \cdot x
+ \omega_{\text{stab}}\cdot ACSR
+ \omega_{\text{fid}}\cdot \Big(\beta F_{\text{text}} + (1-\beta)F_{\text{vis}}\Big),
$$
with total weights summing to 1.

**Suggested default weights**:
- $\omega_{RSat}=0.15$
- $\omega_{NDC}=0.12$
- $\omega_{SSC}=0.15$
- $\omega_{TDQ}=0.12$
- $\omega_{ACQ}=0.16$
- $\omega_{RR}=0.15$
- $\omega_{\text{stab}}=0.08$
- $\omega_{\text{fid}}=0.07$

---

# 5. Audience-Specific Weighting (optional but recommended)

For different audiences $a$, we reweight metrics (same definitions, different priorities):

- **Expert / academic**: higher Fidelity, TDQ, SSC
- **Investor / product**: higher RSat, hook/engagement, RR
- **Students / teaching**: higher cognitive load control, ACQ, LC

Formally, let $\mathbf{\Omega}(a)$ be a weight vector. We report:
- global scores (default weights)
- audience-specific scores (per-audience weights)

---

# 6. Implementation Details (practical computation)

## 6.1 Aligning slides to source chunks

We need an alignment map $g(k)$ that assigns slide $k$ to a subset of source chunks $\mathcal{T}$:
- retrieve top-$K$ chunks by embedding similarity using slide text + script text
- optionally incorporate figure captions and section headers
- define $t_k$ as concatenation of top chunks (or a weighted summary)

This alignment is used by $F_{\text{text}}$, RSat topic allocation, etc.

## 6.2 LLM-as-judge guidelines

When using an LLM judge:
- Provide the judge a strict rubric and examples.
- Use pairwise comparisons when possible.
- Calibrate on a small set of human-scored examples.
- Report inter-annotator agreement for human parts.

## 6.3 Normalization

For any raw metric $x$, map to $[0,1]$ using:
- min-max scaling with dataset-wide bounds, or
- sigmoid/exponential forms (e.g., duration adherence)

Always publish the chosen bounds and calibration set.

---

# 7. Reporting Template

For each system, report:

- Leaderboard A: $S_{\text{Artifact}}$ + breakdown (ACSR, $F_{\text{text}}$, $F_{\text{vis}}$, $L$, $A$)
- Leaderboard B: $S_{\text{Delivery}}$ + breakdown (RSat, NDC, SSC, TDQ, ACQ, RR, ACSR, Fidelity)
- Stability across runs: mean ± std
- (Optional) audience-specific scores

---

# 8. Relation to existing metrics in your draft

Your original metrics can be integrated as follows:
- OHS / RS → part of RSat (hook presence) and TDQ/TRN (rhythm/transition), optionally as an “Engagement Potential” subscore
- CLC → influences RSat (audience fit) and RR (comprehension), optionally as a standalone “Cognitive Load” metric
- ACSR / Fidelity are directly used (Sections 3.1, 3.2)

---

# 9. Minimal “ready-to-run” metric set

If you need a smaller version:
- Artifact: ACSR, $F_{\text{text}}$, $F_{\text{vis}}$, Legibility $L$
- Delivery: RSat, SSC, TDQ, RR, + small ACQ (implicit attention)

This keeps human labeling light while still highlighting delivery-centric advantages.
