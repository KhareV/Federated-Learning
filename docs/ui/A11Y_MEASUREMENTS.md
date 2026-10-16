# Accessibility audit measurements (generated)

- before: `reports/ui/a11y/baseline/a11y.json` (settled-scroll measurement of the tree at `21a5fad` plus only the direct-route fix)
- after: `reports/ui/a11y/final/a11y.json`
- note: the Tab-press limit was 90 for the baseline and 160 for the after run, so the last column compares caps, not behaviour; the baseline hit its cap on the dense pages
- method: real Chrome + Clerk test user, hardware source disabled, no data seeded; Tab pressed up to the stated limit per route, scroll allowed to settle before each measurement

## Keyboard journey (all routes)

| viewport | routes before → after | stops outside the viewport | obscured by sticky header | in a closed/hidden container | without a focus indicator | largest tab-stop count |
|---|---|---|---|---|---|---|
| desktop | 28 → 28 | 0 → 0 | 54 → 0 | 0 → 0 | 0 → 0 | 90 → 129 |
| laptop | 0 → 28 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 129 |
| phone | 28 → 28 | 230 → 0 | 36 → 0 | 0 → 0 | 0 → 0 | 90 → 114 |
| tablet | 0 → 28 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 114 |

## Semantics (desktop, all routes)

| check | before | after |
|---|---|---|
| heading level skips | 6 | 0 |
| tables without a name | 20 | 0 |
| table headers without scope | 49 | 0 |
| unlabelled form controls | 0 | 0 |
| interactive elements without a name | 0 | 0 |
| charts without an accessible name | 0 | 0 |
| duplicate ids | 0 | 0 |
| routes without exactly one h1 | 0 | 0 |
| routes whose direct HTTP load is not 200 | 0 | 0 |

## Console and network (desktop, excluding the Clerk development-keys notice)

| | before | after |
|---|---|---|
| console errors/warnings | 2 | 1 |
| failed requests (HTTP ≥ 400) | 2 | 1 |
| transport failures | 0 | 0 |

Remaining (explained in the audit): `/app/history/NO-SUCH-SESSION` — error: Failed to load resource: the server responded with a status of 404 (Not Found)

External hosts contacted: `delicate-civet-2247.clerk.accounts.dev`

## Charts: tab stops (after)

| route | charts with points | chart tab stops | focusable points (arrow keys) |
|---|---|---|---|
| `/app/observatory/fl10` | 4 | 4 | 129 |
| `/app/federation/live?run=recorded-A` | 4 | 4 | 129 |
