# Surgical Knowledge System — Project Idea

> **Document type:** Concept / idea document (not a project plan)
> **Organization:** MY ROBOTS
> **Status:** Early idea. Methods described here are a starting point, not a final decision.
> **Date:** October 2026

---

## Table of Contents

1. [The Idea in One Sentence](#1-the-idea-in-one-sentence)
2. [The Problem](#2-the-problem)
3. [The Key Insight](#3-the-key-insight)
4. [The Idea in Simple Words](#4-the-idea-in-simple-words)
5. [Who Benefits](#5-who-benefits)
6. [Guiding Principles](#6-guiding-principles)
7. [How the Knowledge Is Organized](#7-how-the-knowledge-is-organized)
8. [How the System Works](#8-how-the-system-works)
9. [Two Pipelines: Live and Offline](#9-two-pipelines-live-and-offline)
10. [What the Surgeon Sees (Application Ideas)](#10-what-the-surgeon-sees-application-ideas)
11. [How the Idea Scales](#11-how-the-idea-scales)
12. [What We Build Ourselves vs. What We Reuse](#12-what-we-build-ourselves-vs-what-we-reuse)
13. [The MVP Concept: What We Will Show](#13-the-mvp-concept-what-we-will-show)
14. [Important Considerations](#14-important-considerations)
15. [Open Questions](#15-open-questions)
16. [Glossary](#16-glossary)

---

## 1. The Idea in One Sentence

**Turn recorded surgery videos into a structured, searchable, surgeon-verified body of knowledge, so that surgeons can learn from past operations in minutes instead of watching hours of video.**

---

## 2. The Problem

- Surgeries (for example, laparoscopic and robotic surgeries) are **recorded on video**.
- After the surgery, the video is **stored and almost never used again**.
- Even an expert surgeon who has performed surgery **X** a hundred times still wants to **review past cases** before the next one.
- But each video is **1–2 hours or longer**. A busy surgeon **cannot watch them all**.
- The most valuable part, **why the surgeon did what they did**, is not in the video at all. It exists **only in the surgeon's head**, and it is lost over time.

**Result:** a huge amount of surgical experience exists, but it is locked away and cannot be searched, shared or learned from easily.

---

## 3. The Key Insight

Every surgery of the same type follows **roughly the same steps**.

What makes each case different is the **obstacles**:

- unexpected bleeding
- unusual anatomy
- adhesions (tissue stuck together)
- poor visibility
- equipment problems
- patient-specific difficulties

When an obstacle appears, the surgeon:

1. **notices** it,
2. **decides** how to handle it,
3. **acts**,
4. and then **continues** with the normal steps.

```
Normal steps ──► OBSTACLE ──► Surgeon notices ──► Decides ──► Acts ──► Back to normal steps
```

**This "obstacle → decision → reason → result" pattern is the most valuable knowledge in surgery.**
Our idea is to capture it, organize it and make it reusable.

---

## 4. The Idea in Simple Words

```
 ┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐    ┌──────────────────┐
 │ Surgery video│ ─► │ AI watches and   │ ─► │ AI asks a surgeon │ ─► │ Verified, linked │
 │ (+ audio)    │    │ listens: finds   │    │ short questions   │    │ KNOWLEDGE        │
 │              │    │ WHAT happened    │    │ about WHY         │    │ (searchable)     │
 └──────────────┘    └──────────────────┘    └───────────────────┘    └──────────────────┘
```

1. A surgery of type **X** is recorded (video, and audio if available).
2. **AI processes the recording.** It figures out which step is happening, which instruments are used, and where something unusual happened (the obstacles).
3. The AI can see **what** happened, but often not **why**. So it creates **a few short, specific questions**, each with the matching video clip.
4. **A surgeon answers** by voice or text. Ideally this is the surgeon who operated; for old videos, it is an expert reviewer.
5. The answers are turned into **structured knowledge**, linked to the exact moment in the video.
6. Over many cases, the knowledge grows into a **knowledge base for surgery X**: what usually happens, which obstacles appear, how surgeons handle them, and why.

> **AI finds the "what". The surgeon explains the "why". Together, they create verified knowledge.**

---

## 5. Who Benefits

| Who | How they benefit |
|---|---|
| **Surgeon preparing for an operation** | Reads a short briefing about similar past cases and likely obstacles in minutes, instead of watching hours of video |
| **Surgeons in training (residents)** | Learn real obstacles and real decisions with the reasoning behind them |
| **The surgeon who operated** | Their experience is preserved and can be shared with colleagues |
| **The hospital / clinic** | Builds its own surgical knowledge asset; supports teaching, quality review and case discussions |
| **Researchers (future)** | A structured, searchable dataset of surgical events, decisions and outcomes |

---

## 6. Guiding Principles

1. **Knowledge first, applications second.**
   The main goal is a rich, well-organized knowledge base. Applications (search, briefing, training) are built on top of it. Good knowledge can power many future applications.

2. **Human-in-the-loop, always.**
   This is healthcare. AI alone is not trusted. **Every important piece of knowledge is confirmed by a surgeon.**

3. **AI does the heavy work; the surgeon spends minimal time.**
   The surgeon is very busy. The AI prepares everything, and the surgeon only answers a few short, specific questions.

4. **Every fact shows where it came from.**
   Was it detected by AI, explained by the operating surgeon, or interpreted by a reviewer? This is always visible.

5. **One general system, many surgeries.**
   The system is not built for one surgery only. Surgery-specific details live in a separate "rule book" (template). Adding a new surgery means adding a new rule book, **not building a new system**.

6. **Each hospital owns its own knowledge.**
   Each hospital's knowledge is kept separate. Combining knowledge across hospitals is only a future possibility, and only with permission.

7. **Reference, not instruction.**
   The system shows *what other surgeons did and why*. It does **not** tell a surgeon what to do. Clinical decisions always stay with the surgeon.

---

## 7. How the Knowledge Is Organized

### 7.1 Four Kinds of Knowledge

| # | Kind | Question it answers | Source |
|---|---|---|---|
| 1 | **Procedure knowledge** | What *should* happen in surgery X? (the normal steps) | Surgeons, textbooks, published literature |
| 2 | **Case knowledge** | What *actually* happened in this particular case? | The video and audio, processed by AI |
| 3 | **Reasoning knowledge** | *Why* did the surgeon do that? | Surgeon's answers to the questions |
| 4 | **Pattern knowledge** | What usually happens across many cases, and what works? | Combining many cases |

They are **not separate databases**. They live in **one connected knowledge graph**, and each kind links to the others:

```
PROCEDURE knowledge    "Step 4 of surgery X"                     (the rule book)
        ▲  case events point to the step they happened in
CASE knowledge         "Case 101: bleeding at 38:12 in Step 4"   (from video/audio)
        ▲  explanations attach to an event
REASONING knowledge    "Added a second stitch because..."        (from the surgeon)
        ▼  many cases are counted together
PATTERN knowledge      "Happened in 18 of 100 cases; mostly when..."  (from aggregation)
```

### 7.2 Layers: From General to Specific

To make the system work for **any** surgery, the knowledge structure is built in layers:

| Layer | Contains | Example | Changes how often? |
|---|---|---|---|
| **Layer 0: Core** | Concepts shared by **every** surgery: step, instrument, anatomy, obstacle, decision, reason, outcome, evidence | "An obstacle happens during a step" | Almost never |
| **Layer 1: Specialty** | Vocabulary of one specialty | Urology anatomy, common urology complications | Rarely |
| **Layer 2: Procedure template** | The "rule book" for one surgery | Steps of surgery **X**, checkpoints, known obstacles | Once per new surgery, then refined |
| **Layer 3: Cases** | One record per real surgery | "Case 101 of surgery X" | Every surgery |

### 7.3 The Basic Unit of Knowledge

Every obstacle is captured in the same shape:

```
 CONTEXT ──► OBSTACLE ──► CUE ──► DECISION ──► REASON ──► OUTCOME ──► EVIDENCE
 (patient,   (what went   (what   (what was    (why)      (what       (video clip,
  step)       wrong)      was     done)                    happened)   transcript)
                          seen)
```

| Part | Meaning | Example |
|---|---|---|
| **Context** | Patient factors and current step | Step 4 of X; patient with a large organ |
| **Obstacle** | What made the step difficult | Bleeding not controlled by the first stitch |
| **Cue** | What the surgeon noticed | Continued bleeding, wide vessel |
| **Decision** | What the surgeon did | Placed a second stitch |
| **Alternatives** | What was considered but not done | Applying pressure only |
| **Reason** | Why this choice | The vessel was too wide for pressure to work |
| **Outcome** | What happened next | Bleeding controlled; 9 extra minutes |
| **Evidence** | Proof | Video clip 38:00–42:00, surgeon's voice answer |

### 7.4 Obstacle Families (Shared by All Surgeries)

Obstacles are organized in a **family tree**. The top levels are the **same for every surgery**. Each surgery adds its own specific obstacles at the bottom.

```
Obstacle
├── Bleeding ............... arterial / venous / oozing
├── Anatomical variation ... unusual vessel / enlarged organ / unusual position
├── Tissue condition ....... adhesions / inflammation / scarring / fragile tissue
├── Visibility ............. smoke / fogging / blood in view / limited space
├── Technical difficulty ... stitch failure / difficult dissection plane
├── Equipment .............. instrument failure / robot issue / energy device issue
├── Patient condition ...... unstable blood pressure / breathing issue
└── Unexpected finding ..... larger disease than expected / unexpected finding
         │
         └── (surgery X adds its own specific obstacles here)
```

**Why this matters:** we can ask questions at **any level**:
- "How is *this specific* obstacle handled in surgery X?"
- "How is *any bleeding* handled across all surgeries?"

### 7.5 Trust Labels

Every piece of knowledge carries a label showing how trustworthy it is:

| Label | Meaning |
|---|---|
| 🤖 **AI-detected** | Found by AI, not yet confirmed |
| 🩺 **Explained by operating surgeon** | First-hand reasoning from the surgeon who performed the case |
| 👁️ **Interpreted by reviewer** | An expert surgeon's interpretation of someone else's case |
| ✅ **Expert-validated** | Reviewed and approved as reliable knowledge |

Different surgeons may handle the same obstacle differently. **The system keeps all viewpoints** with their reasons, instead of forcing one "correct" answer.

---

## 8. How the System Works

### 8.1 The Rule Book (Procedure Template)

Before processing any video of surgery **X**, a **rule book** is created together with expert surgeons:

- the normal **phases and steps** in order,
- the **anatomy** and **instruments** involved in each step,
- **safety checkpoints**,
- **typical duration** of each step,
- a starting list of **known obstacles** for each step,
- standard **terms** (with synonyms, in Japanese and English).

This rule book is what the AI compares each real case against.
It is **written by us with surgeons**. It does not exist ready-made.

### 8.2 How the AI "Watches" the Video

The AI does not watch like a human. It turns the video into a **table**.

1. **Take frames:** a 1-hour video has about 108,000 frames. The AI looks at about **1 frame per second**.
2. **Understand each frame:** a vision model turns each frame into numbers that describe what is visible.
3. **Understand sequences:** another model looks at frames over time to recognize actions and steps.
4. **Several specialist detectors run together**, each filling one column of the table:

| Detector | What it finds |
|---|---|
| Step recognition | Which step of surgery X is happening now |
| Instrument detection | Which instruments are visible or in use |
| Anatomy recognition | Which organs or structures are visible |
| Event detection | Bleeding, smoke, suturing, pauses, camera cleaning |
| Action recognition | "Instrument + action + target" (e.g. *needle holder – stitches – vessel*) |

**Example output (the case timeline table):**

| Time | Step | Instruments | Events | Confidence |
|---|---|---|---|---|
| 36:40 | Step 4 | Needle holder, grasper | Suturing | 0.93 |
| 38:12 | Step 4 | Needle holder, suction | **Bleeding** | 0.81 |
| 39:05 | Step 4 | Suction | Blood in view, pause | 0.77 |
| 41:30 | Step 4 | Needle holder | Suturing (2nd time) | 0.88 |
| 50:52 | Step 5 | Scissors, grasper | — | 0.90 |

### 8.3 How the AI "Listens" (Audio)

Surgeons often speak during surgery. These words are valuable.

1. Separate the **audio** from the video.
2. Detect when someone is **speaking** and ignore machine noise.
3. Convert **speech to text** (Japanese and English).
4. Identify **who is speaking** (surgeon, assistant, others) where possible.
5. Classify **what kind of sentence** it is:

| Type | Example | Why it is useful |
|---|---|---|
| Instruction | "Suction." "Clip." | Confirms what is happening on screen |
| Concern | "Careful, it's bleeding." | Strong signal of an obstacle |
| Explanation | "I'm going this way because the tissue is scarred." | **Reasoning captured live** |
| Decision | "Let's add another stitch." | Marks the decision point |
| Bookmark | "Mark this." | Surgeon flags an important moment |
| Irrelevant | Small talk | Ignored |

The spoken words are added to the **same timeline table**, so video and audio support each other.

### 8.4 Finding Obstacles: Compare Against the Rule Book

The case timeline is compared with the rule book. **Anything different from the normal pattern is a possible obstacle:**

- a step that took much **longer** than usual,
- an **extra** step that is not in the rule book,
- a **missing** step,
- steps done in a **different order**,
- **bleeding** or another event detected,
- the surgeon **expressing concern** in the audio,
- a **bookmark** made during surgery.

### 8.5 Asking the Surgeon

For each possible obstacle, the system creates **short, specific questions**, each with its **video clip**.

**Question types:**

| Type | Example |
|---|---|
| Cue | "What did you notice here?" |
| Decision | "What did you do?" |
| Reason | "Why did you choose this approach?" |
| Alternatives | "What else did you consider?" |
| Prevention | "Could this have been avoided?" |
| Confirmation | "Was this the usual approach? (Yes / Explain)" |

**Rules for good questions:**
- **Few:** only the most important 3–5, ranked by importance.
- **Specific:** linked to a time and a clip, not general.
- **Smart:** if the knowledge base already knows this obstacle well, ask only a quick confirmation.
- **Use what was said:** if the surgeon already explained something during surgery, ask them to confirm it instead of asking again.
- **Voice first:** the surgeon can simply speak the answer.

### 8.6 Turning Answers into Knowledge

1. Voice answer → **converted to text** (the original recording is kept as evidence).
2. AI extracts the **structured parts**: obstacle, cue, decision, reason, alternatives, outcome.
3. Terms are matched to the **standard vocabulary**.
4. The system shows its understanding back to the surgeon → **one-tap confirmation**.
5. Anything new (a term or obstacle not yet known) is flagged so the **vocabulary can grow**.
6. The knowledge graph is **updated**.

### 8.7 Full Example (Surgery X, Case 101)

```
VIDEO      38:12 — Bleeding detected during Step 4.
           Step 4 took 14 minutes (usually about 5).

AUDIO      38:15 — Surgeon: "Careful, it's bleeding from the vessel."
           39:40 — Surgeon: "The first stitch didn't catch it all."

AI DRAFT   Possible obstacle: bleeding not controlled by first stitch.

QUESTION   [clip 38:00–42:00]
           "You said the first stitch didn't catch all of it.
            Why did you choose a second stitch instead of pressure?"

ANSWER     "The vessel was unusually wide. Pressure would not hold it."
(voice)

KNOWLEDGE  Obstacle:     Bleeding not controlled by first stitch
           Step:         Step 4 of surgery X
           Cue:          Continued bleeding; wide vessel
           Patient:      Enlarged organ
           Decision:     Second stitch
           Not chosen:   Pressure only
           Reason:       Vessel too wide for pressure to work
           Outcome:      Controlled; 9 minutes added
           Evidence:     Clip 38:00–42:00; voice answer
           Trust label:  Explained by operating surgeon
```

**After many cases, pattern knowledge appears:**
> "This obstacle occurred in 18 of 100 cases of surgery X. 12 of them involved an enlarged organ. A second stitch was used in 15 of them."

---

## 9. Two Pipelines: Live and Offline

The **same core engine** is used in two ways. Only the **input** and the **person answering** change.

```
     LIVE PIPELINE                                   OFFLINE PIPELINE
  Video/audio during surgery                     Old recorded videos (archive)
            │                                                │
            └──────────────────► INPUT ◄─────────────────────┘
                                   ▼
        ┌───────────────── SAME CORE ENGINE ─────────────────┐
        │  frames + audio → AI → timeline → compare with      │
        │  rule book → obstacles → questions                  │
        └──────────────────────────┬──────────────────────────┘
                                   ▼
            ┌──────────────────────┴───────────────────────┐
   Operating surgeon                                  Reviewer surgeon
   (right after surgery)                              (any time)
            └──────────────────────┬───────────────────────┘
                                   ▼
                    Knowledge graph (one per hospital)
```

### 9.1 Live Pipeline (New Surgeries)

- The video signal is **copied** from the laparoscopy or robot system to our device, **without disturbing** the surgeon's monitor.
- Audio is captured as well, for example with a separate microphone.
- The video is **processed during the surgery**, not after.
- When the surgery ends, the **questions are almost ready**.
- The surgeon answers **within 10–20 minutes after the surgery**, while still in the operating room area and before the next case.
- During surgery, staff or the surgeon can make **live bookmarks** (a tap or "mark this").
- **The surgeon is never asked anything during the operation.** The system only records.

### 9.2 Offline Pipeline (Already-Recorded Videos)

- Hospitals already have **many old videos** of surgery X.
- It is usually **not practical to find the original surgeon** for each old video.
- Instead, an **expert reviewer surgeon** from the same hospital answers the questions.
- There is **no time pressure**, so processing can be slower and more detailed.
- The system **selects the most valuable cases** for the reviewer (rare obstacles, difficult cases) and avoids asking about the same obstacle again and again.
- Answers are labeled **"Interpreted by reviewer"** (see Trust Labels).

### 9.3 Comparison

| | Live pipeline | Offline pipeline |
|---|---|---|
| Input | Live video/audio stream | Saved video files |
| Speed needed | Fast (questions ready right after surgery) | No rush |
| Who answers | The surgeon who operated | An expert reviewer surgeon |
| Question style | "Why did **you**...?" | "Why do you think the surgeon...?" / "Would you do the same?" |
| Number of questions | Few (3–5) | More, answered in batches |
| Audio | Usually available | Often not available |
| Knowledge label | First-hand reasoning | Expert interpretation |
| Main role | Keeps knowledge growing with every new surgery | Builds the starting knowledge base from the archive |

If a surgeon in the live pipeline does not have time to answer, the case **moves to the offline reviewer queue**. Nothing is lost.

---

## 10. What the Surgeon Sees (Application Ideas)

Basic principle: **a surgeon should never need to watch a full video to get an answer.** They get a short summary, and a short clip when they need to see something.

### Before surgery
- **Pre-surgery briefing:** enter patient details and get a one-page summary of similar past cases, likely obstacles and how they were handled.
- **Similar cases:** the closest past cases, as summaries.
- **Procedure map:** steps of surgery X as a timeline, with common obstacles, checkpoints and tips at each step.
- **Preparation list:** instruments and devices used in similar cases.

### Exploring knowledge
- **Obstacle library:** one card per obstacle, with what it looks like (clips), early warning signs, different ways surgeons handled it, the reasons, and the results.
- **Smart video view:** videos split into steps, obstacles marked on the timeline, surgeon explanations attached at the right moment.
- **Side-by-side comparison:** the same step or obstacle from two different cases.
- **Ask a question:** questions in plain language, with answers from the knowledge base that always show their sources and clips.
- **Anatomy variations gallery.**

### Trust and discussion
- **Trust labels** on every piece of knowledge.
- **Different opinions shown side by side**, with reasons.
- **Follow-up questions** to the surgeon who explained a case.

### Learning (for trainees)
- **Step-by-step learning path** through surgery X.
- **"What would you do?" mode:** the video pauses before an obstacle; the trainee chooses an action, then sees what the real surgeon did and why.
- **Case review mode** for teaching sessions.

### Personal
- Bookmarks, notes and personal collections.
- Private view of one's own cases.

### For the surgeon answering questions
- Notification after the surgery: "4 questions, about 3 minutes."
- Each question comes with its video clip.
- Answer by voice; AI repeats its understanding for one-tap confirmation.
- Skip or answer later; privacy options.

---

## 11. How the Idea Scales

| Expansion | What changes | What stays the same |
|---|---|---|
| **New surgery (Y, Z)** in the same specialty | Add a new **rule book** (template) and its specific obstacles | Core engine, core knowledge structure, applications |
| **New specialty** | Add specialty vocabulary (Layer 1) and rule books | Core engine and structure |
| **New hospital** | New, **separate** knowledge base for that hospital; process their archive (offline), then new surgeries (live) | Same system and same structure |
| **Combining hospitals (future, optional)** | With permission, knowledge from several hospitals can be combined to reveal more variations and rare cases | Possible **because** all hospitals share the same structure |

**Key point:** the structure is shared, the content is specific. That is what makes the system expandable without rebuilding it.

---

## 12. What We Build Ourselves vs. What We Reuse

### Built by us (new)

| Component | Description |
|---|---|
| **Core knowledge structure (ontology)** | The shared structure: steps, obstacles, decisions, reasons, outcomes, evidence, trust |
| **Rule book for surgery X** | Created with expert surgeons |
| **Obstacle family tree and vocabulary** | Starting list, growing over time |
| **Core engine** | Combines video and audio results into the case timeline and compares it with the rule book |
| **Question engine** | Decides what to ask, how to ask it, and in what order |
| **Answer-to-knowledge engine** | Turns surgeon answers into structured, verified knowledge |
| **Knowledge graph** | Stores all four kinds of knowledge with links to video evidence |
| **Live and offline input pipelines** | Including a **replayer** that simulates live surgery from a video file |
| **Surgeon applications** | Question-answering app and knowledge-viewing app |

### Reused (existing tools and standards, where licensing allows)

| Area | Examples |
|---|---|
| Video and audio handling | FFmpeg, GStreamer, OpenCV |
| AI models for video | Existing vision models and surgical video models, adapted to surgery X |
| Speech-to-text | Open speech recognition models (e.g. Whisper family), Japanese-capable |
| Language understanding | Large language models for questions and extraction |
| Knowledge standards | Existing surgical process ontologies (as reference), anatomy vocabularies, complication grading systems, W3C standards for provenance and video references |
| Labeling tools | Open-source video annotation tools |
| Open datasets | Public surgical video datasets for early development (licenses must be checked) |

> Note: There is **no ready-made "rule book" for each surgery** and **no existing system that captures the surgeon's reasoning** in this way. These are our core original contributions.

---

## 13. The MVP Concept: What We Will Show

### 13.1 Scope

- **One domain** (e.g. urology), **one surgery: X.** The name of X will be decided later.
- Think of it as a **test case**. If the idea works for X, the same architecture expands to other surgeries.
- The MVP uses **existing, openly available surgical videos** (open datasets), not live hospital connections.
- **Important:** even though the MVP covers only surgery X, the system is designed to be **general**. Nothing specific to X is built into the core. All X-specific details live in its rule book.

### 13.2 What the MVP Demonstrates

| # | What we show | What it proves |
|---|---|---|
| 1 | **Rule book for surgery X** in the knowledge structure | Surgery knowledge can be structured |
| 2 | **Offline pipeline:** a recorded video is processed into a case timeline (steps, instruments, events, speech) | AI can turn a video into a structured record |
| 3 | **Simulated live surgery:** a recorded video plays *as if live* through the replayer; the timeline builds in real time on screen | The live pipeline works without OR hardware |
| 4 | **Obstacle detection:** deviations from the rule book are found and highlighted | AI can find the "what" |
| 5 | **Question generation:** when the "surgery" ends, a short set of questions with clips appears on a phone-style screen | The system asks the right questions quickly |
| 6 | **Answering by voice:** a surgeon (or reviewer) answers; the answer is converted into structured knowledge with one-tap confirmation | Human expertise can be captured with minimal effort |
| 7 | **Knowledge graph growing:** new obstacles, decisions and reasons appear in the graph, linked to video clips | Knowledge accumulates and connects |
| 8 | **Knowledge view:** a simple obstacle library or pre-surgery briefing for surgery X built from the processed cases | The knowledge is useful to a surgeon |

### 13.3 The Demo Screen (Concept)

```
┌──────────────────────────────┬──────────────────────────────────────┐
│                              │  LIVE CASE TIMELINE                  │
│   "LIVE" SURGERY VIDEO       │  Step: 4 ▸ Instruments: needle, ...  │
│   (replayed from file)       │  ⚠ 38:12 Bleeding detected           │
│                              │  💬 "Careful, it's bleeding"          │
│   [speed: 1× 2× 4× 8×]       │  ⚠ Step 4 longer than usual           │
├──────────────────────────────┼──────────────────────────────────────┤
│  LIVE TRANSCRIPT             │  KNOWLEDGE GRAPH (updating)          │
│  38:15 Surgeon: "Careful..." │   Step 4 ── Obstacle ── Decision     │
│  39:40 Surgeon: "First..."   │                └── Reason            │
└──────────────────────────────┴──────────────────────────────────────┘
          Surgery ends ──►  📱 "4 questions ready"  ──► voice answers
```

### 13.4 What the MVP Does *Not* Include

- No connection to real operating room equipment (simulated instead).
- No real patient data from a hospital.
- No multi-hospital features.
- No clinical decision recommendations.

---

## 14. Important Considerations

| Area | Consideration |
|---|---|
| **Surgeon time** | The surgeon has only about 10–20 minutes after surgery. Questions must be few, short and voice-based. |
| **Patient privacy** | Patient consent is required. Identifying information is removed from video, audio and transcripts. Japan's privacy law (APPI) applies. |
| **Staff privacy (audio)** | Operating room conversations may include names and private talk. All staff must consent. Names are removed from transcripts. Raw audio may be deleted after processing. |
| **Patient safety** | Capturing video must **never interfere** with the surgeon's display or equipment. Hospital clinical engineering must approve any connection. |
| **Trust** | Every fact shows its source and trust level. Different opinions are kept, not merged. |
| **Regulation** | The system is a **reference and education tool**, not a decision-making tool. Software that recommends clinical actions may be regulated as a medical device (in Japan, by the PMDA). |
| **Data ownership** | Each hospital's videos and knowledge belong to that hospital and stay separate. |
| **Licensing** | Open datasets and standards must be checked for commercial-use permission. |
| **Legal sensitivity** | Surgeons may hesitate to discuss complications on record. Privacy options and clear data policies are needed. |

---

## 15. Open Questions

These are not decided yet and will be discussed later:

- Which surgery will be **X**?
- Which **open datasets** fit surgery X, and are they licensed for our use?
- What is the best **format for surgeon answers** (voice, text, quick-tap, or a mix)?
- How many questions can a surgeon realistically answer after each surgery?
- How exactly will the **question ranking** work?
- Which **storage technology** will hold the knowledge graph?
- How will **audio** be captured in real operating rooms (separate microphone, robot console microphone, etc.)?
- How will the AI handle **disagreement** between surgeons?
- What will make a surgeon **trust** the knowledge enough to use it?

---

## 16. Glossary

| Term | Simple meaning |
|---|---|
| **Surgery X** | The single surgery type chosen for the MVP (name to be decided) |
| **Obstacle** | Anything that makes a step harder than normal (bleeding, unusual anatomy, adhesions, etc.) |
| **Rule book / Procedure template** | Structured description of the normal steps of a surgery |
| **Case** | One real surgery performed on one patient |
| **Case timeline** | The table the AI creates from a video: what happened, and when |
| **Deviation** | A difference between what happened and what the rule book expects |
| **Ontology** | A formal structure of concepts and how they relate (the "shape" of the knowledge) |
| **Knowledge graph** | A database where knowledge is stored as connected items (case → step → obstacle → decision → reason) |
| **Human-in-the-loop** | AI does the work; a human checks and adds what AI cannot know |
| **Operating surgeon** | The surgeon who performed the case |
| **Reviewer surgeon** | An expert surgeon who interprets a case they did not perform |
| **Live pipeline** | Processing a surgery while it happens |
| **Offline pipeline** | Processing already-recorded surgery videos |
| **Replayer** | A tool that plays a recorded video as if it were a live surgery (used in the MVP) |
| **Provenance / Trust label** | Information about where a piece of knowledge came from and how reliable it is |
| **MVP** | Minimum Viable Product: the smallest version that demonstrates the idea works |

---

*This document describes the idea only. Implementation methods, technology choices and plans will be decided separately and may change as we test the idea in practice.*
