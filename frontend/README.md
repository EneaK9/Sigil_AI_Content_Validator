# Sondë — frontend

Topic-intelligence dashboard. Enter a topic and Sondë pulls posts from five
social platforms, flags posts that may break each platform's **published**
policy, and surfaces sentiment, influential voices, and the most viral posts.

Built with Next.js 14 (App Router), TypeScript (strict), and Tailwind CSS.
Runs fully standalone against local mock data — no backend required.

## Getting started

```bash
# from frontend/
pnpm install        # or: npm install
cp .env.local.example .env.local
pnpm dev            # or: npm run dev
```

Open http://localhost:3000.

## Scripts

| Script              | What it does                          |
| ------------------- | ------------------------------------- |
| `pnpm dev`          | Dev server                            |
| `pnpm build`        | Production build                      |
| `pnpm start`        | Serve the production build            |
| `pnpm lint`         | ESLint                                |
| `pnpm typecheck`    | `tsc --noEmit`                        |
| `pnpm format`       | Prettier                             |

## Mock vs. live backend

The UI ships with a complete `TopicReport` in `lib/mock.ts` so it works with
zero backend.

- **No `NEXT_PUBLIC_API_BASE_URL`** → renders mock data.
- **Set `NEXT_PUBLIC_API_BASE_URL`** (e.g. `http://localhost:8000`) → fetches
  the live report via `lib/api.ts` (`GET /api/topics?q=…&days=…`).

Swapping to the live backend requires no component changes — only the env var
and, if the FastAPI route differs, the path/params in `lib/api.ts`. Keep
`TopicReport` (`types/index.ts`) as the assembled client shape.

## Design system

Tokens are defined once as CSS variables in `app/globals.css` and mirrored into
`tailwind.config.ts`, so components only use semantic utilities (`bg-surface`,
`text-ink`, `border-line`, `font-mono`, `text-amber`, …). No hardcoded hex lives
in components — only in the token source and in mock data (`avatarColor`).

Fonts (via `next/font/google`): **Space Grotesk** (display/UI), **Inter**
(body), **IBM Plex Mono** (all data: numbers, handles, timestamps,
confidence %). Light theme only.

## Architecture

- Data is fetched once at the page level (`app/page.tsx`) and flows down.
- `components/Dashboard.tsx` owns interaction state (`activeTab`,
  `activeSource`); source filtering is pure client-side over the fetched arrays
  (`lib/filter.ts`).
- Leaf components are presentational: typed props in, JSX out — no fetching,
  no global state.

## Product guardrails (intentional)

- Flags are AI-suggested candidates mapped to a published policy, with a
  confidence score and the exact cited rule — not verdicts, not automated
  reports. The only action is **Review**. There is no bulk-report affordance.
- Sensitive posts show a neutral AI summary (`redacted`), never raw content.
- Conversation/search interest is a relative index, not absolute counts.
- Sentiment percentages are a model estimate, surfaced as such.
