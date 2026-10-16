# Surgical Knowledge System: Phase 0 Research Report

> **Purpose:** an analysis of the idea document (`Surgical_Knowledge_System_Idea.md`) plus research findings, to support the discussion before the MVP plan.
> **Status:** findings and options only. **No decisions have been made.** Every decision point is listed in §9 for the project owner.
> **Date:** 2026-10-16
> **Sources:** four parallel research streams: (1) a surgical expert advisory panel (MIS/robotic surgeon, surgical data scientist, clinical-safety/med-ed lead); (2) open datasets and licensing; (3) AI/tech stack; (4) market, novelty, standards and regulation. URLs are kept where they were given. Items marked **[UNVERIFIED]** must be checked before we rely on them.

---

## 1. Executive summary (the 12 things that matter most)

1. **The core idea is sound and differentiated.** Every commercial player (Theator, Medtronic Touch Surgery, Intuitive Case Insights, Caresyntax, OR Black Box, Anaut, Jmees) captures the **"what"**. None of them systematically elicits, structures and verifies **case-specific surgeon reasoning (the "why") linked to video evidence**. The differentiator is the **elicitation loop**, not the video AI.
2. **The claim "no existing system does this" should be softened.** Researchers already elicit surgeon reasoning against video: cognitive task analysis (Madani 2015, Dias 2021), iViewExpert, ReflectOR (2026), and SUREON (2026), which mines reasoning from lecture narration. What is new is the **combination and the automated workflow**.
3. **No open surgical dataset contains real intra-operative surgeon speech.** We verified this directly: the Cholec80 MP4s have no audio track. The audio pipeline (§8.3 of the idea doc) cannot be demonstrated on real OR audio from open data. Workarounds exist (§4.3).
4. **Almost all open surgical data is non-commercial** (CC BY-NC-SA and similar). The main permissive exceptions are **GraSP / PSI-AVA (RARP, MIT licence)**, **RARPL (RARP, CC BY 4.0)** and **Cataract-1K (CC BY 4.0)**.
5. **There is a real tension over the choice of surgery X** (§9, D1):
   - The **surgeon panel** recommends **laparoscopic cholecystectomy**: best data, clearest demo, a ready-made "rule book" (Tokyo Guidelines 2018, critical view of safety), and Japanese-led standards. But its data is **non-commercial only**.
   - The **dataset research** recommends **RARP (urology)** on GraSP: fits the "urology / robotics" direction, has an MIT licence and procedure-specific models. But it has only **13 full videos** and **no bleeding/event labels**.
6. **"Obstacle → decision" captures rescue, but expert judgement is mostly anticipation.** Many of the best decisions leave no visible obstacle: preventive moves, deliberate non-action, bail-out choices. The knowledge unit needs to be extended (§3.1).
7. **The post-op window of 10–20 minutes is optimistic.** Realistically, a surgeon will answer **1–3 questions in under 3 minutes** on most days. **Tap-first, voice-optional** works better than voice-first.
8. **The biggest Japan-specific risk is medico-legal discoverability.** A timestamped record of "why I did this" next to a complication can be used in litigation (there is precedent with Medical Accident Investigation System reports). Governance design matters as much as the AI.
9. **Regulation is manageable if the product stays "education/reference".** In Japan, MHLW's case list puts education material and recorded-surgery viewing **outside** device regulation. Live intra-op alerts and patient-specific "likely obstacle" predictions move toward **SaMD**.
10. **Off-the-shelf frontier VLMs are poor at surgical phase recognition.** Gemini 3.1 Pro scores a macro-F1 of about 0.47 on Cholec80 and GPT-5.1 about 0.36; trained models reach about 0.85+. The pragmatic stack is **hybrid**: trained phase model + detector + VLM only on short candidate clips + LLM for questions and extraction.
11. **Fine-grained AI is immature.** Action-triplet recognition F1 is about 22–23% on HeiChole. Showing "instrument + action + target" to surgeons now risks losing their trust.
12. **The biggest unknown is human, not technical.** Will surgeons answer, and under what data-governance terms? The panel strongly advises a **Wizard-of-Oz validation with 5–10 surgeons** early.

---

## 2. What the idea document gets right (keep)

- **Human-in-the-loop** with **trust/provenance labels** on every fact.
- **"Reference, not instruction"**: important for regulation and for trust.
- **Keeping multiple viewpoints** instead of forcing one "correct" answer.
- **Each hospital owns its knowledge.**
- **Never interrupting the surgeon during surgery** (record-only live pipeline). This is also the correct regulatory guardrail.
- **Live bookmarks** ("mark this").
- **Separating the rule book (template) from the core engine.** This is the key to the "one system, many surgeries" scalability claim.
- **The offline reviewer pipeline.** The expert panel thinks this is probably where most early value lies: no OR integration and no time pressure.
- A clear **MVP exclusion list** (§13.4).

---

## 3. Critical analysis and consequences

### 3.1 The knowledge model (clinical validity)

| Gap in the current model | Example | Consequence if ignored |
|---|---|---|
| **Anticipatory / preventive decisions** | Retracting differently because of a fatty hilum; fundus-first before trouble starts | The deviation detector misses most expert judgement |
| **Deliberate non-action / bail-out** | Not clipping until CVS is achieved; choosing subtotal cholecystectomy | The most valuable safety decisions are invisible |
| **Who acted** | Resident → attending takeover; bedside assistant (off-screen) | Long step durations get mislabelled as "difficulty" |
| **Off-screen physiology** | Anaesthesia events, raising/lowering pneumoperitoneum pressure | Decisions are attributed to the wrong cause |
| **Pre-op context and plan** | BMI, prior surgery, cholecystitis grade, MRI/PSA; nerve-sparing plan | Much of the reasoning happens *before* incision |
| **Delayed outcomes** | Bile leak, positive margins, continence at 3–12 months, Clavien-Dindo at 30 days | "What works" pattern knowledge has no real outcome data |
| **Cause attribution** | Patient-driven difficulty vs event vs surgeon-induced error | A clinical and **legal** distinction |
| **Recall / hindsight bias** | Post-hoc rationalisation | Needs a cued-recall question design |

**Revised unit proposed by the panel:**

`Context (incl. pre-op plan) → Situation/Cue → Anticipation/Plan → Action OR deliberate non-action (+ who) → Immediate result → Delayed outcome (linked later) → Evidence`

The panel also proposes adding **"decision points without an obstacle"** as first-class events, triggered from rule-book checkpoints. Example: "CVS achieved? How did you confirm it?"

The idea doc's example (a second stitch versus pressure) is too thin to impress surgeons. The demo should use a real judgement call.

### 3.2 "Deviation = obstacle" is noisy

- A step that runs long usually means **teaching or a resident handover**, not difficulty.
- **False positives** (trivial ooze flagged as "bleeding") are the fastest way to lose surgeons.
- Detection should **fuse several weak signals** (blood-in-view ratio, suction/irrigation present, "careful/bleeding" utterances, duration z-score), then confirm with a VLM on the clip, then confirm with a human.

### 3.3 Surgeon time and behaviour

- **Right after a case:** closing or supervising closure, sign-out, post-op orders, the **family explanation (often showing the specimen, common in Japan)**, the operative record (often hand-drawn in Japan), and turnover.
- **Realistic load:** **1–3 questions, under 3 minutes**, and zero on bad days.
- **Format:** **tap-first** confirmation of an AI draft ("cystic artery branch bleeding, controlled with clip ✓ / edit"), with **voice optional** for the "why". Speaking reasoning aloud in a corridor is socially awkward in Japan. Offer evening batches or the weekly case conference (カンファレンス) as alternatives.
- **What makes surgeons stop answering:** false positives, generic questions, audit-like questions ("Could this have been avoided?"), re-entering what is already in the op note, and no visible payoff.
- **Give something back immediately:** an auto-drafted op-record timeline with key frames, a 3-minute highlight reel for teaching or conferences, and help finding their cleanest cases for **ESSQS (技術認定, the JSES skill-qualification system)**. ESSQS is a real pain point: the pass rate is about 20–40% and referee agreement is weak.

### 3.4 Trust

- **What builds trust:** clips that start at exactly the right second, correct step labels, **the voice and name of a respected surgeon**, honest sample sizes ("3 cases", not "18%"), and visible provenance.
- **What gets the product dismissed:**
  - one wrong anatomy label (e.g. calling the common bile duct the cystic duct);
  - banal LLM summaries;
  - **an LLM-invented rationale the surgeon never gave**;
  - percentages from tiny samples;
  - anything that sounds like a recommendation.
- **The "wow" moment for surgeons, per the panel:** a surgeon asks *"inflamed Calot's triangle, couldn't get CVS: what did others do?"* and gets back four 20-second clips from different cases. Each clip comes with the operating surgeon's own 15-second voice explanation, the bail-out chosen, and the outcome.
  - Runner-up: the trainee **"What would you do?"** pause-and-predict mode.
  - The animated knowledge graph impresses **investors**, not surgeons.

### 3.5 Medico-legal and cultural (Japan)

- **Discoverability.** In malpractice judgments that cited Medical Accident Investigation System reports, 9 of 15 reports were cited as evidence of negligence, 80% introduced by families (Ohira et al., JMA Journal). Recorded reasoning about complications is far more pointed than a committee report.
- **Design implications:**
  - Keep the education knowledge base separate from the medical record.
  - Write retention and access policies.
  - Let surgeons keep answers private or unpublished, and retract them.
  - De-identify the shared library.
  - Never ask "avoidability" questions about a surgeon's own complications.
  - Get a **Japanese medical-law opinion before any hospital pilot**.
- **OR audio** can capture scolding of juniors (a パワハラ / harassment risk), which drives staff to refuse consent. Make audio opt-in per case and delete raw audio by default.
- **Hierarchy (医局).**
  - Juniors won't contradict their professor on record.
  - Reviewers won't criticise a senior's case, so "Would you do the same?" will get polite non-answers. Ask instead: "What options exist here and when would you choose each?"
  - Anonymise the operator for reviewers.
  - Let the department head own the "Expert-validated" label.

### 3.6 Patient-similarity briefing

Open datasets have **no clinical metadata** (age, BMI, history). In the MVP, the "enter patient details → similar cases" briefing can only be **procedure-level**, not patient-level. A patient-specific "likely obstacles" briefing is also the feature closest to **SaMD** territory (§7).

### 3.7 Pattern knowledge from one hospital

Small numbers and confounding make rates misleading. The panel advises showing **counts and clips, not percentages**, until the numbers are large.

---

## 4. Data findings

### 4.1 Candidate datasets by surgery

| Surgery | Best datasets | Size | Key labels | Licence |
|---|---|---|---|---|
| **Lap cholecystectomy** | Cholec80, CholecT50, Cholec80-CVS, CholecTrack20, HeiChole, Endoscapes2023, SAGES CVS 2024 | 80 full videos (Cholec80); 33 (HeiChole); 1,000 CVS clips | Phases, tools, triplets, CVS, **bleeding/smoke flags (CholecTrack20)**, skill scores (HeiChole) | **All NC** (CC BY-NC-SA / NC) |
| **RARP (urology)** | **GraSP**, PSI-AVA, **RARPL**, SAR-RARP50, ESAD/MESAD | 13 full videos / 32.4 h (GraSP); 10 patients (RARPL) | 11 phases, 21 steps, instrument segmentation, atomic actions; **no bleeding/event labels** | **GraSP / PSI-AVA: MIT**; RARPL: CC BY 4.0; others NC |
| **Lap hysterectomy** | AutoLaparo, GynSurg, LapGyn6-Events | 21 full videos (AutoLaparo); 152 (GynSurg) | 7 phases; **bleeding/smoke events (GynSurg)** | All NC (GynSurg is NC-ND) |
| **Gastric bypass** (reference) | MultiBypass140 | 140 full videos / 214 h | 12 phases, 46 steps, **adverse events with severity 0–5**, the best "obstacle" model | NC |
| **Robotic partial nephrectomy** | None found | — | — | — |

### 4.2 Datasets with annotated bleeding or adverse events

MultiBypass140 (the best fit for the obstacle concept), GynSurg, LapGyn6-Events, SurgBlood (test set only), CholecTrack20 (per-frame bleeding flag), SARAS-MESAD ("SuckingBlood"). **All are non-commercial.**

The other obstacle types (long step, missing step, extra step, out-of-order step) need no event labels. They come from comparing predicted steps against the rule book.

### 4.3 Audio: the hard gap

- No open clinical dataset has OR speech. The closest options:
  - **MM-OR** (real OR mics, but phantom knee surgery; terms unknown);
  - **the USC/Cedars feedback corpus** (real, on request only);
  - **lecture transcripts** (SurgLaVi-β, Surg-QA: post-hoc narration, NC).
- **Workarounds, in order of realism:**
  1. **Surgeon think-aloud voice-over.** A partner surgeon narrates an open video as if live, in Japanese and/or English. You own the recording. Present it transparently as a reconstruction.
  2. **Scripted TTS** at annotated timestamps, for pipeline testing.
  3. **Lecture-transcript corpora** to train and evaluate the utterance classifier (internal R&D only, NC).
  4. **Product path:** real lapel-mic recordings through a hospital partner or S-access JAPAN, with IRB approval and consent.

### 4.4 Licensing consequences (not legal advice)

- **Internal R&D** on NC data is generally fine.
- **An external investor or customer demo by a for-profit company** is arguably commercial use. Get **written permission from the licensor** (e.g. CAMMA/Unistra for the Cholec80 family) before showing NC-derived results externally.
- **A product** cannot ship models trained on NC data. Most public surgical weights (SurgVLP, SurgeNet, Rendezvous) are **also NC**.
- **The GraSP MIT licence** is a software licence applied to patient video. Get written confirmation from BCV Uniandes, and check the scope of patient consent, before relying on it commercially.

### 4.5 Japan data route

- **S-access JAPAN** (NCC Hospital East + JSES + AMED) is a national surgical-video database explicitly for **industrial/commercial use**, by application. It reportedly holds over 6,000 cases with annotations. Fees, eligibility and whether audio is included are **[UNVERIFIED]**.
- **Medicaroid's hinotori MINS** platform is open to third-party AI, making it a potential data partner.

---

## 5. Technology findings

### 5.1 Recommended pattern (from the tech research): a hybrid; don't train big models, don't rely on the VLM alone

| Layer | Approach | Notes |
|---|---|---|
| Phase/step | Frozen frame features (SurgeNet / DINOv2) at 1 fps → small **causal MS-TCN** head trained on the chosen dataset | Trains in minutes to hours; about 88–93% accuracy on Cholec80 for this class of model |
| Instruments | Fine-tune **RF-DETR** (Apache-2.0) or YOLO11 (AGPL, so needs a commercial licence later) | 2–6 GPU-hours |
| Bleeding/events | **Heuristic fusion** (blood ratio, suction, utterances, duration) + VLM confirmation on the clip | No mature open bleeding model with permissive weights |
| Clip description | **Gemini** (native video, clip offsets) on 30–90 s candidate clips only; Qwen3-VL-8B as a local fallback | Weak at phases zero-shot; fine for "what changed in this clip" |
| ASR | **kotoba-whisper-v2.2** (JA, Apache-2.0), faster-whisper large-v3 (mixed JA/EN), ReazonSpeech; **AmiVoice medical** later | Glossary-biased decoding + LLM post-correction |
| Diarization | pyannote community-1 (CC BY 4.0) | The panel suggests cutting this from the MVP |
| LLM | `claude-haiku-5-5` (utterance classification), `claude-sonnet-5-5` (question phrasing, answer extraction via structured outputs), `claude-opus-5-5` (offline rule-book drafting with surgeons) | Rank questions **deterministically in code**; the LLM only phrases them |
| Storage | **PostgreSQL + pgvector**, property graph in tables (entities/edges), PROV-O-style provenance, Media Fragment URIs for evidence | Neo4j is the alternative; JSON-LD export gives a migration path to RDF |
| Replayer | The browser `<video>` is the master clock; backend pushes media-time-stamped events over **SSE**; heavy results **precomputed** | No WebRTC/GStreamer needed for the MVP |
| Frontend | Next.js + Tailwind/shadcn; Cytoscape.js graph; **PWA** answer screen (MediaRecorder) opened by QR code | No React Native needed |
| Compute | One RTX 4090 / L4 (24 GB) handles 1 fps inference; VLM via API or a second GPU | Cloud GPUs are cheap per hour [prices UNVERIFIED] |

### 5.2 Model licensing

Nearly all surgical-specific weights are **non-commercial**. A **commercial-safe path** would be general backbones (DINOv2, SigLIP) plus RF-DETR, trained on owned or licensed data. The DINOv3 licence is **[UNVERIFIED]**.

### 5.3 Demo reliability tricks

- **Precompute and reveal**, with an optional "true-live" toggle for the light models.
- **1–2 "golden cases"** whose outputs have been hand-checked.
- **Cached LLM responses** as a fallback for each question and answer.
- **Pre-cut clips** with Media Fragment links.
- **Seed the graph** with 5–10 offline cases so the library and "Ask" have content.
- **Run everything on one machine**; venue Wi-Fi must never be a single point of failure.

---

## 6. Competitive landscape and IP

| Player | Captures | Relevance |
|---|---|---|
| **Theator** | Steps, events, AI op-note signed post-op; Oracle Health partnership (Jun 2026); 600k+ procedures | **Closest threat.** The surgeon already signs its AI op-note right after surgery, the natural place to add "why?" prompts. **Large patent portfolio**: decision junctions, event detection, cross-patient compilations of the same event |
| Medtronic Touch Surgery | 14 AI algorithms; positioned as "education & training only" | Validates the education positioning |
| Intuitive (DV5, My Intuitive+, Case Insights) | Phase segmentation + kinematics | Owns da Vinci data |
| OR Black Box (SST) | OR audio/video, de-identification of voices | Precedent for audio de-identification |
| Anaut, Jmees (JP) | Approved intra-op SaMD (anatomy) | They do "what"; not competitors on "why" |
| Medicaroid MINS, Olympus, J&J Polyphonic | Data platforms open to third-party apps | **Potential partners / distribution** |
| Research: SUREON, ReflectOR, CTA (Dias, Madani), iViewExpert | Reasoning from narration / audio / interviews | Prior art; ReflectOR is very close to the audio idea |

**Consequence:** the obstacle library and side-by-side comparison features overlap with Theator's patents. A **freedom-to-operate (FTO) review** is needed before commercialisation. It is not needed for the MVP demo itself.

**Possible positioning (from the research):** *"A vendor-neutral reasoning layer on top of surgical video. It is Japanese-first and education/reference-only, and it turns a few targeted post-op questions into verified decision records."*

---

## 7. Regulation and privacy guardrails

| Area | Finding | Guardrail for the MVP |
|---|---|---|
| **PMD Act (Japan)** | MHLW case list: education material and recorded-surgery viewing are **not devices**. Supporting the choice of procedure or approach **is** a device. If any one function qualifies, the whole product is regulated. | Education/reference labelling; **no intra-op alerts**; frame the briefing as **case retrieval**, not prediction; PMDA 該当性相談 (device-classification consultation) before building a patient-specific briefing |
| **APPI** | Surgical video is personal information (PPC alert, Nov 2022). Giving it to a company needs **patient consent**, and "for academic research" wording is not consent. The 2026 APPI amendment adds an AI-development exemption, effective by about 2028 [details UNVERIFIED] | No hospital data in the MVP (open data only) |
| **Research ethics** | Using hospital video needs IRB review; the 2026 guideline revision expands opt-out for existing data [enforcement date UNVERIFIED] | Needed for any later pilot |
| **OR staff audio** | Staff personal information; consent, name redaction, raw-audio deletion | Opt-in per case |
| **US FDA** | CDS that processes images/signals cannot be non-device CDS | Stay education-only |
| **EU** | MDR Rule 11 / AI Act high-risk; AI Act Annex III also covers *evaluating learning outcomes* | Avoid skill scoring or certification decisions |

---

## 8. Business angle (for context)

Possible payers:
- **teaching hospitals and departments** (knowledge retention, M&M conferences, resident teaching);
- **ESSQS candidates and reviewers** (preparation, reviewer rationale; avoid pass/fail scoring);
- **device and robot makers** (a reasoning-layer app on their platforms);
- **surgical societies** (JSES, JUA) through curated obstacle libraries.

There is **no reimbursement in Japan**. Willingness to pay is **unproven**.

---

## 9. Decisions for the project owner (options only, not decided)

| # | Decision | Options | What the research says |
|---|---|---|---|
| **D1** | **Surgery X** | (a) Lap cholecystectomy; (b) RARP (urology); (c) both: chole as primary, a thin RARP template to prove generalisation; (d) RARP primary, chole for internal benchmarking only | Surgeon panel: (c), with chole primary. Dataset research: (d), RARP on GraSP for licence reasons. The trade-off is **data richness and demo clarity** vs **commercial licence and urology/robotics fit** |
| **D2** | **MVP audience** | Investors / surgeons in Japan / a hospital partner / an internal proof of concept | Changes what to emphasise: the graph animation (investors) vs the clip-plus-voice library (surgeons). It also changes the licence exposure (an external demo on NC data needs permission) |
| **D3** | **Audio approach** | Surgeon think-aloud voice-over / TTS / skip the audio pipeline in the MVP / seek real audio via a partner | Voice-over is the most realistic; must be disclosed as a reconstruction |
| **D4** | **Knowledge unit** | Keep the doc's 7-part model / adopt the panel's extended model (anticipation, non-action, who acted, delayed outcome, no-obstacle decision points) | The extended model is more clinically credible; a slightly larger schema |
| **D5** | **Answer modality** | Voice-first (as the doc says) / tap-first + optional voice / mixed | Panel: tap-first in Japan |
| **D6** | **MVP feature cuts** | Which of these to cut: action triplets, patient-similarity briefing, pattern percentages, the "prevention" question, diarization, the graph in the surgeon UI, an elaborate 8× replayer | Panel suggests cutting all of them from the surgeon-facing MVP; the graph may stay for an investor view |
| **D7** | **Validation before building** | Wizard-of-Oz test with 5–10 surgeons first / build first, validate after / run in parallel | Panel strongly recommends early validation of moment selection, answer rate and governance terms |
| **D8** | **Surgeon partners** | Is there access to 1+ Japanese surgeons (for the rule book, voice-over, recorded answers, validation)? | Critical for credibility; real answers from a real surgeon in the demo |
| **D9** | **Data/licence strategy** | Open NC data with licensor permission / permissive-only (GraSP, RARPL) / start an S-access JAPAN application in parallel | Affects which surgery is feasible commercially |
| **D10** | **Tech stack** | Hybrid stack as in §5.1 / alternatives (Neo4j, local VLM only, etc.) | Hybrid with Postgres is the pragmatic default from the research |
| **D11** | **Timeline, team, budget, compute** | — | Not known yet; needed to size the MVP |
| **D12** | **Doc revisions** | Soften the novelty claim, add anticipatory decisions, rename "obstacle" to a broader "decision moment", etc. | Optional |

---

## 10. Unverified items to check before committing

- Licences: GraSP (MIT on patient video, needs confirmation), SurgToolLoc/SurgVU (Intuitive; no licence file in the zips, download pages return 403), EndoVis 17/18, M2CAI16, Cholec80-CVS, ProstaTD, LapOntoSPM, FMA/Uberon; Japan's SNOMED membership; DINOv3 terms.
  - *Now confirmed:* SAR-RARP50 is **CC BY-NC-SA 4.0** (README and record metadata).
- Whether GraSP, HeiChole, AutoLaparo or SAR-RARP50 raw files contain any audio track (check with ffprobe).
  - *Already probed, video-only:* SurgToolLoc-2022 and SurgVU25 samples.
- GraSP/TAPIS weights: the Google Drive archive is the working route; the authors' own server (157.253.243.19) did not respond.
- Release status of the weights for BlooDet, EndoFM-LV, Surg-R1, SurgVidLM and the TeCNO/Trans-SVNet/LoViT checkpoints.
- S-access JAPAN fees, eligibility and audio availability.
- Details of the APPI 2026 AI exemption; enforcement date of the revised ethics guidelines; whether the Next-Gen Medical Infrastructure Act covers video.
- Current Gemini model names and video-input specifics; cloud GPU prices.
- 2025–26 status of Polyphonic, Proximie and OPExPARK.
