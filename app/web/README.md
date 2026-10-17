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

- **Routes:** `/` is Home (J1, the case cards); `/cases/:caseId` is the case page (video player with 1×–16× speeds, flagged moments that seek the video).
- **Contract types** are never written by hand: import them from the generated `contracts/ts/contracts.ts` through the `@contracts` alias, e.g. `import type { Case } from "@contracts/contracts"`. App-server response shapes built from them live in `src/api/types.ts`. `@/` points to `src/`.
- **i18n (J15):** every UI string is a key in both `src/i18n/ja.json` and `src/i18n/en.json` (a unit test checks that the key sets match); keys are typed, so a missing key fails `tsc`. Content fields from the API are `Bilingual`; show them with `useBilingual()`. The JA | EN toggle switches instantly, sets `<html lang>` and remembers the choice in `localStorage` (first visit: Japanese for a Japanese browser, else English).
- **Trust labels:** show every piece of knowledge with `<TrustBadge label=… />` (emoji + localised name).
- **Unit tests** live next to the code (`*.test.ts(x)`); `tests/acceptance/` belongs to Tester 2. UI components follow shadcn/ui (`components.json`), so `npx shadcn add <name>` adds more into `src/components/ui/`.
