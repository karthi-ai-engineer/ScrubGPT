# app/web/ (Dev2)

Web UI: Control Room, Answer app, Case Explorer, Library, Ask, Graph and more. See `app/web/CLAUDE.md` for the rules and `docs/MVP_Master_Plan.md` §2.10 for the features (J1–J16).

## Usage

Vite + React + TypeScript (strict), Tailwind CSS v4, shadcn/ui-style components, react-i18next, TanStack Query and React Router. Node 26 (`.nvmrc`); run every command in `app/web/`.

```
npm ci              # install exactly what package-lock.json pins
npm run dev         # http://localhost:5173; /api and /media are proxied to the app server on :8000
npm run build       # type-check (tsc -b) + production build into dist/
npm run preview     # serve dist/ (same proxy)
npm run lint        # eslint
npm run test        # vitest (jsdom), once; also runs Tester 2's tests/acceptance/
npm run typecheck   # tsc -b only
```

Start the app server first (it serves `/api/*` and `/media/*` on port 8000); without it the pages show a "can't reach the app server" message with a retry button.

- **Routes:** `/` is Home (J1, the case cards); `/cases/:caseId` is the case page (video player with 1×–16× speeds, flagged moments that seek the video); `/cases/:caseId/control-room` is the **Control Room** (J2, linked from the case page and every home card): the case replays "live" with a step bar, event markers, a JA/EN transcript ticker, alerts and the J8 graph panel (Cytoscape.js, loaded as its own chunk).
- **Control Room sync (plan §8.2):** the `<video>` is the master clock. `src/replay/` holds the pure sync engine (`sync.ts`: an item shows when `currentTime >= t_start`, binary search; the current step is `t_start <= t < t_end`) and a clock (`clock.ts`) that ticks every animation frame while playing and on `seeked`/`ratechange`/`timeupdate`; React state changes only when what is revealed changes, so seeking back hides items again and 16× never desyncs. The graph elements come from the pure `src/graph/buildGraphElements.ts` (one node per Decision Record, never merged) and are laid out as a left-to-right tree (`treeLayout.ts`: case → steps → moments → obstacle leaves and records) with one-line labels; hovering or tapping a node shows its full text and trust label.
- **"Surgery ends" needs the app server's SSE stream:** when the video ends (or comes within 0.25 s of the end), the page POSTs `/api/cases/{id}/replay-ended` once per play-through and listens on `GET /api/events` (`EventSource`) for `case.ended`; the banner and the phone-frame notification show the counts from that event (never a fixed number). If the stream is down, the POST's reply (same payload) is shown instead. `npm run dev` proxies `/api/events` like any other `/api` path; the flow was checked with the built app served by the app server itself.
- **Contract types** are never written by hand: import them from the generated `contracts/ts/contracts.ts` through the `@contracts` alias, e.g. `import type { Case } from "@contracts/contracts"`. App-server response shapes built from them live in `src/api/types.ts`. `@/` points to `src/`.
- **i18n (J15):** every UI string is a key in both `src/i18n/ja.json` and `src/i18n/en.json` (a unit test checks that the key sets match); keys are typed, so a missing key fails `tsc`. Content fields from the API are `Bilingual`; show them with `useBilingual()`. The JA | EN toggle switches instantly, sets `<html lang>` and remembers the choice in `localStorage` (first visit: Japanese for a Japanese browser, else English).
- **Trust labels:** show every piece of knowledge with `<TrustBadge label=… />` (emoji + localised name).
- **Unit tests** live next to the code (`*.test.ts(x)`); `tests/acceptance/` belongs to Tester 2. UI components follow shadcn/ui (`components.json`), so `npx shadcn add <name>` adds more into `src/components/ui/`.
