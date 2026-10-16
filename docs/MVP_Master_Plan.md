# MVP Master Plan: Surgical Knowledge System (RARP)

> **Organisation:** MY ROBOTS
> **Scope:** the MVP only (not the full product)
> **Date:** 2026-10-16
> **Inputs:** `Surgical_Knowledge_System_Idea.md` (the idea) and `Research_Report_Phase0.md` (the research)
> **Status:** draft for review by Dev1 and Dev2. Nothing is built yet.

---

## 0. Decisions this plan is built on (made by the project owner)

| Topic | Decision |
|---|---|
| Surgery X | **RARP (robot-assisted radical prostatectomy) only** |
| Video sources | Open datasets (**GraSP / PSI-AVA**) plus **YouTube RARP videos**, for private demo use only |
| Audience | **All four:** investors, surgeons, hospital, internal |
| Surgeon | Available **later**. Until then the dev team role-plays the surgeon, and those answers are labelled "Simulated" |
| Timeline | **4–6 weeks** |
| Team | **Dev1** (office PC x64, home Surface ARM64 16 GB) and **Dev2** (home, ASUS Zenbook Snapdragon ARM64 48 GB). Both are generalists and both build with Claude |
| Way of working | **Two parallel tracks with minimal dependency, integrated at the end** |
| Compute | No NVIDIA GPU, so **no model training** |
| Paid AI | **OpenAI only** |
| Vision | **GPT vision only** (sampled frames, not training) |
| Language | **Bilingual Japanese + English**, both UI and content |
| Answer modes | **Tap, voice and text, given equal weight** |
| Knowledge unit | **Extended model** (from the surgical panel) |
| Demo runs on | **Local laptop** |

---

## 1. What the MVP is, in one paragraph

A recorded RARP video plays **as if it were live**. While it plays, the system shows the surgical step, flagged moments (bleeding, a step that runs long, safety checkpoints) and the transcript, in Japanese and English. When the "surgery" ends, a phone screen shows **"4 questions · about 3 minutes"**. Each question comes with its video clip, and the surgeon answers by **tap, voice or text**. The AI reads its understanding back for one-tap confirmation. The answer becomes a **verified decision record**, which appears **live** in the knowledge graph and in the **Knowledge Library**. There the user can browse obstacles across cases, compare how different surgeons handled them, and **ask questions in plain Japanese or English**. Answers come with cited clips, and **every fact shows where it came from**.

---

## 2. Feature catalogue (everything we will deliver)

**Priority key (MoSCoW):**
- **M** = Must. These ship even in the 4-week plan.
- **S** = Should. These ship in the 6-week plan.
- **C** = Could. Stretch goals, only if time allows.

**Owner:** **D1** = Dev1 (the "Brain" track), **D2** = Dev2 (the "App" track).

### 2.1 Knowledge foundation (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| A1 | **RARP Rule Book** | Phases and steps in order; typical duration ranges; anatomy and instruments per step; safety checkpoints; known obstacles per step; bilingual terms. Stored as one YAML file. Draft until a surgeon reviews it | M |
| A2 | **Core ontology (Layer 0)** | The shared types of things and relations: Case, Step, Moment, Obstacle, Cue, Action, Actor, Reason, Outcome, Evidence, Decision Record. Aligned to OntoSPM and PROV-O through IRIs | M |
| A3 | **Obstacle family tree** | The 8 universal families plus RARP-specific obstacles. Also records what caused each obstacle (patient, event, technical, equipment, unknown) | M |
| A4 | **Bilingual vocabulary** | JA/EN terms with synonyms (e.g. DVC = dorsal vein complex = サントリーニ静脈叢) | M |
| A5 | **Trust labels** | 🤖 AI-detected · 📐 Dataset annotation · 🎙️ Extracted from narration · 🩺 Explained by operating surgeon · 👁️ Interpreted by reviewer · ✅ Expert-validated · 🧪 Simulated (demo) | M |
| A6 | **Visual step atlas** | 2–3 reference frames per step, taken from GraSP's ground-truth labels and shown to GPT as examples (no training) | M |
| A7 | Severity grading | EAUiaiC grade on events | C |

### 2.2 Case ingestion (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| B1 | **GraSP / PSI-AVA importer** | Videos plus their ground-truth phases and steps, turned into cases | M |
| B2 | **YouTube importer** | yt-dlp download plus metadata: language, whether the video is narrated, and **whether it is edited/condensed** | M |
| B3 | **Normaliser** | 720p H.264 "faststart" MP4, a 16 kHz mono audio track, a poster frame and thumbnail strips | M |
| B4 | **Case registry** | One `case.json` per case: source, type (full-length or edited), language, data note | M |
| B5 | RARPL importer | An extra open dataset (CC BY 4.0) | C |

### 2.3 Perception, with GPT vision only (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| C1 | **Frame sampler** | One frame every N seconds (default 5), plus extra frames where the scene changes | M |
| C2 | **Step recognition** | GPT looks at 1-minute windows of frames, with the rule book and the step atlas as context, and returns step probabilities | M |
| C3 | **Rule-book decoding** | Turns the noisy per-window guesses into clean, ordered step segments using rule-book order and duration priors (Viterbi). This is plain code, not training, and the **biggest accuracy lever** | M |
| C4 | Instrument tagging | Instruments visible in each window, from the same GPT call | S |
| C5 | **Event detection** | Bleeding (red-pixel ratio plus a GPT check), camera out of body, idle/pause; smoke and suction are S | M |
| C6 | **Deep look** | For each flagged moment, GPT gets denser frames and describes what is visible and what changed | M |
| C7 | **Accuracy evaluator** | Scores GPT's steps against GraSP's ground truth (frame accuracy, segment F1) and writes `metrics.json`. These numbers are reported honestly | M |
| C8 | **Ground-truth mode** | For GraSP cases, uses the dataset's own step labels, shown with the 📐 label | M |
| C9 | True live processing | GPT processes each window while the video plays | C |

### 2.4 Audio and language (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| D1 | **Audio extraction and chunking** | Chunks small enough for the API's 25 MB file limit | M |
| D2 | **Timestamped transcription** | `whisper-1` (segment timestamps) or `gpt-4o-transcribe-diarize` (timestamped segments with speaker labels) | M |
| D3 | **JA↔EN translation** | Every utterance stored in both languages | M |
| D4 | **Utterance classification** | Instruction / concern / explanation / decision / bookmark / teaching / irrelevant | M |
| D5 | Term normalisation | Maps spoken terms to the vocabulary (A4) | S |
| D6 | Synthetic operating-room speech | Scripted OR-style lines voiced by TTS for GraSP cases, which have no audio. Labelled "synthetic" | S |
| D7 | **Narration mining** | YouTube narration often explains *why*. This turns it into draft decision records labelled 🎙️ | S |

### 2.5 Timeline and moment engine (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| E1 | **Timeline fusion** | Steps, events, instruments and utterances merged into one `timeline.json` | M |
| E2 | **Deviation detection** | A step longer or shorter than usual (z-score against the rule book; **switched off for edited videos**), plus missing, extra and out-of-order steps | M |
| E3 | **Event and speech moments** | Bleeding, a concern in the transcript, a bookmark, an explanation given at a decision point | M |
| E4 | **Checkpoint decision points** | Moments where nothing went wrong but a decision was made, e.g. "Ureteral orifices identified before bladder neck closure?" | M |
| E5 | **Moment ranking** | Merges duplicates, scores the moments, and picks each clip's start and end | M |
| E6 | **Clip cutter** | Pre-cut MP4 clips and a poster image per moment | M |

### 2.6 Question engine (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| F1 | **Typed questions** | Cue, decision, reason, alternatives, confirm-what-you-said, checkpoint, options-at-this-point. **There is no "could this have been avoided?" question** | M |
| F2 | **Two styles** | Operating surgeon ("you") and reviewer ("the surgeon") | M |
| F3 | **Tap scaffolding** | Each question carries an AI draft (✓ correct / ✎ edit / ✗ not an issue) and multiple-choice options | M |
| F4 | Knowledge-base-aware | If an obstacle is already well covered in the knowledge base, only ask for confirmation | S |
| F5 | **Uses what was said** | "You said '…'. Is this why?" | M |
| F6 | **Budget** | 3–5 questions in operating mode, up to 10 in reviewer mode, each with a time estimate | M |
| F7 | **Bilingual questions** | JA and EN text for every question | M |

### 2.7 Answer-to-knowledge engine, at runtime (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| G1 | **Voice transcription endpoint** | Turns spoken answers into text, JA or EN | M |
| G2 | **Extraction into a Decision Record** | The answer becomes a Decision Record (§4) as strict JSON | M |
| G3 | **Read-back** | A short JA/EN summary for one-tap confirmation, with editable chips | M |
| G4 | New-term detection | Flags unknown terms so the vocabulary can grow | S |
| G5 | **No invention** | A field the surgeon did not mention stays empty ("not stated"). Every filled field must point to the words that support it | M |

### 2.8 Knowledge services, at runtime (D1)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| H1 | **Embeddings** | Vectors for decision records and questions | M |
| H2 | **Ask** | A grounded answer with citations. **It says plainly when the knowledge base doesn't cover the question** | M |
| H3 | Pre-op briefing | A procedure-level briefing, framed as retrieval of past cases, not prediction | S |
| H4 | Trainee scenarios | Pause points and choices, built from recorded alternatives (precomputed) | S |

### 2.9 App server and knowledge store (D2)

| ID | Feature | What it delivers | Pri |
|---|---|---|---|
| I1 | **App server and case loader** | FastAPI plus SQLite. Scans case packages and validates them against the contracts | M |
| I2 | **Knowledge graph store** | Entities, edges, provenance and decision records. **Keeps every viewpoint** | M |
| I3 | **Pattern counts** | "Seen in 3 of 9 cases". The sample size is always shown, and **no percentages are shown when n < 20** | M |
| I4 | **Retrieval for Ask** | Cosine similarity over stored embeddings | M |
| I5 | **Live updates (SSE)** | When an answer is confirmed, the graph and library update instantly | M |
| I6 | **Demo operations** | Seed, reset and snapshot the knowledge base with one command | M |
| I7 | **Brain client** | Switchable between **mock** (fixtures) and **real** (the Brain API) | M |
| I8 | Audit log | Who confirmed or edited what, and when | S |

### 2.10 Screens (D2)

| ID | Screen | What it delivers | Pri |
|---|---|---|---|
| J1 | **Home / cases** | Case list with source, language, status and trust badges | M |
| J2 | **Control Room** ("live" replay) | Video at 1×/2×/4×/8×/16×; a live step bar and event markers; a JA/EN transcript ticker; alerts; a graph panel that grows; "surgery ends" → "4 questions ready" | M |
| J3 | **Surgeon Answer app** | Mobile layout. Question cards with the clip on loop; **tap, voice and text side by side**; read-back; confirm/edit chips; skip or later; "2 of 4 · ~2 min" | M |
| J4 | **Case Explorer** | The smart video view: step strip, moment markers, explanations pinned to their moments, jump-to | M |
| J5 | **Knowledge Library** | Obstacle family tree leading to obstacle cards: clips, cues, **the different ways surgeons handled it**, reasons, outcomes, **viewpoints side by side**, counts | M |
| J6 | **Ask** | JA/EN question box; the answer comes with cited clips you can play | M |
| J7 | Procedure Map | RARP steps with known obstacles, checkpoints and case counts per step | S |
| J8 | **Graph view** | A panel inside the Control Room is M; a full explorer page for investors, with filters, is S | M/S |
| J9 | **Provenance drawer** | On every fact: source, model and prompt version, who confirmed it and when, evidence links | M |
| J10 | Reviewer queue | The offline pipeline: pending cases, batch answering in reviewer style | S |
| J11 | Trainee "What would you do?" | The video pauses, you choose, then you see what the surgeon did and why | S |
| J12 | Pre-op Briefing | Procedure-level briefing, with optional case factors as filters | S |
| J13 | Side-by-side comparison | The same obstacle in two cases | C |
| J14 | Admin / pipeline | Case processing status, AI accuracy against ground truth, rule book viewer | S |
| J15 | **JA/EN toggle** | Everywhere, switchable instantly | M |
| J16 | **Disclaimers** | "Education/reference, not clinical advice"; "Demo data" badges | M |

**Totals:** about 50 M-features, about 20 S-features and about 6 C-features. The 4-week plan ships all M. The 6-week plan ships M + S.

---

## 3. Architecture

**Legend:** blue = Dev1 (Brain) · green = Dev2 (App) · amber box + bold arrows = the two contracts, the only coupling between the tracks · grey = external.
Image version: `MVP_Architecture.png` (for viewers that do not render Mermaid).

```mermaid
flowchart TB
    subgraph SRC["📼 Video sources"]
        direction LR
        GRASP["GraSP / PSI-AVA<br/>full RARP · step labels"]
        YT["YouTube RARP<br/>narrated JA / EN"]
    end

    KB[("📚 Knowledge files · Dev1<br/>rule book · taxonomy<br/>vocabulary · step atlas")]

    subgraph OFF["🧠 OFFLINE · Brain pipeline · Dev1 · office PC"]
        direction TB
        ING["Ingest + normalise · B1–B4"]
        FR["Frame sampler · C1"]
        AUD["Audio → transcribe → translate → classify · D1–D4"]
        VIS["GPT vision windows + step atlas · C2"]
        EVT["Event heuristics + GPT check · deep look · C5–C6"]
        DEC["Rule-book decoding (Viterbi) · C3"]
        FUS["Timeline fusion · E1"]
        MOM["Moment engine · deviations · checkpoints · clips · E2–E6"]
        QE["Question engine · F1–F7"]
        SEED["Seed records 🧪 / 🎙️"]
        ING --> FR
        ING --> AUD
        FR --> VIS --> DEC --> FUS
        FR --> EVT --> FUS
        AUD --> FUS
        FUS --> MOM --> QE --> SEED
    end

    CP[/"📦 CONTRACT #1 · Case Package (files)<br/>case · timeline · moments · questions · clips · seed_records"/]

    subgraph RT["💻 RUNTIME · demo laptop"]
        direction TB
        subgraph WEB["🖥️ Web app · Dev2"]
            direction LR
            SCR["Control Room · Answer app 📱<br/>Case Explorer · Library<br/>Ask · Graph view · Provenance"]
        end
        subgraph AS["🗄️ App server :8000 · Dev2"]
            direction LR
            LOAD["Case loader<br/>+ contract validation"]
            STORE[("SQLite knowledge store<br/>entities · edges · provenance")]
            PAT["Pattern counts<br/>+ retrieval"]
            SSE["SSE<br/>live updates"]
            BC["Brain client<br/>mock ⇄ real"]
            LOAD --> STORE --> PAT
            STORE --> SSE
        end
        subgraph BR["🧠 Brain API :8100 · Dev1 · stateless"]
            direction LR
            EPS["/v1/answers/transcribe<br/>/v1/answers/extract<br/>/v1/embed · /v1/ask<br/>/v1/briefing (S)"]
            CACHE[("disk cache<br/>offline mode")]
        end
    end

    OAI(["☁️ OpenAI API<br/>vision · text · STT · TTS · embeddings"])

    SRC --> OFF
    KB -. "rules + vocabulary" .-> OFF
    OFF ==> CP
    CP == "shared drive" ==> AS
    WEB <== "REST + SSE" ==> AS
    AS == "📜 CONTRACT #2 · Brain API (HTTP)" ==> BR
    OFF -. "Batch API" .-> OAI
    BR -. "live calls" .-> OAI

    classDef contract fill:#fff4cc,stroke:#c98a00,stroke-width:3px,color:#3b2a00
    classDef dev1 fill:#e3efff,stroke:#2f6fd6,color:#0b2a5b
    classDef dev2 fill:#e5f7ea,stroke:#2e9a4f,color:#0d3b1c
    classDef ext fill:#f1f1f1,stroke:#888,color:#222
    class CP contract
    class ING,FR,AUD,VIS,EVT,DEC,FUS,MOM,QE,SEED,KB,EPS,CACHE dev1
    class LOAD,STORE,PAT,SSE,BC,SCR dev2
    class OAI,GRASP,YT ext
```

<details>
<summary>Plain-text version (for terminals and Claude sessions)</summary>

```
 ═══════════════ OFFLINE: Brain pipeline (Dev1, runs on the office PC) ═══════════════
 GraSP / PSI-AVA ─┐
 YouTube (yt-dlp) ┴─► ingest ─► normalise ─┬─► frames ─► GPT vision windows ─► rule-book decoding ─► steps
                                           │           └─► event heuristics + GPT check ─► deep look
                                           └─► audio ─► transcribe ─► translate ─► classify
                      fuse ─► timeline ─► moment engine ─► questions ─► clips ─► seed records
                                           │
                       ┌───────────────────▼────────────────────┐
                       │  CASE PACKAGE  (files, contract v1)    │  ◄── CONTRACT #1
                       └───────────────────┬────────────────────┘
                                           │ shared drive (videos never go into git)
 ═══════════════ RUNTIME: demo laptop ═════▼══════════════════════════════════════════
 ┌──────── Brain API :8100 (Dev1) ────────┐  HTTP  ┌──────── App server :8000 (Dev2) ────────┐
 │ POST /v1/answers/transcribe            │◄───────│ case loader + contract validation      │
 │ POST /v1/answers/extract               │        │ knowledge store (SQLite)               │
 │ POST /v1/embed   POST /v1/ask          │        │ pattern counts · retrieval · SSE       │
 │ POST /v1/briefing (S)                  │        │ brain client (mock ⇄ real)             │
 │ OpenAI calls + disk cache (offline)    │        └───────────────┬────────────────────────┘
 └────────────────────────────────────────┘                        │ REST + SSE
             ▲ CONTRACT #2                       ┌─────────────────┴──────────────────────────┐
                                                 │ Web app (Dev2): Control Room · Answer app · │
                                                 │ Case Explorer · Library · Ask · Graph · …   │
                                                 └─────────────────────────────────────────────┘
```

</details>

**The whole decoupling idea:**
- Dev1 and Dev2 touch each other only through **two contracts**: Contract #1, the **Case Package** (files), and Contract #2, the **Brain API** (HTTP).
- Both are agreed in Phase 0 and then frozen.
- Dev2 builds against **fixture case packages** and a **mock Brain**. Dev1 builds and tests engines from the **command line**, with no UI.
- Neither ever needs the other's code until integration.

### 3.1 Technology stack (chosen to suit ARM laptops with no GPU)

| Layer | Choice | Why |
|---|---|---|
| Python tooling | **uv**, Python 3.12/3.13 (the same minor version on every machine) | One tool manages Python versions and environments on x64 and ARM64 |
| Brain | Python: `openai`, `pydantic` v2, FastAPI, Typer (CLI), Pillow + numpy, PyYAML, yt-dlp, **FFmpeg CLI** | No PyTorch, CUDA or OpenCV. GPT-only vision makes the stack ARM-friendly |
| App server | Python: FastAPI, **SQLite** (standard library, WAL mode), `sse-starlette`, httpx, numpy | No database server to install. Runs anywhere, one file, easy reset |
| Web | **Vite + React + TypeScript**, Tailwind + shadcn/ui, react-i18next, TanStack Query, **Cytoscape.js**, native `<video>`, MediaRecorder | A fast local SPA; server-side rendering isn't needed |
| Contracts | **Pydantic models are the single source of truth.** JSON Schema is generated from them, and TypeScript types (`json-schema-to-typescript`) from that | One definition, three outputs, so the two sides can't drift apart |
| AI | OpenAI. Model **tiers** live in config (below) | Model names change; tiers don't |
| Repo | One **private GitHub repo** (monorepo), with folder ownership enforced through `CODEOWNERS` | Prevents merge conflicts between the tracks |

**OpenAI model tiers.** Confirm the exact model names on setup day; current third-party listings show the GPT-5.6 Luna/Terra/Sol family.

| Tier | Used for | Class |
|---|---|---|
| `VISION_FAST` | 1-minute step windows (many calls, low detail) | Cheapest vision-capable model |
| `VISION_DEEP` | Deep look at flagged moments (few calls, high detail) | Mid or top tier |
| `TEXT_SMART` | Questions, extraction, read-back, Ask, briefing | Mid or top tier, with structured outputs |
| `TEXT_FAST` | Utterance classification, translation | Cheapest tier |
| `STT` | `whisper-1` (segment timestamps) / `gpt-4o-transcribe-diarize` (timestamped, speaker-labelled segments) | Only these give the timestamps the timeline needs |
| `TTS` | Synthetic OR speech (D6), read-back audio (optional) | TTS with JA and EN voices |
| `EMBED` | H1 | Embedding model |

**Cost controls:**
- Use the **Batch API** for the offline pipeline (about 50% cheaper; nothing there needs to be real-time).
- Use prompt caching for the step atlas.
- Cache every response on disk, keyed by a hash of the request.
- Set a hard monthly spend limit on the API key.
- **Rough estimate:** a few dollars per hour of processed video, so roughly $50–200 for the whole MVP. Verify against current prices on setup day.

---

## 4. Contracts (frozen at the end of Phase 0)

### 4.1 Conventions

- **Time:** seconds as floats, measured from the start of the *normalised* video.
- **Evidence:** a Media Fragment such as `video.mp4#t=2280.0,2520.0`.
- **IDs:**
  - Cases: `grasp-01`, `yt-en-03`, `yt-ja-02`
  - Moments: `grasp-01.m07`
  - Questions: `grasp-01.m07.q1`
  - Records: UUIDv7
- **Text:** every human-readable field is `{ "ja": "...", "en": "..." }`.
- **Versions:** every file carries `"contract_version": "1.0"`. Adding a new **optional** field is fine. Anything else needs both developers to agree and a version bump.

### 4.2 Contract #1: the Case Package (`data/cases/<case_id>/`)

| File | Contents |
|---|---|
| `case.json` | id, title, source (`grasp` / `psi-ava` / `youtube`), source URL, language, `video_type` (`full` / `edited`), `narrated` (true/false), duration, `step_source` (`ai` / `dataset`), data note |
| `video.mp4`, `poster.jpg`, `thumbs/` | Normalised video and images |
| `timeline.json` | `steps[]` (step_id, start, end, confidence, source); `events[]` (type, start, end, confidence, signals, source); `instruments[]` (S); `utterances[]` (start, end, speaker, text{ja,en}, class, source) |
| `moments.json` | Ranked `moments[]`: kind (`deviation` / `event` / `speech` / `checkpoint`), step_id, t_start, t_end, clip path, why_flagged (list of signals), score, deep-look description, draft obstacle (taxonomy id) |
| `questions.json` | `operating[]` and `reviewer[]` question sets: id, moment_id, type, text{ja,en}, ai_draft{ja,en}, tap_options[], est_seconds, quote (the narration being confirmed, if any) |
| `clips/` | `<moment_id>.mp4` and `.jpg` |
| `seed_records.json` | Decision Records for the seed knowledge base: 🧪 Simulated answers (M), 🎙️ narration-mined records (S) |
| `metrics.json` | GraSP cases only: AI step accuracy against ground truth |
| `trainee.json` | (S) Pause points and choices |

### 4.3 The Decision Record (extended knowledge unit)

```
DecisionRecord
├─ id, case_id, moment_id, step_id, language
├─ kind: rescue | anticipatory | checkpoint | bail_out | deliberate_non_action
├─ context:        { patient_factors[], preop_plan, step }
├─ situation_cue:  { text{ja,en}, cue_terms[] }
├─ obstacle:       { family, type (taxonomy id) | null, cause: patient|event|technical|equipment|unknown }
├─ anticipation:   text | null        (what the surgeon expected or planned)
├─ action:         { type: act | deliberate_non_action, text, actor: surgeon|assistant|resident|bedside|anesthesia|unknown }
├─ alternatives[]: { option, why_not }
├─ reason:         text
├─ immediate_result: text | null
├─ delayed_outcome:  { status: pending|known|not_applicable, text|null, source|null }   ← linked later
├─ evidence[]:     { media_fragment | transcript_span | answer_audio }
├─ grounding[]:    { field, quote }   ← every filled field points to the answer words that support it (G5)
├─ provenance:     { trust_label, attributed_to (role), generated_by {model_tier, prompt_version},
│                    confirmed_by, confirmed_at }
├─ new_terms[]
└─ confidence
```

Several records may point to the **same moment**; they are different viewpoints, all kept. For OpenAI strict structured outputs, the schema keeps every key required, with `null` allowed where a value may be missing, and sets `additionalProperties: false`.

### 4.4 Contract #2: the Brain API (runtime, `:8100`)

| Endpoint | Input | Output | Pri |
|---|---|---|---|
| `GET /health` | — | status, model tiers, cache mode | M |
| `POST /v1/answers/transcribe` | audio (webm/mp4), language hint | text, detected language | M |
| `POST /v1/answers/extract` | question, moment, case context, answer {mode: tap/voice/text, tap_choice, text, lang}, answerer role | DecisionRecord draft, read-back {ja,en}, missing_fields[], new_terms[] | M |
| `POST /v1/embed` | texts[] | vectors[][] | M |
| `POST /v1/ask` | query, lang, candidate records (top-k from the store) | answer {ja,en}, citations[record_id], coverage: full/partial/none | M |
| `POST /v1/briefing` | case factors (optional), lang, candidate records | briefing sections with citations | S |

The Brain API is **stateless**: it never touches the database. The app server sends it whatever records it needs.

### 4.5 Fixtures (built in Phase 0, so Dev2 can start immediately)

- `contracts/fixtures/case-fixture-01/`: a complete, hand-made case package. It uses a short video excerpt, plausible steps, 6 moments, a question set and 5 seed records.
- `contracts/mock_brain/`: a 50-line FastAPI app that returns fixture responses for every Brain API endpoint.
- `contracts/validate.py`: validates any case package or API response against the schemas. Both developers run it.

---

## 5. Repository layout and ownership

```
ScrubGPT/
├─ CLAUDE.md                 ← shared rules for both devs' Claude sessions (ownership, contracts, conventions)
├─ docs/                     ← idea, research, this plan, demo script
├─ contracts/                ← SHARED · frozen after Phase 0 · changes need both devs
│   ├─ models/               ← Pydantic source of truth
│   ├─ schema/  ts/          ← generated JSON Schema + TS types
│   ├─ brain_api.md          ← endpoint spec
│   ├─ fixtures/  mock_brain/  validate.py
├─ knowledge/                ← Dev1: rulebooks/rarp.yaml · taxonomy/obstacles.yaml · vocab/terms.yaml · atlas/
├─ brain/                    ← Dev1: pipeline/ · engines/ · api/ · prompts/ (versioned) · cli.py · CLAUDE.md
├─ app/
│   ├─ server/               ← Dev2: FastAPI app server, SQLite store · CLAUDE.md
│   └─ web/                  ← Dev2: React app · CLAUDE.md
├─ scripts/                  ← start_demo, reset_demo, validate_all
└─ data/  (git-ignored)      ← raw/ · cases/ · cache/   → synced via a shared drive, never committed
```

**Rule:** Dev1 edits only `knowledge/` and `brain/`; Dev2 edits only `app/`. Both edit `contracts/` only together. Each folder's `CLAUDE.md` tells that developer's Claude the same rule, so neither AI companion strays into the other's area.

---

## 6. Phases and schedule

### Phase 0: Contract Sprint (Days 1–3, **both devs together**)

This is the only phase where the two developers depend on each other.

| Day | Work |
|---|---|
| 1 | Create the GitHub repo, CODEOWNERS and `CLAUDE.md` files. Set up the environment on **all three machines** (uv, Node LTS, FFmpeg, and an ARM64 check; see §9). Set up the OpenAI key with a spend limit and confirm the model tiers. Set up the shared drive |
| 2 | Write the Pydantic contracts (§4) and generate the schemas and TS types. Write the Brain API spec. Agree the conventions |
| 3 | Build the fixture case package, the mock Brain and `validate.py`. Each developer runs a "hello world" against the contracts. **Tag `contracts-v1.0`** |

**Exit criteria:** `contracts-v1.0` is tagged; Dev2's empty app loads the fixture case; Dev1's CLI validates the fixture.

### Phase 1: Parallel build (independent tracks)

#### Dev1, the Brain track (office PC; home Surface for code and prompt work)

| Week | Deliverables | Milestone |
|---|---|---|
| **W1** (Days 4–5 and on) | B1–B4: download GraSP; select and download **10–12 YouTube RARP videos** (criteria in §7); normalise everything. A1, A3, A4: Rule Book v0.9, taxonomy, vocabulary. A6: step atlas from GraSP ground truth. C1: frame sampler | 12+ normalised cases; `rarp.yaml` drafted |
| **W2** | C2, C3, C5, C7, C8: step recognition with rule-book decoding; event heuristics; **evaluated on GraSP ground truth**, with 2–3 rounds of prompt changes. D1–D4: transcription, translation and classification for the YouTube cases | `timeline.json` for both golden cases; first accuracy numbers |
| **W3** | E1–E6: fusion, deviations, checkpoints, ranking, clip cutting. C6: deep look. F1–F3, F5–F7: question engine, both styles, bilingual | **Full case packages for the 2 golden cases** (dropped onto the shared drive) |
| **W4** | G1–G3, G5 and H1–H2: Brain API (transcribe, extract, read-back, embed, ask). Seed records (🧪 simulated answers run through G2). Batch-process all cases | **All Brain M-features done**; all case packages validated |
| **W5** (6-week plan) | S-features: D5–D7 (narration mining, synthetic OR speech), F4, G4, H3, H4. Offline cache recording for all demo paths | Brain S-features done |

#### Dev2, the App track (Zenbook, at home)

| Week | Deliverables | Milestone |
|---|---|---|
| **W1** (Days 4–5 and on) | I1: app server and case loader with validation. Web skeleton, design system and layout. J15 i18n. J1 home. Video player component with speed control | Fixture case browsable in JA and EN |
| **W2** | J2 **Control Room**: replay sync engine (§8.2), step bar, event markers, transcript ticker, alerts, "surgery ends" flow. J8 graph panel (Cytoscape) on fixture data. I5 SSE plumbing | Control Room plays the fixture "live" |
| **W3** | J3 **Answer app**: question cards, clip loop, tap/voice/text, MediaRecorder, read-back, confirm/edit chips. I2 knowledge store. I7 brain client (mock). Confirmed answers update the graph through SSE | Full answer loop working against the mock Brain |
| **W4** | J5 **Library**, J4 **Case Explorer**, J6 **Ask**, J9 provenance drawer, J16 disclaimers. I3 pattern counts, I4 retrieval, I6 seed/reset | **All App M-features done** against fixtures and mocks |
| **W5** (6-week plan) | S-features: J7 Procedure Map, J8 full graph page, J10 reviewer queue, J11 trainee mode, J12 briefing, J14 admin/metrics, I8 audit log | App S-features done |

**Optional, zero-coupling check (recommended):** each Friday, Dev1 drops the latest real case packages onto the shared drive. Dev2's loader validates them. This is a **data-only** check, with no code merging, and it catches contract drift weeks before integration.

### Phase 2: Integration (end of the project, as requested)

| Day | Work |
|---|---|
| 1 | `validate_all` on every real case package. Switch the brain client from **mock to real**. Run the golden case end to end |
| 2 | Load all cases and the seed knowledge base. Run the Ask, answer and extraction paths on real data. Fix contract mismatches |
| 3 | Record the offline cache: run every demo path once so all OpenAI responses are cached. Test with Wi-Fi off. Run on both candidate demo laptops |

### Phase 3: Polish and rehearsal

Fix UI rough edges, tune the demo cases, complete the bilingual copy, write the demo script (§10), rehearse three times (once per audience emphasis), then apply the **freeze tag**.

### Calendar

| | 4-week plan (M only) | 6-week plan (M + S) |
|---|---|---|
| Phase 0 | W1 Days 1–2 (compressed) | W1 Days 1–3 |
| Phase 1 | W1 Day 3 to W3 | W1 Day 4 to W5 |
| Phase 2 | W4 Days 1–3 | W6 Days 1–3 |
| Phase 3 | W4 Days 4–5 | W6 Days 4–5 |

---

## 7. Data plan

| Set | What | Purpose |
|---|---|---|
| **GraSP** (13 full RARP videos, about 32 h, phase/step ground truth, MIT) | All of it | Golden case G1, the step atlas, the accuracy evaluation, ground-truth mode |
| **PSI-AVA** | Overlaps with GraSP | Extra atlas frames if needed |
| **YouTube RARP**, 10–12 videos | **Mix:** about 6 English-narrated, **about 4 Japanese-narrated** (e.g. search 「ロボット支援前立腺全摘除術 手術動画 解説」), 1–2 un-narrated. **Prefer** full-length or lightly edited, HD, and **cases with difficulty**: median lobe, large prostate, DVC/pedicle bleeding, prior TURP or hernia mesh adhesions, difficult apex | Golden case G2 (JA narration), seed knowledge base, real speech |

**Golden cases:**
- **G1:** a GraSP case. Ground-truth steps (with AI steps alongside for comparison), synthetic OR speech (S), the main "live" replay.
- **G2:** a Japanese-narrated YouTube case, showing the bilingual demo and real speech.

**Seed knowledge base:**
- About 8–12 processed cases.
- About 40–80 decision records (🧪 Simulated answers, written with Claude/GPT from narration and the literature and pushed through G2), plus 🎙️ narration-mined records (S).
- **All of them are replaced or confirmed when the surgeon joins.**

**Handling:**
- `data/` stays out of git, and videos are shared only through a private shared drive.
- The demo stays private, per the owner's decision.
- Edited YouTube videos are flagged `video_type: edited`, which **switches off duration-based deviations** for them.

---

## 8. How the key parts work

### 8.1 Step recognition without training (C1–C3)

1. Sample one frame every 5 s at low detail. A 3-hour video gives about 2,160 frames.
2. Group the frames into 1-minute windows of 12 frames each.
3. Send each window to GPT `VISION_FAST` with: the rule-book step list (JA/EN descriptions), **atlas reference frames per step** (cached prompt), and the step decoded for the previous window. GPT returns a probability for each step, plus visible events and instruments.
4. **Viterbi decoding:** the steps must follow the rule-book order (with allowed skips and repeats) and use typical-duration priors. This turns noisy guesses into clean segments.
5. **Measure against GraSP ground truth** (C7) and show the numbers honestly in the admin view. For GraSP demo cases, ground-truth mode (📐) is available.

### 8.2 "Live" replay (J2)

- The browser `<video>` is the **master clock**. Its `currentTime` drives everything.
- The app reveals each timeline item when `currentTime ≥ item.t`. Speed changes and seeking can therefore never put things out of sync.
- When the video ends, the app server raises a "questions ready" event over SSE, and the phone frame shows its notification.
- Everything heavy is **precomputed**. C9 (true live processing) is a stretch goal.

### 8.3 Answering (J3 + G1–G3)

```
question card (clip loops) ─► [Tap ✓/✎/✗ + choices] or [🎙 hold to speak] or [⌨ type]
   ─► (voice) /transcribe ─► /extract ─► read-back chips (JA/EN) ─► Confirm
   ─► app server stores the record + provenance ─► SSE ─► graph and library update live
```

The **phone** is shown as a phone-sized frame on the laptop screen (the default, which is reliable offline). An optional real phone can connect over local HTTPS using mkcert (C). Browsers only allow microphone access on `localhost` or over HTTPS.

### 8.4 Ask (H2 + I4 + J6)

1. The query is embedded.
2. The store returns the top-k records.
3. `/v1/ask` answers **only from those records** and cites them.
4. The UI shows the answer with playable cited clips.

When nothing relevant exists, it says so; it never guesses.

---

## 9. Machines and environment

| Machine | Role | Notes |
|---|---|---|
| **Office PC** (x64, i5-1334U, 32 GB) | Dev1's main machine; **all video processing**; demo laptop candidate #1 | Python, Node, Git, FFmpeg and Docker are already installed. 216 GB free |
| **Surface** (ARM64, 16 GB) | Dev1 at home: code, prompts, short runs | |
| **Zenbook** (ARM64, 48 GB) | Dev2's main machine; demo laptop candidate #2 | |

**ARM64 rules:**
- The stack has **no CUDA, PyTorch or OpenCV**. Pillow, numpy, pydantic, FastAPI and the OpenAI SDK all run on ARM64.
- If a Python wheel fails on ARM64, install **x64 Python through uv**. It runs under Windows' built-in x64 emulation.
- Use the ARM64 Node LTS build, and ARM64 or x64 FFmpeg.
- Docker is **not** required.
- Phase 0, Day 1 includes a smoke test on all three machines.

---

## 10. Demo script (8–10 minutes; the order changes with the audience)

1. **The problem** (30 s): hours of video, and the reasoning is lost.
2. **Procedure Map / Rule Book** (30 s): this is RARP, structured.
3. **Control Room** (2 min): G1 plays "live" at 8×. Steps light up; the AI flags DVC bleeding and "bladder neck took longer than usual"; a checkpoint appears; the transcript scrolls.
4. **Surgery ends, then the phone** (2 min): "4 questions · ~3 min". Answer one by **tap**, one by **voice in Japanese**, one by **text**. Read-back, confirm.
5. **Knowledge grows** (1 min): new nodes appear in the graph; the new record shows its 🩺 or 🧪 trust label.
6. **Library** (1 min): the "DVC bleeding" card shows 4 cases, different ways of handling it, and viewpoints side by side with counts.
7. **Ask in Japanese** (1 min): 「中葉肥大がある場合、膀胱頸部でどう対処した？」 ("When there is a median lobe, how did surgeons handle the bladder neck?") The answer comes with cited clips.
8. **Trainee mode** (S, 1 min).
9. **Scale and honesty** (30 s): a new surgery only needs a new rule book; AI accuracy is shown honestly; every fact has provenance.

**Emphasis by audience:**
- **Investors:** 3, 5 and 9.
- **Surgeons:** 4, 6 and 7. The graph stays in the background.
- **Hospital:** 6, 7 and the privacy/provenance story.

---

## 11. Definition of Done (every feature)

- Works on real or fixture data, and **passes `validate.py`** wherever a contract is involved.
- **JA and EN** both present.
- **Provenance is visible** for every piece of knowledge it shows.
- Reviewed with Claude (`/code-review`); the developer's own folder only.
- One-paragraph usage note in the module's README.

---

## 12. Risks and mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **GPT-only step recognition is inaccurate** (published GPT surgical-phase F1 is about 0.36) | Wrong step durations lead to false deviations | Step atlas as few-shot examples, rule-book Viterbi decoding, ground-truth mode for GraSP, honest metrics, and a human confirms every fact anyway |
| 2 | **YouTube videos are edited** (cuts, time-lapse) | Duration deviations become meaningless | `video_type: edited` switches them off; use event, speech and checkpoint moments instead |
| 3 | **YouTube narration is a lecture, not real OR talk** | Speech classes differ | A "teaching" class, the 🎙️ trust label, and honest framing. Narration is in fact a rich source of reasons |
| 4 | **Integrating at the end** | Late surprises | Frozen contracts, generated types, fixtures, a mock Brain, `validate.py`, and the optional Friday data drop |
| 5 | ARM64 environment problems | Lost days | Pure-Python stack, x64 emulation fallback, a Day-1 smoke test, heavy processing on the x64 office PC |
| 6 | Phone microphone needs HTTPS | Voice answers fail on a real phone | The phone frame on the laptop is the default; mkcert HTTPS is optional |
| 7 | OpenAI cost, latency or downtime during the demo | Demo stalls | Batch API offline; disk cache; recorded offline cache; typed or tap answers as fallback; phone hotspot as backup |
| 8 | Medical accuracy of the rule book without a surgeon | Loses surgeons' trust | Built from GraSP's taxonomy and published RARP literature; labelled "draft, pending urologist review"; first job for the surgeon later |
| 9 | Hallucinated reasons in extraction | Destroys trust | G5 grounding (each field quotes the answer), "not stated" stays empty, read-back confirmation |
| 10 | Scope creep (about 70 features) | Missed deadline | MoSCoW: M features first on both tracks; S starts only when M is done |
| 11 | GPT refuses or weakens on surgical images | Gaps in the timeline | Medical/education framing in the system prompt, retry with a different tier, and the gap is marked "not analysed" |

---

## 13. Setup items: confirmed and still open

**Confirmed by the owner (2026-10-16):**

| Item | Decision |
|---|---|
| Schedule | **6-week plan (M + S)** |
| Repo | Private GitHub repo on **`karthi-ai-engineer`**; Dev2 added as a collaborator |
| Shared drive for `data/` | **Google Drive** (Google Drive for desktop sync) |
| Friday data drop | **Yes.** A data-only contract check every Friday, with no code merging |

**Still open:**

1. **OpenAI API key** with a monthly spend limit. The owner pastes it into a git-ignored `.env` file, never into chat or git. Confirm the model names and prices for each tier on Day 1.
2. **Dev2's availability** for Phase 0 (Days 1–3, at least the Day 2 contract review). Also Dev2's GitHub username, for collaborator access.
3. Main demo laptop (office PC or Zenbook). This can wait until Phase 2.
4. Product or demo name for the UI title. This can wait until Phase 3.

---

## Appendix A: RARP Rule Book skeleton (draft, pending urologist review)

**Phases** (standard anterior approach; to be mapped to GraSP's 11 phases / 21 steps in W1):

| # | Phase (EN) | 日本語 | Checkpoint(s) | Known obstacles |
|---|---|---|---|---|
| 1 | Port placement and docking | ポート留置・ドッキング | — | Adhesions from prior surgery, obesity |
| 2 | Pelvic lymph node dissection (optional) | 骨盤リンパ節郭清 | Obturator nerve identified | Vessel bleeding, nerve proximity |
| 3 | Retzius space development / bladder drop | レチウス腔の展開 | Space adequately developed | **Hernia-mesh adhesions**, obesity |
| 4 | Endopelvic fascia and DVC control | 内骨盤筋膜切開・DVC処理 | DVC secured | **DVC (Santorini) bleeding** |
| 5 | Anterior bladder neck dissection | 膀胱頸部前壁の切開 | Bladder neck identified | **Median lobe**, large prostate, prior TURP |
| 6 | Posterior bladder neck dissection | 膀胱頸部後壁の切開 | **Ureteral orifices identified** | Median lobe, wide bladder neck |
| 7 | Seminal vesicle and vas dissection | 精嚢・精管の剥離 | SVs fully mobilised | Inflammation, bleeding from SV artery |
| 8 | Posterior dissection (Denonvilliers) | 後面剥離（デノンビリエ筋膜） | Correct plane, rectum safe | **Adherent plane / rectal injury risk** |
| 9 | Pedicle control and nerve sparing | 側方茎処理・神経温存 | **Nerve-sparing grade decided** | Pedicle/NVB bleeding, accessory pudendal artery |
| 10 | Apical dissection and urethral transection | 尖部処理・尿道切断 | Urethral length kept, margin check | Difficult apex, positive-margin risk |
| 11 | Posterior reconstruction (optional) | 後壁再建（Rocco） | — | Tissue tension |
| 12 | Vesicourethral anastomosis | 膀胱尿道吻合 | **Leak test watertight** | Anastomotic tension, leak |
| 13 | Specimen extraction and closure | 標本摘出・閉創 | Haemostasis at low pressure | Port-site bleeding |

**Universal obstacle families:** Bleeding · Anatomical variation · Tissue condition · Visibility · Technical difficulty · Equipment · Patient condition · Unexpected finding. The RARP-specific obstacles above sit beneath these as leaves.
