# Onboarding: start here (Dev2, or any new machine)

This guide gets a Windows machine (x64 or **ARM64 / Snapdragon**) ready to work on ScrubGPT with Claude Code. Allow about 30–45 minutes.

**Do it on every machine you use.** Dev2: the Zenbook at home **and** the office laptop. Dev1: the office PC and the Surface. Your Claude chat history stays on each machine, but **everything important is in the repo**, so you can switch machines freely: just `git pull` and say "I'm DevN. Start session."

## 0. Accounts (do these first)

| What | Action |
|---|---|
| **GitHub** | **Only two accounts take part (D-046):** `karthi-ai-engineer` (owner, Dev1) and `TharunAppireddy` (Dev2, write access already granted). Sign in with **that** account on every machine, never a company or other account |
| **Google Drive** | Accept the share of the folder **`ScrubGPT-data`** (videos + case packages; never in git) |
| **Claude** | A Claude account that can use Claude Code |
| **OpenAI** | **Dev2 does not need a key.** The app never calls OpenAI; only the Brain (Dev1) does |

## 1. Install the tools (PowerShell)

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS -e --version 26.3.1   # same Node as the office PC (.nvmrc = 26)
winget install --id Gyan.FFmpeg -e          # an x64 build is fine on ARM64 (it runs under emulation)
winget install --id Google.GoogleDrive -e
```

Close PowerShell, open a new one, then:

```powershell
uv python install 3.13
git --version; gh --version; uv --version; node --version; ffmpeg -version
gh auth login                               # sign in as YOUR project account (Dev1: karthi-ai-engineer, Dev2: TharunAppireddy)
gh auth status                              # must show that account, on every machine you use
```

Don't change your **global** git identity (an office machine may need it for company work). The project's identity is set **inside the repo** in step 2.

`node --version` must print `v26.x`. If winget can't find that exact version, install `v26` with **fnm** (`winget install Schniz.fnm`, then `fnm install 26 && fnm use 26`).

**ARM64 note:** the stack deliberately avoids PyTorch, CUDA and OpenCV, so everything should install natively. If a Python package ever fails on ARM64, ask Claude to switch that environment to **x64 Python through uv**. It runs under Windows' built-in emulation.

## 2. Get the code

```powershell
cd $HOME
git clone https://github.com/karthi-ai-engineer/ScrubGPT.git
cd ScrubGPT
git config user.name  "Your Name"
git config user.email "179685213+TharunAppireddy@users.noreply.github.com"   # Dev2
# Dev1: git config user.email "296384397+karthi-ai-engineer@users.noreply.github.com"
git config --local credential.https://github.com.username TharunAppireddy   # Dev2 (Dev1: karthi-ai-engineer): push only as this account
git config --local --get user.email         # check: your noreply address above
git push --dry-run                          # check: works without asking for another account
copy .env.example .env
uv sync --all-packages     # installs the workspace + ruff/pytest
```

**Why the noreply address:** GitHub credits a commit to whichever account owns its email. A company email would make a company account a contributor to this repo. CI rejects any commit that isn't linked to `karthi-ai-engineer` or `TharunAppireddy` (D-046).

## 3. Google Drive data folder

1. Open Google Drive for desktop and sign in.
2. In Drive (web), add a **shortcut to `ScrubGPT-data` in "My Drive"**.
3. In File Explorer, right-click the folder and choose **"Available offline"**. This makes videos play smoothly.
4. Note the folder's path, for example `G:/My Drive/ScrubGPT-data`.
   - **Dev1:** set `DATA_DIR` to this path in `.env`.
   - **Dev2:** keep `DATA_DIR=./contracts/fixtures` until integration (Week 6). Use the Drive folder for the **Friday drops** (`drop/YYYY-MM-DD/`).

**Dev2's `.env` until integration:** `BRAIN_MODE=mock` (the fake Brain on `:8101`) and `DATA_DIR=./contracts/fixtures`. Leave the OpenAI values empty. Keep `APP_DB_PATH` local and **outside** Google Drive.

**Status worktree:** nothing to do now. Claude creates `..\ScrubGPT-main` automatically the first time it updates your status file while you're on a work branch (`CLAUDE.md`, Git workflow).

## 4. Claude Code

Install it (PowerShell). The docs are at https://code.claude.com/docs:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Then, inside the repo folder:

```powershell
claude
```

Your **first message** in every session:

> **I'm Dev2. Start session.**

(Use **Dev1** if you are Dev1.)

Claude then:
1. reads `CLAUDE.md`, `docs/status/project.md`, your `docs/status/devN.md` and the other developer's requests to you;
2. tells you where the project stands and proposes your next task;
3. works only in your track's folders, on your current branch: the shared `p0/contracts` in Phase 0 (your own files only), then `devN/b1`…`b5`.

**The team (`docs/TEAM.md`).** Nothing extra to install: the agents come with the repo.
- **Team Lead:** a Claude agent on GitHub. To ask it something, write a comment that **starts with** `/team-lead` in any issue or PR, or open an **Ask the Team Lead** issue.
- **Requests from the other developer:** Claude shows them in your briefing. Your session analyses them first.
- **Your tester:** Dev1 → `tester-brain`, Dev2 → `tester-app`. Claude starts it after each task. Its tests live in their own folders; never edit them.

At the end, say **"End session."** Claude commits your work to your branch (e.g. `dev2/b1`), pushes it, and updates your status file on `main`. Block merges into `main` happen at the end of each block (see `docs/Work_Split.md`).

**Before Mon 19 Oct:** only onboarding. Phase 0 work starts on Mon 19 Oct.

## 5. Checklist

- [ ] `gh auth status`: the **active** account is yours (`gh auth switch -u <login>` if not)
- [ ] Repo-local identity set: noreply `user.email` + `credential.https://github.com.username` (step 2); `git push --dry-run` works
- [ ] All tools print a version
- [ ] Repo cloned, `uv sync --all-packages` OK, `.env` created (`DATA_DIR`: Dev1 → the Drive folder, Dev2 → `./contracts/fixtures`)
- [ ] `claude` starts in the repo, and "I'm Dev2. Start session." gives a status summary
- [ ] Tick "Dev2 onboarded" in `docs/status/project.md` (Claude can do this for you)

## 6. Where to read more

| Doc | What |
|---|---|
| `docs/TEAM.md` | **The agent team:** Team Lead, testers, how requests move, labels |
| `docs/Work_Split.md` | How the two tracks work in parallel, timeline, daily routine |
| `docs/status/` | Live status: `project.md` (shared), `dev1.md`, `dev2.md` |
| `docs/DECISIONS.md` | Every decision and why it was made |
| `docs/MVP_Master_Plan.md` | Full plan: features, architecture, contracts |
