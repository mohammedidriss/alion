# Alion — Dissertation Framework & Research Questions

> **Program:** Doctor of Business Administration (DBA), Golden Gate University
> **Working title:** *Multi-Modal AI Coaching for Combat Sports: Design, Validation, and Adoption of a Sensor-Fused Feedback Platform*
> **Author:** Mohamad Idriss
> **Status:** Living document — last updated 2026-05-22
> **Companion docs:** [RQ1.md](RQ1.md) · [LITERATURE_REVIEW_NOTES.md](LITERATURE_REVIEW_NOTES.md)

---

## Table of Contents
1. [Positioning & Problem Statement](#1-positioning--problem-statement)
2. [The Gap](#2-the-gap)
3. [Research Questions — Overview](#3-research-questions--overview)
4. [RQ1 — Perceived Efficacy of Multi-Modal Fusion](#rq1--perceived-efficacy-of-multi-modal-fusion)
5. [RQ2 — Technical Validity of the Sensing Pipeline](#rq2--technical-validity-of-the-sensing-pipeline)
6. [RQ3 — HRV Readiness & Within-Session Performance](#rq3--hrv-readiness--within-session-performance)
7. [RQ4 — Longitudinal Coaching Value](#rq4--longitudinal-coaching-value)
8. [RQ5 — Adoption, Trust & Perceived Utility (DBA Core)](#rq5--adoption-trust--perceived-utility-dba-core)
9. [RQ6 — Operational Feasibility: Feedback Latency](#rq6--operational-feasibility-feedback-latency)
10. [How the RQs De-Risk Each Other](#10-how-the-rqs-de-risk-each-other)
11. [Contribution Statement](#11-contribution-statement)
12. [Scope, Assumptions & Limitations](#12-scope-assumptions--limitations)
13. [Ethics & IRB](#13-ethics--irb)

---

## 1. Positioning & Problem Statement

Boxing has over half a billion participants worldwide, and the post-pandemic
shift toward at-home and unsupervised training has widened a structural gap:
fighters increasingly train **without real-time, expert coaching feedback**,
which both limits technical development and elevates injury risk.

Two research lineages have tried to close this gap. Vision-based systems
(AIFit, CVPR 2021) deliver pose-based feedback from a camera but fail in
boxing — gloves and contact occlude tracking, and cameras cannot measure the
forces and accelerations that define a punch. Sensor-based systems (BoxingPro,
*Electronics* 2025) attach IMUs and translate kinematics into LLM-generated
coaching advice, but operate only at the **single-punch level** within an
isolated session, with no physiological context, no longitudinal tracking, and
no role-aware platform.

**This dissertation asks whether a deployed, multi-role platform that fuses
biomechanical (CV), kinematic (IMU), and physiological (HRV) data — and
translates that fusion into LLM-generated coaching feedback — produces
coaching value that practitioners recognise, trust, and would adopt.**

As a **DBA** dissertation the contribution is deliberately dual: a technical
artifact (the Alion platform and its validation) *and* a management finding
(whether and why combat-sports practitioners would adopt multi-modal AI
coaching, and what that implies for the sports-technology market).

---

## 2. The Gap

| Capability | AIFit (2021) | BoxingPro (2025) | **Alion (this work)** |
|---|---|---|---|
| Sport | Fitness | Boxing | Boxing / combat sports |
| Modalities | RGB camera | IMU + video | **CV + IMU + HRV** |
| Granularity | Exercise rep | Single punch | **Session + longitudinal** |
| Physiology | — | — | **HRV readiness & fatigue** |
| Roles | Single user | Single user | **Fighter / Coach / Referee / Gym Mgr** |
| Deployment | Prototype | Prototype | **Production SaaS** |
| Business lens | — | — | **Adoption & trust study** |

No prior system combines sensor fusion, physiological context, longitudinal
analytics, a multi-role platform, *and* an empirical adoption study. That
combination is the gap.

---

## 3. Research Questions — Overview

The study deliberately spans **six** complementary questions so that the
dissertation's contribution does not rest on any single result. Each RQ is
independently publishable and independently defensible.

| RQ | Theme | Type | Primary method | Key output |
|---|---|---|---|---|
| **RQ1** | Does fusion *feel* better to coaches? | Perceived quality | Blinded within-subjects rating | Friedman χ², Kendall's W |
| **RQ2** | Does the pipeline *measure* correctly? | Technical validity | Labeled-video benchmark | Precision/Recall/F1, timestamp MSE |
| **RQ3** | Does HRV readiness predict performance? | Physiological validity | Repeated-measures correlation | Mixed-effects β, r + CI |
| **RQ4** | Is longitudinal feedback *valuable*? | Longitudinal utility | Coach-agreement study | Cohen's κ, actionability Likert |
| **RQ5** | Would practitioners *adopt* it? | Adoption / business | Mixed-methods (UTAUT + interviews) | Construct scores, themes |
| **RQ6** | Is it *fast enough* to use live? | Operational feasibility | Latency instrumentation | Median latency vs rest window |

RQ1 is the original study (see [RQ1.md](RQ1.md)). RQ2–RQ6 are new and are
specified below.

---

## RQ1 — Perceived Efficacy of Multi-Modal Fusion

*(Existing study — summarised here; full protocol in [RQ1.md](RQ1.md).)*

> **RQ1.** Does coaching advice generated from the **fused** payload
> `{CV, HRV, IMU}` get rated higher by certified coaches than advice generated
> from any single modality, on specificity, actionability, technical
> correctness, and novelty?

- **H1:** Fused advice out-ranks every single-modality condition on each
  criterion. **H0:** no mean-rank difference across the four modes.
- **Design:** within-subjects, blinded; conditions `cv / hrv / imu / fused`;
  identical LLM + prompt, only the payload subset varies; per-session shuffle.
- **Sample:** n = 30 sessions × 3 raters × 4 modes × 4 criteria = 1,440 ratings.
- **Analysis:** Friedman χ² per criterion, Wilcoxon post-hoc (Bonferroni),
  Kendall's W effect size, ICC(3,k) inter-rater reliability.

**Refinement for this dissertation:** RQ1 now explicitly depends on **RQ2** for
construct validity (the modalities being fused must be shown to measure what
they claim) and is reframed as a study of *perceived* quality, distinct from
the *measured* validity established in RQ2 and the *adopted* value in RQ5.

---

## RQ2 — Technical Validity of the Sensing Pipeline

> **RQ2.** How accurately does Alion detect and classify boxing punches and
> their key kinematic events relative to manually-labeled ground truth, and how
> does accuracy vary by punch type and hand?

**Why it matters.** Every downstream claim (RQ1, RQ3, RQ4) assumes the system
measures punches correctly. The current heuristic detector has a self-reported
~30–40% error and has never been formally evaluated. RQ2 closes that gap and
turns "we built a detector" into "the detector performs at *X*, here is the
evidence." This is the question an examiner will press hardest on; answering it
pre-empts the challenge.

**Hypotheses.**
- **H2a (detection):** Punch-detection F1 against ground truth ≥ 0.80.
- **H2b (classification):** 6-class punch-type macro-F1 significantly above the
  16.7% random baseline (target ≥ 0.70).
- **H2c (timing):** Mid-stroke timestamp error (MSE) is comparable to the
  BoxingPro benchmark (0.13–0.22 ms across punch types, *Electronics* 2025
  Table 4), and follows the same pattern — lower error for cross/uppercut,
  higher for jab.

**Design.** Offline benchmark against a held-out, manually-labeled video set.
- **Stimulus data:** clips produced by `scripts/ml/split_punch_video.py` from
  the data-collection protocol (one long video per punch type per hand), plus
  public sets (Olympic Boxing, UCF101/HMDB-51 boxing clips) where licensing
  allows.
- **Ground truth:** manual labels (`data/labels/{session_id}.json`) — punch
  presence, type, and mid-stroke frame — annotated by the researcher and a
  second annotator on a 20% overlap subset for inter-annotator agreement.
- **System under test:** the live CV pipeline (MediaPipe Pose → heuristic
  detector → type classifier), and, as a second arm, the LSTM second-pass
  classifier (`punch_lstm_v1`) once trained.

**Metrics & analysis.**
| Sub-question | Metric | Analysis |
|---|---|---|
| Detection | Precision, Recall, F1; greedy time-window matching | Bootstrap 95% CI on F1 |
| Type classification | Confusion matrix, per-class + macro-F1 | McNemar vs heuristic baseline |
| Timestamp accuracy | MSE (ms) per punch type | Compare to BoxingPro Table 4 |
| Annotator reliability | Cohen's κ on the 20% overlap | Report κ |

**Contribution.** A defensible, quantified measurement-validity claim — the
empirical foundation the rest of the dissertation stands on. The existing
evaluation harness (`scripts/evaluate.py`) already implements the matching
logic; RQ2 is largely a matter of running it on labeled data and reporting
honestly.

---

## RQ3 — HRV Readiness & Within-Session Performance

> **RQ3.** Does pre-session HRV-derived readiness predict within-session
> performance decay (decline in punch output and velocity across rounds)?

**Why it matters.** The physiological dimension is Alion's headline
differentiator over BoxingPro. But "we collect HRV" is not a contribution —
"HRV readiness predicts performance, therefore the fusion is informative" is.
RQ3 tests whether the physiological signal carries genuine predictive value.

**Hypotheses.**
- **H3a:** Higher pre-session readiness (per-fighter z-scored RMSSD) is
  associated with *lower* round-over-round velocity decay (negative slope
  relationship).
- **H3b:** Readiness adds predictive value beyond punch count alone in a
  mixed-effects model with a per-fighter random intercept.
- **H0:** Readiness is uncorrelated with within-session performance decay.

**Design.** Repeated-measures observational study using the Polar H10
(in-session and pre-session HR) once hardware integration lands.
- **Predictor:** pre-session 5-minute resting readiness (RMSSD-based z-score,
  per-fighter once ≥5 baselines exist; cold-start clamp otherwise).
- **Outcome:** per-round performance markers — mean punch velocity, punch
  count, and the slope of velocity across rounds (the "decay" measure).
- **Unit of analysis:** session, nested within fighter.

**Analysis.** Linear mixed-effects model (`velocity_decay ~ readiness +
punch_count + (1 | fighter)`); report fixed-effect β, 95% CI, marginal/conditional
R². Supplementary repeated-measures correlation (Bakdash & Marusich) with
Pearson/Spearman r and Fisher CI, gated at n ≥ 10 sessions (the dashboard
already applies this gate).

**Contribution.** Empirical evidence that physiological state is informative for
combat-sports performance — validating the premise of the fusion that
distinguishes Alion from all prior boxing systems.

---

## RQ4 — Longitudinal Coaching Value

> **RQ4.** Over repeated sessions, do Alion's LLM-generated longitudinal
> observations align with independent coach assessments of the same fighters,
> and do coaches judge those observations actionable?

**Why it matters.** Longitudinal, cross-session analysis is the capability no
prior boxing system claims. RQ4 tests whether that capability produces
**accurate and useful** insight, not just more text.

**Hypotheses.**
- **H4a (alignment):** Agreement between the platform's longitudinal
  observations (trend direction, flagged issues) and blinded coach assessments
  of the same fighters exceeds chance (Cohen's κ > 0.4, "moderate").
- **H4b (actionability):** Coaches rate the observations actionable at a mean
  ≥ 4.0 / 5.0.
- **H0:** Observation–coach agreement is at chance level.

**Design.** For each fighter with ≥ 5 completed sessions:
1. The platform generates its longitudinal observation set (it already does
   this from the last 15 sessions).
2. ≥ 2 certified coaches *independently* assess the same fighter from the raw
   session history (blinded to the AI output) on the same dimensions.
3. A third step has coaches rate the AI observations for accuracy and
   actionability after revealing them.

**Analysis.** Cohen's / Fleiss' κ for categorical agreement; Likert summaries
for actionability; thematic notes on where AI and coaches diverge (the
divergences are themselves a finding — they map the boundary of what the system
gets right).

**Contribution.** Direct evidence for the longitudinal value proposition, the
single clearest novelty claim relative to BoxingPro.

---

## RQ5 — Adoption, Trust & Perceived Utility (DBA Core)

> **RQ5.** How do fighters, coaches, and gym managers evaluate Alion's perceived
> usefulness, ease of use, trust in AI-generated feedback, and intention to
> adopt — and how do these differ by role?

**Why it matters.** This is the question that makes the work a **DBA**
dissertation rather than a computer-science thesis. A technically valid system
that no one will adopt is a business failure. RQ5 examines the market and
organizational reality of multi-modal AI coaching.

**Theoretical frame.** UTAUT / Technology Acceptance Model constructs:
- **Performance Expectancy** (perceived usefulness for training outcomes)
- **Effort Expectancy** (perceived ease of use)
- **Trust** in AI-generated coaching feedback (a domain-specific addition —
  trust is the documented barrier to AI coaching adoption)
- **Behavioral Intention** to adopt
- **Facilitating Conditions** (does a gym have the staff/hardware to run it?)

**Design.** Convergent mixed-methods.
- **Quantitative:** a validated Likert survey (UTAUT item battery, adapted)
  administered to participants across all three roles after a structured
  hands-on session with the platform.
- **Qualitative:** semi-structured interviews (≈ 30–45 min) with a purposive
  subsample, exploring trust, perceived threat-to-expertise, and workflow fit.

**Analysis.**
- Quantitative: construct reliability (Cronbach's α ≥ 0.7); descriptive scores
  per construct; between-role comparison (Kruskal–Wallis, given small n);
  correlation of Trust → Behavioral Intention.
- Qualitative: reflexive thematic analysis (Braun & Clarke); themes triangulated
  against the survey constructs.

**Contribution.** The management/organizational finding: *whether, by whom, and
why* multi-modal AI coaching would be adopted in real gyms — and what that
implies for sports-technology product strategy. This is the dissertation's
business backbone.

---

## RQ6 — Operational Feasibility: Feedback Latency

> **RQ6.** What is the end-to-end latency of generating corner advice, and is it
> within the inter-round rest window (typically 60 s) required for live, between-
> rounds coaching?

**Why it matters.** BoxingPro's own evaluation found **Feedback Timing scored
lowest of all five criteria across every model tested** — latency is the field's
acknowledged open problem. Measuring and characterising it is a contained,
high-value contribution that engages directly with the prior benchmark.

**Hypotheses.**
- **H6a:** Median end-to-end advice latency < 60 s (one rest period) for at
  least one viable model configuration.
- **H6b:** Latency differs significantly by payload mode and by model
  (local small model vs cloud model).

**Design.** Instrument the `/sessions/{id}/advice` path; record wall-clock
latency across ≥ 100 generations spanning payload modes and at least two model
backends (e.g., local `gemma-4-e4b` vs a cloud Claude model). Hold prompt and
hardware constant within each arm.

**Analysis.** Median and IQR latency per (mode, model); Kruskal–Wallis across
modes; report the fraction of generations completing within the rest window.
Discuss the engineering levers (caching, streaming, model size, quantisation)
and their trade-offs against RQ1's quality scores — i.e., the quality/latency
frontier.

**Contribution.** A quantified quality-vs-latency trade-off curve for in-session
AI coaching, directly extending BoxingPro's identified limitation.

---

## 10. How the RQs De-Risk Each Other

The central risk the proposal review identified: *if RQ1 returns a null result
(fused advice not rated higher), does the dissertation collapse?* The six-RQ
structure is designed so the answer is **no**.

```
                 RQ2 (measurement validity)
                  │  underpins
                  ▼
   RQ3 ──┐    RQ1 (perceived quality)
 (physio)│        │
         ▼        ▼
        RQ4 (longitudinal value) ──► RQ5 (adoption / business)
                                         ▲
                       RQ6 (latency) ────┘
```

- **If RQ1 is null:** RQ2 (validity), RQ4 (longitudinal value), and RQ5
  (adoption) still stand as independent contributions. A null RQ1 becomes a
  *finding* — "modality fusion did not improve *perceived* advice quality in
  this sample, though it improved measured X / was valued for Y" — not a
  failure.
- **If RQ2 is weak:** the dissertation pivots to honest scoping ("detection is
  not a claimed contribution; we rely on established methods and report their
  limits") while RQ5's adoption finding is unaffected.
- **RQ5 always delivers:** the adoption/trust study produces a publishable
  management contribution regardless of every technical result — appropriate
  for a DBA.

This is the core argument for examiner confidence: **no single result can sink
the thesis.**

---

## 11. Contribution Statement

> While AIFit (Fieraru et al., 2021) demonstrated vision-based fitness coaching
> and BoxingPro (Zhu et al., 2025) established the IoT-LLM paradigm for
> boxing coaching at the single-punch level, both remain isolated research
> prototypes. **This dissertation contributes (1) a deployed, multi-role
> platform that fuses computer-vision, inertial, and heart-rate-variability data
> into LLM-generated combat-sports coaching; (2) a quantified validation of that
> platform's measurement accuracy, physiological predictive value, and
> longitudinal coaching utility; and (3) the first empirical study of whether and
> why combat-sports practitioners would adopt multi-modal AI coaching.** Together
> these position Alion as the first holistic, validated, and adoption-studied AI
> coaching platform for combat sports.

---

## 12. Scope, Assumptions & Limitations

Stated up front, honestly — these are the boundaries the defence will probe.

- **Detector accuracy is being established, not assumed.** Until RQ2 completes,
  no quantitative detection claim is made. The heuristic's prior ~30–40% error
  is acknowledged.
- **Synthetic IMU during bootstrap.** Until wrist sensors (WitMotion WT61C-BT)
  and the Polar H10 are fully integrated, the fused condition uses IMU
  synthesised from CV punches, introducing modality redundancy. RQ1/RQ3 results
  collected before hardware integration are labelled as such.
- **Performance "Output Index" has no physical units.** It is an ad-hoc ranking;
  RQ3 should adopt a literature-backed intensity metric (e.g., velocity-based
  load) before the defence.
- **Small, local participant pool.** Coaches and fighters are recruited from the
  local boxing community; findings may not generalise to MMA/kickboxing or other
  regions. Stated as an external-validity limit.
- **Single LLM sample per generation.** Cached advice is one draw from a
  non-deterministic model; documented with model + temperature.
- **DBA, not CS, framing.** The contribution is applied and managerial; the
  technical artifact is a means, and state-of-the-art detection accuracy is not
  the goal.

---

## 13. Ethics & IRB

- **Human participants:** coaches (raters/interviewees), fighters (data
  subjects), gym managers (survey). Requires GGU IRB review — informed consent,
  right to withdraw, de-identified storage.
- **Athlete data is sensitive.** Real athlete data collection is gated on the
  platform's security and encryption work (see `decisions/002-encryption-deferred.md`
  and the access-control hardening completed 2026-05). No real PHI is collected
  until that is in place.
- **AI-generated feedback is advisory.** The system is explicitly not a medical
  device and does not provide medical or injury diagnosis; this is stated to
  participants.
- **Data minimisation:** raters see only what the coaching task requires; survey
  and interview data are stored separately from performance data.

---

*Add results, instruments (survey battery, interview guide, rater orientation),
and analysis notebooks to `docs/studies/` and `data/studies/` as each RQ
executes.*
