## Summary

- **Phase / block:** <!-- e.g. Phase 0 / Day 2, Phase 1 / Block 2, Integration, Polish, Contract change (write "Block N", D-041) -->
- **Developer:** <!-- Dev1 (Brain) or Dev2 (App) -->
- **Feature IDs:** <!-- e.g. C2, C3 (MVP_Master_Plan.md §2) -->

## What changed

<!-- A few bullets. Link the plan section or decision (D-0xx) where it helps. -->

-

## How it was tested

- [ ] `scrubgpt-validate` (case package, Procedure Reference or live Brain API responses)
- [ ] `pytest` + `ruff`
- [ ] `vitest` + `eslint`
- [ ] Manual: <!-- what you ran or clicked, on which machine, with which case -->

## Contract impact

- [ ] None
- [ ] Additive — MINOR bump (new fields are `T | None = None`); needs the other developer's approval (D-033)
- [ ] Breaking — MAJOR bump; agree with the other developer before starting, then their approval

## Checklist

- [ ] Stays inside my own track's folders (Phase 0 / contract PRs: only my assigned files in `contracts/`, D-031)
- [ ] JA and EN present for every human-readable string
- [ ] Provenance (trust label) visible for every piece of knowledge shown
- [ ] `/code-review` run
- [ ] README usage note updated
- [ ] My status file is updated on `main`, not on this branch
- [ ] Milestone and `dev1`/`dev2` label set
- [ ] No AI attribution lines in commits or in this description (D-018)
- [ ] No media, `data/`, `.env`, secrets or local databases committed
