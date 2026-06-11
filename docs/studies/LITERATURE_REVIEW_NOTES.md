# Literature Review Notes — Alion Dissertation
> Living document. Add new papers as they are reviewed.
> Last updated: 2026-05-21

---

## Table of Contents
1. [BoxingPro (Zhu et al., 2025)](#1-boxingpro-zhu-et-al-2025)
2. [AIFit (Fieraru et al., 2021)](#2-aifit-fieraru-et-al-2021)
3. [Reference Map — BoxingPro Citations](#3-reference-map--boxingpro-citations)
4. [Dissertation Structure Guide](#4-dissertation-structure-guide)
5. [Alion Positioning Statement](#5-alion-positioning-statement)

---

## 1. BoxingPro (Zhu et al., 2025)

**Full citation:**
> Zhu, M.; Huang, P.; Xu, X.; He, H.; Zhang, L. BoxingPro: An IoT-LLM Framework for Automated Boxing Coaching via Wearable Sensor Data Fusion. *Electronics* **2025**, *14*, 4155. https://doi.org/10.3390/electronics14214155

**Open access:** https://www.mdpi.com/2079-9292/14/21/4155

**PDF on file:** `/Users/mohamadidriss/Downloads/electronics-14-04155 (1).pdf`

**Status: Primary methodological benchmark for Alion.**

---

### 1.1 What It Does

BoxingPro is an IoT + LLM framework that:
1. Attaches **two WitMotion JY61 IMU sensors** to both hands of a boxer
2. Streams 9-axis kinematic data at **200 Hz via Bluetooth**
3. Records **200 FPS video** simultaneously (side-view, chest height)
4. Extracts biomechanical features from IMU + video pose estimation
5. Constructs structured **"kinematic prompts"** fed to an LLM
6. LLM generates **personalised, step-by-step coaching feedback** in natural language

---

### 1.2 IMU Hardware — Directly Validates Alion's Sensor Choice

BoxingPro used **WitMotion JY61** — the same JY61 family as the **WT61C-BT** purchased for Alion.

| Spec | Value |
|---|---|
| Accelerometer range | ±16 g |
| Gyroscope range | ±2000°/s |
| Sampling rate | Up to 200 Hz |
| Transmission | Bluetooth |
| Axes | 9 (accX/Y/Z, gyrX/Y/Z, pitch/roll/rawAngle) |

**Cite BoxingPro to justify the WT61C-BT sensor choice in your methods chapter.**

---

### 1.3 Signal Processing Pipeline — Adopt for Alion

#### Step 1 — IMU Preprocessing
- Noise reduction + sensor bias correction + normalisation
- Apply **5th-order Butterworth low-pass filter** to each kinematic attribute
  - *Citation for Butterworth filter:* Yu, B. et al. (1999) J. Appl. Biomech. 15, 318–329 [Ref 26]
- Standardise resulting dataset D

#### Step 2 — Key Timestamp Detection (Punch Segmentation)
Compute first discrete difference of preprocessed dataset D:
- Filter out entries with values below 0.001 (minor fluctuations) → dataset D'
- **Mid-stroke** = timestamp of maximum resultant acceleration
- **Initial position** = timestamp of minimum acceleration immediately *before* mid-stroke
- **Final position** = timestamp of minimum acceleration immediately *after* mid-stroke

> ⚠️ Jab has highest segmentation error (lowest peak acceleration, most linear trajectory). Needs special handling in Alion's punch segmentation.

#### Step 3 — Biomechanical Feature Extraction

| Feature | Formula |
|---|---|
| Max acceleration (3 axes) | max(\|D_accX\|), max(\|D_accY\|), max(\|D_accZ\|) |
| Max punch speed | D_acc[: midstroke] · T^d (integrate initial→mid-stroke) |
| Angular momentum | L = W · D_gyr |
| Torque | τ = dL/dT |

- Torque is a known determinant of punching force generation
  - *Citation:* Scattone-Silva, R. et al. (2012). Sci. Sport 27, e31–e37 [Ref 28]

#### Step 4 — Skeleton Joint Extraction from Video
- **MoveNet** (Google) via TensorFlow — selected for speed/accuracy balance
- MobileNetV2 backbone, 192×192×3 RGB input
- Outputs **17 body keypoints** with confidence scores
- 3.4M parameters; ~30 FPS on mobile; mAP 73.8% on COCO
- *Citation:* Bajpai, R. & Joshi, D. (2021). IEEE Trans. Instrum. Meas. 70, 2508511 [Ref 27]

#### Step 5 — LLM Prompt Construction ("Kinematic Prompt")

```
[Problem background]: A boxer executed a [PUNCH_TYPE]. Through the analysis
based on the datasets collected from the IMUs held in his left and right hands,
we find the following characteristics:

[Key data]:
  <max acceleration of the punching hand>: X-axis: ... m/s², Y-axis: ... m/s², Z-axis: ... m/s²
  <duration of the punch>: ... milliseconds
  <speed in the middle of the stroke>: X: ... m/s, Y: ... m/s, Z: ... m/s
  <torque in the middle of the stroke>: X: ... Nm, Y: ... Nm, Z: ... Nm

[Task]: Please analyse this punch according to the characteristics,
and give specific advice for improvement if possible.
```

---

### 1.4 Dataset Design — Template for Alion Data Collection

| Parameter | BoxingPro | Alion Target |
|---|---|---|
| Subjects | 18 (4F, 14M, age 5–40) | >30, broader age/gender mix |
| Skill levels | Novice (13), Beginner (1), Professional (4) | Novice, Intermediate, Advanced, Elite |
| Punch types | 6 (Jab, Cross, Lead/Rear Hook, Lead/Rear Uppercut) | Same 6 + combinations |
| Repetitions | 3 per punch per subject | 5+ per punch per subject |
| Total instances | 324 | >1000 |
| Sensor placement | Both hands | Both hands + optional torso |

**6 punch types used (standardise these in Alion):**
- Jab — straight punch, lead hand
- Cross — straight punch, rear hand
- Lead Hook — circular punch, lead hand
- Rear Hook — circular punch, rear hand
- Lead Uppercut — upward punch, lead hand
- Rear Uppercut — upward punch, rear hand

---

### 1.5 LLM Comparison — Benchmark Scores to Beat

Evaluated by 4 professional boxers on a Likert 0–5 scale across 5 criteria:

| Criterion | Llama2-7B | ChatGLM | DeepSeek-V3 | Llama2-7B Fine-Tuned |
|---|---|---|---|---|
| Biomechanical Correctness (B) | 3.2 | 3.5 | **4.1** | 3.8 |
| Quantifiable Metrics (Q) | 2.9 | 3.1 | **4.2** | 4.1 |
| Operability (O) | 3.0 | 3.4 | 3.9 | **4.3** |
| Feedback Timing (F) | 3.1 | 3.0 | **4.0** | 3.5 |
| Understandability (U) | 3.3 | 3.6 | 4.3 | **4.5** |

**Key findings:**
- DeepSeek-V3 and Fine-Tuned Llama2-7B significantly outperformed base models
- **Feedback Timing (F) scored lowest across ALL models** — real-time latency is the field's biggest unsolved problem
- LoRA fine-tuning on 1500 boxing-specific prompt-suggestion pairs improved Operability and Understandability most

**Alion evaluation target:** B ≥ 4.1, Q ≥ 4.2 (match or exceed DeepSeek-V3 baseline)

**Adopt this 5-criterion rubric verbatim for Alion's expert evaluation chapter.**

---

### 1.6 Temporal Detection Accuracy (Punch Segmentation MSE)

| Punch Type | Average MSE (ms) | SD |
|---|---|---|
| Jab (J) | 0.218 | 0.351 |
| Cross (C) | 0.151 | 0.233 |
| Lead Hook (LH) | 0.222 | 0.297 |
| Rear Hook (RH) | 0.162 | 0.271 |
| Lead Uppercut (LU) | 0.196 | 0.196 |
| Right Uppercut (RU) | **0.134** | 0.182 |

- Right Uppercut and Cross: best accuracy (dominant hand, sharper acceleration peaks)
- Jab: worst accuracy (linear trajectory, lower peak acceleration)
- Left-hand strikes consistently higher error (most subjects right-handed)

---

### 1.7 Limitations of BoxingPro — Gaps Alion Fills

| Limitation | How Alion Addresses It |
|---|---|
| Real-time latency (LLM inference delay) | Streaming API + pre-cached suggestions per round |
| Small dataset (324 instances, 18 subjects) | Larger collection, multiple gyms via platform |
| Single-session only | Longitudinal tracking across weeks/months |
| No physiological context | HRV integration (Polar H10, arriving 2026-05-16) |
| No fatigue modelling | HRV + round-by-round performance degradation |
| Hands-only sensor placement | Extensible to torso/feet |
| No role hierarchy | Fighter, Coach, Referee, Gym Manager roles |
| Research prototype | Deployed SaaS platform (Railway, web dashboard) |
| Gender/age bias | Broader recruitment via gym network |

---

### 1.8 Future Work Directions (from BoxingPro)
1. Optimise LLM component for real-time latency (quantisation, smaller models)
2. Expand dataset — more diverse boxers and punch variations
3. Integrate into **augmented reality (AR) glasses** for immersive in-training feedback

---

## 2. AIFit (Fieraru et al., 2021)

**Full citation:**
> Fieraru, M.; Zanfir, M.; Pirlea, S.C.; Olaru, V.; Sminchisescu, C. AIFit: Automatic 3D Human-Interpretable Feedback Models for Fitness Training. In *Proceedings of the IEEE/CVF CVPR*, Virtual, 19–25 June 2021; pp. 9919–9928.

**Open access PDF:** https://openaccess.thecvf.com/content/CVPR2021/papers/Fieraru_AIFit_Automatic_3D_Human-Interpretable_Feedback_Models_for_Fitness_Training_CVPR_2021_paper.pdf

**Status: Key theoretical framework paper. Top-tier venue (CVPR 2021).**

---

### 2.1 What It Does

AIFit is the first end-to-end system for automatic 3D pose-based coaching feedback from a standard RGB camera:
1. Reconstructs 3D human pose and shape from **monocular RGB video** (GHUM / SMPL-X body models)
2. Automatically segments exercise repetitions
3. Learns a **statistical reference distribution** from instructor demonstrations
4. Compares trainee motion against reference → localized deviation detection
5. Outputs **natural language feedback** grounded spatially and temporally in the trainee's own video

**Dataset introduced: Fit3D**
- 3M+ images, 611 sequences, 13 subjects
- 37+ exercise types, full MoCap ground truth
- Available at: https://fit3d.imar.ro

### 2.2 Key Result
~80% accuracy compared to gold-standard MoCap — monocular RGB pose estimation is good enough for practical coaching

### 2.3 Limitations (Why Alion Uses IMUs Instead)
- Camera field-of-view and occlusion problems — **gloves/contact block body tracking in boxing**
- No precise kinematic data (acceleration, velocity) — camera cannot measure force/torque
- Privacy concerns with video recording athletes
- Limited to pre-defined, cyclical fitness exercises — **boxing is non-cyclical and reactive**

### 2.4 How It Fits Into the Dissertation
AIFit → BoxingPro → Alion is the clear **intellectual lineage**:
- AIFit proved AI coaching feedback from sensor data is feasible (fitness, vision-based)
- BoxingPro extended this to boxing with IMUs + LLMs (punch level)
- Alion extends further to **full training sessions, physiological monitoring, and multi-role platform** (session + longitudinal level)

---

## 3. Reference Map — BoxingPro Citations

### Tier 1 — Must Cite in Alion Dissertation

| # | Authors | Year | Title (short) | Journal/Conf | Why It Matters |
|---|---|---|---|---|---|
| [1] | Worsey et al. | 2020 | Wearable IMU config for punch classification | *IoT* 2020, 1, 360–381 | Validates IMU-based punch classification; evaluates sensor placements |
| [3] | Alevras et al. | 2022 | Epidemiology of injuries in amateur boxing | *J. Sci. Med. Sport* 25, 995–1001 | Establishes injury problem motivating coaching tech |
| [8] | Fieraru et al. | 2021 | AIFit (CVPR) | CVPR 2021, pp. 9919–9928 | Vision-based coaching baseline; intellectual predecessor |
| [22] | Hanada et al. | 2021 | Boxersense — punch detection with IMUs | ABC 2021, pp. 95–114 | IMU punch detection feasibility in boxing |
| [28] | Scattone-Silva et al. | 2012 | Acceleration, peak torque in karate athletes | *Sci. Sport* 27, e31–e37 | Justifies torque as a coaching metric for striking sports |

### Tier 2 — Strong Supporting References

| # | Authors | Year | Title (short) | Journal/Conf | Why It Matters |
|---|---|---|---|---|---|
| [4] | Gupta & Gupta | 2021 | YogaHelp — motion sensors for yoga feedback | *IEEE Trans. Artif. Intell.* 2, 362–371 | IMU coaching proven in yoga; generalises the paradigm |
| [7] | Wang et al. | 2019 | AI Coach — deep pose estimation for athletics | ACM Multimedia 2019, pp. 374–382 | Early AI coaching system; historical lineage |
| [9] | Dittakavi et al. | 2022 | Pose Tutor — explainable pose correction | CVPR 2022, pp. 3540–3549 | Explainability in AI coaching; relevant to interpretability |
| [13] | An et al. | 2024 | IoT-LLM — IoT reasoning with LLMs | arXiv 2024, 2410.02429 | Theoretical framing: IoT sensors as "sensory organs" for LLMs |
| [18] | Bao et al. | 2023 | FusePose — IMU-Vision fusion for pose estimation | *IEEE Trans. Multimed.* 25, 7736–7746 | IMU + camera fusion; relevant if Alion adds video |
| [21] | Hammerla et al. | 2016 | Deep/CNN/RNN models for HAR with wearables | arXiv 2016, 1604.08880 | Foundational deep learning on wearable IMU time-series |
| [26] | Yu et al. | 1999 | Butterworth low-pass filter cutoff frequency | *J. Appl. Biomech.* 15, 318–329 | Signal processing — filter design for IMU data |

### Tier 3 — Background / Optional

| # | Authors | Year | Title (short) | Notes |
|---|---|---|---|---|
| [5] | Qi et al. | 2018 | GPARMF — hybrid sensor fusion for gym HAR | *IEEE Internet Things J.* 6, 1384–1393 |
| [6] | Gochoo et al. | 2019 | Privacy-preserving yoga posture recognition | *IEEE Internet Things J.* 6, 7192–7200 |
| [14] | Chen & Yang | 2020 | Pose Trainer — exercise posture correction | arXiv 2020 |
| [15] | Kim et al. | 2021 | FIXMYPOSE — pose correction captioning | AAAI 2021 |
| [19] | Wozniak et al. | 2021 | Body pose prediction with RNN + body sensors | *IEEE Trans. Ind. Inform.* 17, 2101–2111 |
| [20] | Phukan et al. | 2022 | CNN for human activity recognition | *IEEE Sens. J.* 22, 21816–21826 |
| [23] | Ji et al. | 2024 | HARGPT — LLMs as zero-shot HAR recognisers | arXiv 2024 |
| [25] | Wu et al. | 2023 | Embodied task planning with LLMs | arXiv 2023 |
| [27] | Bajpai & Joshi | 2021 | MoveNet — joint profile prediction | *IEEE Trans. Instrum. Meas.* 70, 2508511 |

---

## 4. Dissertation Structure Guide

### Chapter 2 — Literature Review

```
2.1  Vision-Based Sports Coaching Systems
     → AIFit [Fieraru 2021], Pose Tutor [Dittakavi 2022], AI Coach [Wang 2019]
     → Limitation: occlusion, no kinematic data, not suited to dynamic combat sports

2.2  Wearable Sensor-Based Activity Recognition in Sport
     → Foundational deep learning: Hammerla 2016
     → General sport: YogaHelp [Gupta 2021], GPARMF [Qi 2018]
     → Boxing-specific: Worsey 2020 (punch classification), Hanada 2021 (Boxersense)
     → Limitation: classify "what" was done; cannot explain "how" to improve

2.3  IoT-LLM Integration for Physical Coaching
     → IoT-LLM paradigm: An et al. 2024
     → Boxing application: BoxingPro [Zhu 2025] ← PRIMARY BENCHMARK
     → Limitation: punch-level only; no physiology; no longitudinal tracking; no role hierarchy

2.4  Injury Prevention and the Coaching Gap
     → Alevras 2022 (injury epidemiology in amateur boxing)
     → Gap: no deployed platform integrates biomechanics + physiology + multi-role coaching

2.5  Summary of Gap and Alion's Contribution
     → Longitudinal tracking across sessions
     → HRV-based physiological monitoring
     → Multi-role platform (fighter, coach, referee, gym manager)
     → Deployed production system
```

### Chapter 3 — Methods (Drawing from BoxingPro)

1. **IMU Hardware:** WitMotion WT61C-BT (same JY61 family as BoxingPro) — cite [BoxingPro] + [Worsey 2020]
2. **Preprocessing:** 5th-order Butterworth low-pass filter — cite [Yu 1999]
3. **Punch Segmentation:** Key timestamp detection via first discrete difference — cite [BoxingPro]
4. **Feature Extraction:** Max acceleration, speed, angular momentum, torque — cite [BoxingPro] + [Scattone-Silva 2012]
5. **LLM Coaching Module:** Kinematic prompt template — adapt from [BoxingPro]
6. **HRV Module:** Polar H10, rMSSD, pNN50 — unique Alion contribution
7. **Platform Architecture:** Multi-role SaaS — unique Alion contribution

### Chapter 4 — Evaluation

Use BoxingPro's **5-criterion Likert rubric** for expert evaluation:

| Criterion | Code | Description |
|---|---|---|
| Biomechanical Correctness | B | Technical accuracy of the advice |
| Quantifiable Metrics | Q | Use of data-driven, measurable insights |
| Operability | O | Actionability — can the boxer actually do it? |
| Feedback Timing | F | Relevance to the phase of the punch |
| Understandability | U | Clarity and conciseness of language |

**Target scores (to claim improvement over BoxingPro):**
- B ≥ 4.1, Q ≥ 4.2 (match DeepSeek-V3)
- O ≥ 4.3, U ≥ 4.5 (match Fine-Tuned Llama2-7B)
- F > 4.0 (beat ALL existing models — latency is the open problem)

---

## 5. Alion Positioning Statement

> *"While BoxingPro (Zhu et al., 2025) established the IoT-LLM paradigm for boxing coaching at the punch level — demonstrating that wearable IMU data can be translated into expert-validated coaching feedback with average scores exceeding 4.0/5.0 — it remains limited to isolated punch analysis within a single session. Alion extends this paradigm to the session and longitudinal level, integrating HRV-based physiological monitoring (Polar H10), multi-round tactical planning, and a multi-role platform architecture serving fighters, coaches, referees, and gym managers within a unified, deployed production system. This positions Alion as the first holistic AI coaching platform for combat sports that bridges biomechanical analysis, physiological monitoring, and tactical coaching within a single operational deployment."*

---

## 6. Comparative Table — Alion vs. Existing Systems

| Dimension | AIFit (2021) | BoxingPro (2025) | **Alion** |
|---|---|---|---|
| Sport | General fitness | Boxing | Boxing / combat sports |
| Sensor modality | RGB camera | IMU + video | IMU + HRV wearable |
| Analysis granularity | Exercise rep | Single punch | Full session + longitudinal |
| Physiological data | None | None | HRV (recovery, fatigue) |
| Coaching feedback | 3D pose deviation | LLM natural language | LLM + round plans + history |
| User roles | Single user | Single user | Fighter, Coach, Referee, Gym Manager |
| Session context | Single exercise | Single punch sequence | Multi-round training session |
| Longitudinal tracking | No | No | Yes — across weeks/months |
| Deployment | Research prototype | Research prototype | Production SaaS (Railway) |
| Dataset scale | 3M+ images, 37 exercises | 324 punches, 18 subjects | TBD — to be collected |
| Evaluation | MoCap accuracy ~80% | Expert Likert 4.0–4.5/5 | Expert Likert (target ≥4.1) |

---

*Add new papers to this document as the review expands. Sections to add: HRV in sport, round plan / tactical coaching literature, combat sports performance analytics.*
