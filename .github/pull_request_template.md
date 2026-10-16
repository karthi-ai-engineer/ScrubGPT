## Summary

- **Phase / block:** <!-- e.g. Phase 0 / Day 2, Phase 1 / B2, Integration, Polish, Contract change -->
- **Developer:** <!-- Dev1 (Brain) or Dev2 (App) -->
- **Feature IDs:** <!-- e.g. C2, C3 (MVP_Master_Plan.md §2) -->

## What changed

<!-- A few bullets. Link the plan section or decision (D-0xx) where it helps. -->

-

## How it was tested

- [ ] `validate.py` (case package or Brain API responses)
- [ ] `pytest` + `ruff`
- [ ] `vitest` + `eslint`
- [ ] Manual: <!-- what you ran or clicked, on which machine, with which case -->

## Contract impact

- [ ] None
- [ ] Additive (new optional field): MINOR bump of `contract_version`
- [ ] Breaking: MAJOR bump, **needs the other developer's approval** (D-021, D-023)

## Checklist

- [ ] Stays inside my own track's folders (Brain: `knowledge/`, `brain/`; App: `app/server/`, `app/web/`); cross-track needs are written as requests
- [ ] JA and EN present for every human-readable string
- [ ] Provenance (trust label) visible for every piece of knowledge shown
- [ ] My status file is updated on `main`, not on this branch
- [ ] No AI attribution lines in commits or in this description (D-018)
- [ ] No media, `data/`, `.env`, secrets or local databases committed
