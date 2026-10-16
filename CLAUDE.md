# ScrubGPT: Surgical Knowledge System (MVP)

This project turns recorded **RARP** (robot-assisted radical prostatectomy) videos into **surgeon-verified decision knowledge**. The AI finds *what* happened; the surgeon explains *why* (by tap, voice or text); the answers become linked, provenance-tagged records that surgeons can browse and query in Japanese or English.

- **Organisation:** MY ROBOTS
- **Owner:** Muthiah Karthi, who is also Dev1
- **Scope:** MVP demo only
- **Schedule:** 6 weeks (Must + Should features)
- **Status:** see `docs/status/project.md`

## The repo is the shared memory

Dev1's and Dev2's Claude sessions run on **different machines and accounts**, so they **cannot see each other's chats or local memory**. Everything a session needs is in the repo. The rules (this file and the track `CLAUDE.md` files) arrive with `main`. **Read the status files from `origin/main`**; they are only edited on `main`.

| File | Purpose | Who edits |
|---|---|---|
| `CLAUDE.md` (this file + `brain/`, `app/server/`, `app/web/`) | Rules for every session | Orchestrator, on `main` |
| `docs/status/project.md` | Phase, shared checklist, waiting-on, key dates, **merge log**, Friday drop log | Orchestrator; others only tick shared items they finished |
| `docs/status/dev1.md` / `dev2.md` | That developer's live checklist, current task, blockers, **requests for the other developer**, drop results, session log | **Only that developer's session** |
| `docs/DECISIONS.md` | Every decision and why it was made (append-only; **newest entries win**) | Orchestrator, or any session when the owner decides something |
| `docs/Work_Split.md` | How the parallel tracks work, timeline, daily routine | Orchestrator |
| `docs/MVP_Master_Plan.md` | The plan. Feature IDs such as `C3` and `J2`; **§4 is the contract spec** | Orchestrator (contract parts follow D-033) |
| `docs/ONBOARDING.md` | Machine setup | Orchestrator |
| `docs/TEAM.md` | **The agent team**: roles, full and light paths, labels, test brief and report templates (D-042 … D-046) | Orchestrator |
| `.github/team-lead/ROLE.md`, `.claude/agents/*.md` | Instructions for the Team Lead (on GitHub), its research assistant and system designer, and the two testers | Orchestrator, on `main` |
| `docs/visualizer/index.html` | **Process Visualizer**: one animated page (plan §14). Created after `contracts-v1.0`, extended after every phase or block | Orchestrator |
| GitHub issues (`request`, `contracts`, `blocker`, `bug`, `question`) | Cross-track requests, contract changes, bugs, questions. The Team Lead checks each one first (D-040, D-042) | Anyone |
| `docs/Research_Report_Phase0.md`, `docs/Surgical_Knowledge_System_Idea.md` | Background (rarely needed) | — |

## Session protocol (every session, every machine)

**Start**: when the developer says *"I'm Dev1"* or *"I'm Dev2"* (if they don't say, ask):
1. Check the identity. Office machines are shared models, so check every time (D-046):
   - `gh auth status`: the **active** account must be this developer's: Dev1 `karthi-ai-engineer`, Dev2 `TharunAppireddy`. If another account is active, run `gh auth switch -u <login>`.
   - `git config --local --get user.email` must be that account's noreply address: Dev1 `296384397+karthi-ai-engineer@users.noreply.github.com`, Dev2 `179685213+TharunAppireddy@users.noreply.github.com`.
   - `git config --local --get credential.https://github.com.username` must be that login, so `git push` can't use a company account cached on the machine.
   - If anything is wrong, fix it **repo-locally** (`git config --local …`, never `--global`) before any commit or push, then check with `git push --dry-run`.
2. `git fetch`. Read `docs/status/project.md`, **your** `docs/status/devN.md`, and the **"Requests for DevN"** section of the *other* developer's status file, all **from `origin/main`** (e.g. `git show origin/main:docs/status/dev2.md`). Skim the newest `docs/DECISIONS.md` entries. Run `gh issue list --state open` to catch requests, blockers and contract changes. Then:
   - Run `gh issue list --label analysis --label devN`: requests the Team Lead routed to **you**. Each one gets your **analysis comment** (ACCEPT / QUESTION / PUSH BACK, template in `docs/TEAM.md` §7) **before** you start your own next task. Blockers come first.
   - Run `gh issue list --label accepted --label devN`: accepted requests you are building.
   - Run `gh issue list --label blocker`: blockers come before everything else.
   - Run `gh pr list --search "review-requested:@me"`: PRs waiting for **your** approval (e.g. the other developer's contract PRs, D-033).
   - Run `gh pr list --author @me`: your open PRs. For each, read the Team Lead's **latest review** comment. Fix CHANGES NEEDED first.
3. Switch to your current branch (see Git workflow), or create it from `main` if it doesn't exist. **If `main` changed anything other than `docs/status/` since your branch last had it** (block merge, contract change, `CLAUDE.md` or `docs/` update), merge `main` into your branch first, so you work with the current rules.
4. Reply with a short briefing:
   - the current phase or block;
   - what's done;
   - blockers;
   - requests and issues for you, **marking the ones waiting for your analysis**;
   - PRs waiting for your approval, and the latest Team Lead verdict on yours;
   - the **proposed next task**: a blocker, else an analysis that's due, else a CHANGES NEEDED fix, else the first unchecked item in your checklist.
5. When the developer agrees, work **only in your track's folders** (in Phase 0 and in contract changes: **only your assigned files in `contracts/`**, D-031). **Before you tick a code task, run your tester** (`docs/TEAM.md` §4). Phase 0 Day 2 work is tested together on Day 3.

**End**: when the developer says *"End session"*, or a task is finished:
1. Commit the work on your branch and push. Use the message prefix per D-041, e.g. `C3: …` or `P0: …`.
   - Your tester's own commits (`T1: …` / `T2: …`) stay separate. **Never stage a tester's folders.** Stage with an exclude, e.g. Dev2: `git add -- app ':(exclude)app/server/tests/acceptance' ':(exclude)app/web/tests/acceptance'`; Dev1: `git add -- brain knowledge ':(exclude)brain/tests/acceptance'`.
   - Don't push tester commits whose tests still FAIL. Push once the fix makes them pass.
2. **Update your status file on `main`**:
   - tick finished items, **only those with a tester PASS**;
   - update "Current task", "Blockers" and "Requests for <other>";
   - add one session-log line that includes the tester results (e.g. `C3 done, T1 PASS 7/7`).
   
   Commit as `status(devN): …` and push.
3. If the owner decided anything, append it to `docs/DECISIONS.md` on `main` (`decision: D-0xx …`).
4. Tell the developer what's done and what's still unverified.

**Cross-track needs.** Never edit the other track's folders. Open a **Request** issue (or a **Contract change** issue). The Team Lead checks it and routes it to the other developer. Add one line with the issue number under "Requests for <other>" in **your** status file, and tell your developer to ping the other developer if it's urgent.
- **From the command line, always add the labels the form would add.** Without `triage`, the Team Lead never starts. Example: `gh issue create --title "[request] …" --label request --label triage --body-file <file>`, with a body that follows the form's fields (`.github/ISSUE_TEMPLATE/`).
- If you forgot `triage`, start it with a comment that begins `/team-lead triage`.

## Working agreement

- **The team (D-042, `docs/TEAM.md`):**
  - The **Team Lead** is a Claude agent that runs on GitHub. It checks and routes every request, answers questions (comments that start with `/team-lead`) and reviews every pull request into `main`. Its assistants are a researcher and a system designer.
  - **If the Team Lead is unavailable** (no secret yet, an outage, or no reply within 30 minutes), the orchestrator stands in: it follows `.github/team-lead/ROLE.md` by hand and posts under the heading `🧭 Team Lead (stand-in) · …`. The orchestrator runs in Dev1's session, so a stand-in verdict on Dev1's own work (a Dev1-authored PR, a Dev1-track PR, or a request Dev1 sent) counts only with **Dev2's explicit OK** in a comment. Otherwise it counts like the Team Lead's own.
  - Each developer has an **independent tester** (a subagent).
  - The **orchestrator** is the Claude session on Dev1's office PC (D-016). It keeps the plan, decisions, contracts process, project status, **block merges and the Process Visualizer** coherent, and logs Team Lead decisions (`to-log`).
  - Sessions on Dev2's machines follow the repo files and raise anything unclear with `/team-lead`.
- **The owner makes product and scope decisions.** Claude recommends, and makes technical or process calls the owner has delegated. Log every decision in `docs/DECISIONS.md`.
- When several decisions are open, ask them together as quick multiple-choice questions.
- Report outcomes honestly. If something is untested, failing or skipped, say so.

## The agent team: how work moves (D-042 … D-046; full guide in `docs/TEAM.md`)

| Path | For | Steps |
|---|---|---|
| **Full** | Contract changes, requests between Dev1 and Dev2, bugs found in the other track, blockers, **every PR into `main`** | Issue → Team Lead triage → receiving developer's analysis → build → tester → Team Lead review (READY) → approvals → orchestrator merges |
| **Light** | Your own checklist tasks and bugs in your own track | Build → your tester → PASS → tick |

- **Ask the Team Lead:** start a comment with `/team-lead` and your question, on any issue or in a PR's conversation (not an inline review comment), or open an **Ask the Team Lead** issue. It answers on GitHub. The comment must **start** with `/team-lead`; anywhere else it does nothing. Don't call the `researcher` or `system-designer` agents yourself; they work for the Team Lead.
- **Requests sent to you:** analyse them first (ACCEPT / QUESTION / PUSH BACK), using the template in `docs/TEAM.md` §7. Show the analysis to your developer before posting it. Move the labels as `docs/TEAM.md` §7 says. Disagreements go to `/team-lead`. Product or scope questions go to the owner (label `decision`).
- **Your tester:** Dev1 → **`tester-brain`** (T1); Dev2 → **`tester-app`** (T2).
  - Commit your work first. Then start it with **only a test brief** (`docs/TEAM.md` §6): feature IDs, spec references, acceptance criteria, the commit, how to run it. Never your reasoning about the implementation.
  - Run it in the **foreground**, and don't touch the working tree until it reports. It shares your checkout.
  - It writes acceptance tests from the spec in its own folders, commits them as `T1: …` / `T2: …`, and reports PASS / FAIL / BLOCKED.
  - **FAIL:** fix the code, never the tests. If you think a test is wrong, re-brief the tester with "dispute: …".
  - **Spec gaps:** start a `/team-lead` comment on the related issue or PR, or open an **Ask the Team Lead** issue, and name it in the next brief.
- **If you are the Team Lead running on GitHub,** follow `.github/team-lead/ROLE.md` instead of the session protocol.

## Two tracks: ownership is the most important rule

Two developers build **in parallel** and integrate at the end. They are coupled **only** through `contracts/`.

| Path | Owner | Track |
|---|---|---|
| `knowledge/`, `brain/` | **Dev1** | Brain: offline pipeline + stateless Brain API |
| `app/server/`, `app/web/` | **Dev2** | App: app server, knowledge store, web UI |
| `contracts/` | **Shared, file by file (D-031).** Every change is **approved by the other developer** (D-033). Frozen after the `contracts-v1.0` tag | The contracts |
| `brain/tests/acceptance/`, `contracts/tests/acceptance/t1/` | **Tester 1** only (`T1:` commits, D-044) | Acceptance tests for Dev1's work |
| `app/server/tests/acceptance/`, `app/web/tests/acceptance/`, `contracts/tests/acceptance/t2/` | **Tester 2** only (`T2:` commits, D-044) | Acceptance tests for Dev2's work |
| `docs/`, `scripts/`, root files (`pyproject.toml`, `uv.lock`, …) | Orchestrator, on `main`; status files per developer | — |
| `.github/`, `.claude/`, **every `CLAUDE.md`** (also `brain/`, `app/server/`, `app/web/`) | Orchestrator, **only on `main`**. CI rejects them on every work branch (D-046): they steer CI, the Team Lead and every session | — |

**Inside `contracts/` (D-031):**
- **Dev1** owns `scrubgpt_contracts/models/{common,case_package,decision_record,reference}.py`, `scrubgpt_contracts/validate.py`, `fixtures/cases/`, `fixtures/reference/` and `pyproject.toml`.
- **Dev2** owns `scrubgpt_contracts/models/brain_api.py`, `brain_api.md`, `scrubgpt_contracts/mock_brain/`, `scrubgpt_contracts/codegen/` and `fixtures/brain_api/`.
- `schema/` and `ts/` are **generated** by `scrubgpt-codegen`. Never edit them by hand.

**Rules:**
- **Know which developer you are working for.** If it isn't clear, ask once.
- **Never edit the other track's folders or files.** Write a request instead.
- **Never work around a contract.** If a contract seems wrong, stop and raise it.
- **Each track replaces only its own placeholder `pyproject.toml`** (D-031). Dependency changes update the root `uv.lock`. If it conflicts at a block merge, the orchestrator re-runs `uv lock`.

### The contracts (spec: plan §4)

1. **Case Package** (files in `<DATA_DIR>/cases/<case_id>/`): `case.json`, `video.mp4`, `poster.jpg`, `thumbs/`, `timeline.json`, `moments.json`, `questions.json`, `clips/`, `seed_records.json`, plus `metrics.json` (GraSP cases). Required files are listed in plan §4.2.
2. **Procedure Reference** (`<DATA_DIR>/reference/<procedure_id>.json`): steps, checkpoints and the obstacle taxonomy, with bilingual names (D-035).
3. **Brain API** (HTTP; real Brain on `:8100`, **fake Brain on `:8101`** with identical endpoints and shapes): `/health`, `/v1/answers/transcribe`, `/v1/answers/extract`, `/v1/translate`, `/v1/embed`, `/v1/ask`, `/v1/briefing` (S).

**Shared primitives** are fixed in plan §4.1 and must be reused exactly: `Bilingual`, `TrustLabel`, `Role`, `Provenance`, `Evidence`, `ApiError`, the ID formats, the field-path syntax (`a.b[0].c`) and `contract_version`. The core knowledge unit is the **DecisionRecord** (plan §4.3); `/extract` returns a **DecisionRecordDraft**.

**Compatibility (D-023, D-034):**
- `contract_version` is `"MAJOR.MINOR"`.
- v1.0 fields are required keys (nullable where they may be absent). A field added later is `T | None = None` (MINOR). Anything breaking is MAJOR.
- **Every** contract change needs the other developer's approval; a MAJOR change needs agreement *before* starting (D-033).
- Contract models are **tolerant readers** (`extra="ignore"`). Strict OpenAI structured-output schemas are internal to `brain/`.

## Conventions (both tracks)

- **Time:** seconds as a float from the start of the normalised video; always `t_start` / `t_end`.
- **Evidence:** Media Fragment URIs, e.g. `video.mp4#t=2280.0,2520.0`.
- **Bilingual:** every human-readable field is `{ "ja": "...", "en": "..." }`, both non-empty. No English-only UI strings or content.
- **Provenance on every piece of knowledge,** using the trust-label enum values: `ai_detected` 🤖, `dataset_annotation` 📐, `narration_extracted` 🎙️, `operating_surgeon` 🩺, `reviewer` 👁️, `expert_validated` ✅, `simulated` 🧪.
- **Names (D-041):**
  - Work blocks are written **"Block N"** (branch `devN/bN`, milestone "BN · …"). A bare **B1–B5** means the case-ingestion *features*.
  - **Golden demo cases** are **GC1** (GraSP) and **GC2** (Japanese-narrated YouTube), not features G1/G2.
- **Relative paths** in `.env` (`DATA_DIR`, `APP_DB_PATH`) resolve against the **repo root**.

## Product guardrails (non-negotiable)

- **Education and reference only.** No clinical recommendations, no intra-operative alerts, no patient-specific predictions. A briefing is framed as *retrieval of past cases*.
- **Never invent reasoning.** A field the surgeon did not state stays `null`. Every extracted field is grounded in a quote, with `source` `answer|edit|narration` (G5).
- **Show counts, not percentages, when n < 20.**
- **No "could this have been avoided?" questions.**
- **Keep every viewpoint.** Never merge several records into one "correct" answer.
- Role-played or synthetic content is always labelled `simulated` 🧪 or "synthetic".

## Data and secrets

- Videos, case packages, the procedure reference and caches live in `DATA_DIR` (Google Drive; see `data/README.md`).
  - Dev2 uses `DATA_DIR=./contracts/fixtures` until integration (D-026).
  - **Never commit media (outside synthetic fixtures), `data/`, `.env` or SQLite files.**
- Fixture media must be **synthetic** (FFmpeg test pattern, D-036), **≤ 5 MB in total**. CI enforces this.
- Demo data (GraSP, PSI-AVA, YouTube) is for **private, internal demo use only**. **The repo is public for now** (D-014): commit nothing sensitive, and never commit real surgical frames, including in the visualizer (D-039).
- Never paste API keys into chat. The developer puts them into `.env` themselves.

## Tech stack and environment

- **Python:** **Python 3.13** (`.python-version`); a **uv workspace** at the root with members `contracts` (`scrubgpt-contracts`, importable as `scrubgpt_contracts`), `brain` (`scrubgpt-brain`) and `app/server` (`scrubgpt-app`) (D-031); Pydantic v2, FastAPI, SQLite (standard library); UUIDv7 via `uuid6`.
- **Web:** **Node 26** (`.nvmrc`); `app/web/` uses Vite + React + TypeScript, Tailwind + shadcn/ui, react-i18next, TanStack Query, Cytoscape.js.
- **Quality:**
  - Python: `ruff` (lint and format) + `pytest`, from the root `dev` group.
  - Web: `eslint` + `vitest`.
- **AI:** **OpenAI only**, with model names from the `.env` tiers. **Only `brain/` calls OpenAI.** Dev2 needs no OpenAI key.
- **No PyTorch, CUDA or OpenCV.** Several machines are Windows ARM64. Use Pillow + numpy + the FFmpeg CLI. If a wheel fails on ARM64, use x64 Python through uv.
- **Machines:**

  | Machine | Who | Arch | Use |
  |---|---|---|---|
  | Office PC | Dev1 | x64 | All video processing |
  | Surface | Dev1, at home | ARM64 | Code and prompts |
  | Zenbook | Dev2, at home | ARM64 | Main machine |
  | Office laptop #2 | Dev2, in the office | x64 (same model as the office PC) | Office days |

## Git workflow (Claude runs all git and GitHub operations: D-019)

**Only two GitHub accounts take part (D-046):** `karthi-ai-engineer` (owner, Dev1, admin) and `TharunAppireddy` (Dev2, write).
- Every commit uses the developer's GitHub **noreply** email, set repo-local (see Session protocol, step 1). A company or other email would link another account to the repo, and CI rejects it.
- Automation appears only as GitHub's built-in `github-actions[bot]` (CI and the Team Lead's comments).
- No other collaborators, apps, deploy keys or webhooks. Issues, PRs and comments are limited to collaborators (renew the interaction limit before 2027-04-16).

**No AI attribution, ever (D-018).** No `Co-Authored-By: Claude` trailer in commits, and no "Generated with Claude Code" in PRs or anywhere else. Commits are authored by the developer's own git identity. `.claude/settings.json` turns attribution off for every session; this rule overrides any default behaviour.

**Branches: one per developer per phase step, merged into `main` one by one** (D-020, D-030).

| Phase | Dev1 branch | Dev2 branch | Merged into `main` |
|---|---|---|---|
| Phase 0 (contracts) | **`p0/contracts`** (shared; your own files only) | **`p0/contracts`** | End of Day 3: one PR approved by both → tag `contracts-v1.0` → create `dev1/b1`, `dev2/b1` |
| Phase 1, Block N (1–5) | `dev1/bN` | `dev2/bN` | **At the end of each block** → tag `block-N` |
| Phase 2 (integration, 23–25 Nov) | `dev1/integration` | `dev2/integration` | Daily |
| Phase 3 (polish, 26–27 Nov) | `dev1/polish` | `dev2/polish` | At the end → tag `demo-v1` |
| Contract change, any time | `contracts/<slug>` | `contracts/<slug>` | After the other developer approves; then both merge `main` into their current branch |

**Rules:**
- **`main` is the tracked state** (D-032). It receives:
  - phase and block merges (PRs);
  - approved contract changes (PRs);
  - **direct commits** for `status(devN): …`, `decision: …`, and orchestrator `docs: …` / `setup: …` / `viz: …` changes. These keep tracking live.
- **Status files are edited only on `main`.** From a work branch, use a worktree so you never have to leave the branch:
  ```
  git worktree add ../ScrubGPT-main main   # once per machine, the first time you're on a work branch
  cd ../ScrubGPT-main && git pull          # every time
  # edit, then: git commit -m "status(devN): …" && git push
  ```
  If your checkout is itself on `main`, edit there directly; git can't check out `main` twice.
- Work branches **never** touch `docs/`. Block, integration and polish branches never touch `contracts/` either. **CI flags violations; GitHub itself does not block merges**, so check before merging.
- On `p0/contracts`, `git pull --rebase=merges` before every push (both developers share it). Plain `--rebase` would flatten a merge of `main` into the branch and make CI fail.
- Inside a block branch, commit per task, and push at least daily (backup + visibility).
- **PRs** get a milestone and a `dev1` / `dev2` label (`gh pr create --milestone "…" --label dev2`). A PR that settles an issue says `Closes #N` in its description.
- **Team Lead review (D-045):** every PR into `main` gets an automatic Team Lead review comment (**READY**, **CHANGES NEEDED** or **OWNER NEEDED**). After new pushes, ask for a re-check with `/team-lead re-check`.
- **Approval (D-021, D-033, D-045):** every merge needs the Team Lead's latest review to say **READY**, plus:
  - for a PR touching only the author's track folders: `gh pr checks <n>` all green;
  - for a PR touching `contracts/`: also an **APPROVED review by the other developer**: `gh pr view <n> --json reviews --jq '[.reviews[] | select(.state == "APPROVED") | .author.login] | unique'`. (`reviewDecision` stays empty, because no ruleset requires reviews.) The owner's OK can stand in only for **Dev2-authored** PRs.
- **Block merge (orchestrator):**
  1. Both branches pass `/code-review` (`/code-review <PR#>` works without checking the branch out), tests and contract validation.
  2. Open the PRs (`gh pr create`); check `gh pr checks` and the **Team Lead's review: READY** on both.
  3. Merge `dev1/bN`, then `dev2/bN`. If `uv.lock` conflicts, re-run `uv lock`.
  4. Tag `block-N`.
  5. Add a line to the **merge log** in `docs/status/project.md`.
  6. Create `dev1/bN+1` and `dev2/bN+1` from `main`. After Block 5, create `devN/integration` instead.
  7. **Extend the Process Visualizer** (`docs/visualizer/index.html`, plan §14, D-039) with this block's section: inputs → animated processing → outputs → connections. **Animations show data transformations, never decorative UI motion.** Commit it to `main` as `viz: …`.
- **Destructive operations** (force-push, history rewrite, deleting branches with unmerged work) happen only when genuinely required, and Claude reports them right after. `main` blocks force-push for everyone but the owner.
- **Friday data drop (D-038):**
  1. Dev1 copies the latest case packages to `<DATA_DIR>/drop/YYYY-MM-DD/`: JSON, clips, posters, plus `video.mp4` for golden cases.
  2. Dev2's loader validates them **file by file**, and Dev2's session records the result in `dev2.md` → "Drop results".
  3. The orchestrator copies it into the `project.md` drop log.

  This is data only; no code is merged.

## Definition of Done (every feature)

- Works on real or fixture data, and **validates against the contracts**.
- `ruff`/`pytest` or `eslint`/`vitest` pass; CI is green.
- **JA and EN** both present.
- **Provenance is visible** for every piece of knowledge it shows.
- Reviewed with `/code-review`.
- **Your tester reports PASS**, and its acceptance tests are committed (`T1:` / `T2:`, D-044). For full-path work, the tester report is posted on the issue.
- A one-paragraph usage note in the module README (each track documents its own commands there).

## Commands

Available now (office PC verified):

```
uv sync --all-packages          # install the workspace + dev tools (ruff, pytest)
uv run ruff check . && uv run ruff format --check .
uv run pytest -q                # exit code 5 = no tests yet (fine); tests marked `live` are skipped
uv run pytest -m live           # only the `live` tests (need OpenAI or real data; never in CI)
```

Added as they land. Each track documents its own commands in its module README; the orchestrator copies the key ones here at block merges:
- `uv run scrubgpt-validate case|reference|response|live …` (Dev1, Phase 0)
- `uv run scrubgpt-mock-brain --port 8101` and `uv run scrubgpt-codegen` (Dev2, Phase 0)
- Brain, app server and web run commands (Block 1)
