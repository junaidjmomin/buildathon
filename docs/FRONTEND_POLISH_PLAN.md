# Frontend Polish & Redesign Plan

Status date: 2026-08-29
Scope: `frontend/` only. Specification authority for product behavior remains
`features.md` → `backend.md` → `frontend.md` → `techstack.md`.

## Part 1 — Why tab switching jitters today (diagnosis)

The jitters are **not** inherent to Next.js. Four concrete architectural causes,
verified in the code:

1. **The app shell remounts on every navigation.** All 13 pages are
   `"use client"` components that each render their own `<AppShell>`
   (`frontend/src/components/app-shell.tsx`). Every tab switch unmounts one
   page's entire shell subtree (sidebar, header, run selector) and mounts a new
   one. The sidebar repaints, the header reflows, the run-selector query
   re-subscribes — that is the visible flash/jitter. The shell must live in
   `app/layout.tsx` and persist across `{children}` swaps.

2. **Full-page spinners instead of skeletons.** List pages (e.g.
   `root-causes/page.tsx:23`) gate the whole page behind
   `isPending ? <LoaderCircle spin> : content`, causing a giant
   layout jump from spinner → full content. `app/loading.tsx` has good
   skeletons but only applies to the initial route segment load.

3. **Data waterfalls on every mount.** Each page re-runs the
   `runs → activeRun → per-run data` query chain. With `staleTime: 30_000`
   (`providers.tsx:12`), data older than 30s refetches on each remount,
   swapping rendered content mid-view.

4. **No prefetch on intent.** Navigation links don't warm the query cache on
   hover/focus, so first visit to a tab always shows a pending state.

## Part 2 — Performance & UX plan (fix the jitters)

### 2.1 Persistent shell (highest impact)
- Move `AppShell` into `app/layout.tsx`; remove the per-page `<AppShell>`
  wrappers from all 13 pages.
- Sidebar, header, run selector, and their `["runs"]` query mount exactly once.
- Route transitions swap only the page content area.

### 2.2 Skeletons everywhere, spinners nowhere
- Shared `Skeleton` primitives (block, text, card, table-row) in
  `components/ui/skeleton.tsx` styled to the new theme.
- Each data-bound page renders a layout-matching skeleton while pending —
  same grid, same card sizes — so the transition from skeleton → data is a
  content fill, not a layout jump.
- Keep the thin top progress bar for slow navigations; delete the
  full-viewport spinner pattern.

### 2.3 Query cache tuning
- `staleTime: 60_000`, `gcTime: 10 * 60_000`, `refetchOnWindowFocus: false`
  in `providers.tsx`.
- `placeholderData: keepPreviousData` for run-scoped list queries so switching
  runs shows the previous list instantly while the new one loads.
- Deduplicate the `runs` fetch: a single `useRuns()` hook
  (`lib/hooks.ts`) used by shell and pages.

### 2.4 Prefetch on intent
- Nav links prefetch their page's primary queries on hover/focus via
  `queryClient.prefetchQuery`.
- Next.js `<Link>` prefetch stays on (default).

### 2.5 Route-level loading segments
- `loading.tsx` per route group where the first paint waits on data
  (runs/[runId]/*, agreements/[id], controls/[key]) with page-shaped skeletons.

### 2.6 Motion polish
- One shared transition scale: 150ms ease-out for hovers, 200ms for
  content fades; `prefers-reduced-motion` respected globally.
- No layout-triggering animations (transform/opacity only).

## Part 3 — Theme selection & redesign

### 3.1 Selected theme: "Control Room" (dark, terminal-grade)

Rationale: sl3dge is an *engine that verifies money movement* — an analyst
instrument, not a marketing site. A dark, terminal-grade palette:

- reads as serious/trustworthy for financial evidence review
- makes tabular numerals and status colors the visual heroes
- differentiates sharply from generic light fintech dashboards
- demos exceptionally well (buildathon context)

Palette (CSS custom properties, tokenized in `globals.css`):

| Token | Value | Use |
|---|---|---|
| `--ink-900` | `#0a1210` | app background |
| `--ink-800` | `#101b18` | panel surfaces |
| `--ink-700` | `#182724` | raised cards / sidebar |
| `--line` | `#24352f` | borders, dividers |
| `--paper` | `#e8ede9` | primary text |
| `--paper-dim` | `#93a39b` | secondary text |
| `--evergreen` | `#2fbd7f` | primary accent (verify/pass) |
| `--amber` | `#e3b341` | warnings, pending |
| `--crimson` | `#e2604f` | violations, errors |
| `--sky` | `#5fb6d9` | informational, links |

Typography: keep Geist Sans + Geist Mono (already self-hosted via
`next/font`); mono carries all money amounts, IDs, and metrics
(`tabular-nums` already in place). Type scale tokenized: 11/12/13/15/18/24/32.

Status semantics get first-class badges: `PASS` evergreen, `VIOLATION`
crimson, `UNRESOLVED`/pending amber, `INFO` sky — used identically on every
screen.

### 3.2 Redesign mechanics (how 13 pages restyle without a rewrite)

1. **Token layer** — all colors/spacing/radius/motion as CSS variables +
   Tailwind v4 `@theme` mapping. No hard-coded hex in components after this.
2. **Shared primitives** (`components/ui/`):
   `Panel`, `StatCard`, `Badge` (status), `PageHeader` (eyebrow + title +
   subtitle), `EmptyState`, `ErrorState` (with retry), `DataTable`,
   `Skeleton`, `MoneyText` (mono, tabular, currency-aware).
3. **Page pass** — every page rebuilt on the primitives: same data, same
   routes, same API calls; new shell, new visual hierarchy. Detail pages get a
   consistent back-link + header + section rhythm.
4. **Charts** (recharts) restyled to the token palette with mono axis labels.
5. **Sidebar/header redesign**: dark shell with the run selector promoted to a
   prominent, labeled control; active route gets an evergreen edge indicator.

### 3.3 Accessibility & quality gates
- WCAG AA contrast on all token pairs (verified programmatically).
- Global `:focus-visible` ring in evergreen; keyboard paths unchanged.
- Existing Vitest suite (17 tests) stays green; add tests for new primitives'
   rendering states.
- Gates before merge: `tsc --noEmit`, `eslint`, `vitest run`,
  `next build`, plus a manual tab-switch smoke check (Overview → Controls →
  Exceptions → Root causes → Data sources) with zero shell flicker.

## Part 4 — Execution order

| Phase | Work | Risk |
|---|---|---|
| 1 | Persistent shell in layout (2.1) + query tuning (2.3) | Low — mechanical |
| 2 | Theme tokens + UI primitives (3.1–3.2.2) | Low — additive |
| 3 | Page-by-page redesign on primitives (list → detail pages) | Medium |
| 4 | Skeletons + prefetch + route loading segments (2.2, 2.4, 2.5) | Low |
| 5 | Motion polish, contrast audit, final verification (2.6, 3.3) | Low |

Each phase ends with the full verification gate. No backend changes required.
