# Onboarding: start here (Dev2, or any new machine)

This guide gets a Windows machine (x64 or **ARM64 / Snapdragon**) ready to work on ScrubGPT with Claude Code. Allow about 30–45 minutes.

**Do it on every machine you use.** Dev2: the Zenbook at home **and** the office laptop. Dev1: the office PC and the Surface. Your Claude chat history stays on each machine, but **everything important is in the repo**, so you can switch machines freely: just `git pull` and say "I'm DevN. Start session."

## 0. Accounts (do these first)

| What | Action |
|---|---|
| **GitHub** | Send your GitHub username to Dev1, then accept the invite to `karthi-ai-engineer/ScrubGPT` |
| **Google Drive** | Accept the share of the folder **`ScrubGPT-data`** (videos + case packages; never in git) |
| **Claude** | A Claude account that can use Claude Code |
| **OpenAI** | **Dev2 does not need a key.** The app never calls OpenAI; only the Brain (Dev1) does |

## 1. Install the tools (PowerShell)

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS -e        # Node 26 (pinned in .nvmrc); check with: node --version
winget install --id Gyan.FFmpeg -e          # an x64 build is fine on ARM64 (it runs under emulation)
winget install --id Google.GoogleDrive -e
```

Close PowerShell, open a new one, then:

```powershell
uv python install 3.13
git --version; gh --version; uv --version; node --version; ffmpeg -version
gh auth login                               # sign in to GitHub
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

**ARM64 note:** the stack deliberately avoids PyTorch, CUDA and OpenCV, so everything should install natively. If a Python package ever fails on ARM64, ask Claude to switch that environment to **x64 Python through uv**. It runs under Windows' built-in emulation.

## 2. Get the code

```powershell
cd $HOME
git clone https://github.com/karthi-ai-engineer/ScrubGPT.git
cd ScrubGPT
copy .env.example .env
```

## 3. Google Drive data folder

1. Open Google Drive for desktop and sign in.
2. In Drive (web), add a **shortcut to `ScrubGPT-data` in "My Drive"**.
3. In File Explorer, right-click the folder and choose **"Available offline"**. This makes videos play smoothly.
4. Note the folder's path, for example `G:/My Drive/ScrubGPT-data`.
   - **Dev1:** set `DATA_DIR` to this path in `.env`.
   - **Dev2:** keep `DATA_DIR=./contracts/fixtures` until integration (Week 6). Use the Drive folder for the **Friday drops** (`drop/YYYY-MM-DD/`).

**Dev2's `.env` until integration:** `BRAIN_MODE=mock` (the fake Brain on `:8101`) and `DATA_DIR=./contracts/fixtures`. Leave the OpenAI values empty. Keep `APP_DB_PATH` local and **outside** Google Drive.

**Status worktree (once per machine):** status files are edited only on `main`, through a second checkout next to the repo:
```powershell
git worktree add ..\ScrubGPT-main main
```
Claude uses it automatically. You don't need to do anything else.

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
3. works only in your track's folders, on your current branch (`p0/devN-…` in Phase 0, then `devN/b1`…`b5`).

At the end, say **"End session."** Claude commits your work to your branch (e.g. `dev2/b1`), pushes it, and updates your status file on `main`. Block merges into `main` happen at the end of each block (see `docs/Work_Split.md`).

**Before Mon 19 Oct:** only onboarding. Phase 0 work starts on Mon 19 Oct.

## 5. Checklist

- [ ] GitHub invite accepted; `gh auth status` OK
- [ ] All tools print a version
- [ ] Repo cloned, `.env` created (`DATA_DIR`: Dev1 → the Drive folder, Dev2 → `./contracts/fixtures`), status worktree created
- [ ] `claude` starts in the repo, and "I'm Dev2. Start session." gives a status summary
- [ ] Tick "Dev2 onboarded" in `docs/status/project.md` (Claude can do this for you)

## 6. Where to read more

| Doc | What |
|---|---|
| `docs/Work_Split.md` | How the two tracks work in parallel, timeline, daily routine |
| `docs/status/` | Live status: `project.md` (shared), `dev1.md`, `dev2.md` |
| `docs/DECISIONS.md` | Every decision and why it was made |
| `docs/MVP_Master_Plan.md` | Full plan: features, architecture, contracts |
