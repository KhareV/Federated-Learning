# UI tour measurements (generated)

- before: mid-pass audit tour (`reports/hardware/ui_tour/audit_interim`, an earlier build of this same pass)
- after: `reports/hardware/ui_tour/unified_final/tour.json.tour.json`
- routes are measured at desktop (1440 px); `–` = not measured in that run.

| route | words before → after | small-text elements (<10.5 px) | long paragraphs (≥45 words) | heading skips | HTTP | keyboard stops without focus ring |
|---|---|---|---|---|---|---|
| `/app` | 294 → 305 | 10 → 9 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/about` | 292 → 292 | 4 → 4 | 1 → 1 | 0 → 0 | 200 | 0/24 |
| `/app/device` | 122 → 122 | 4 → 4 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/federation` | 419 → 437 | 35 → 16 | 0 → 0 | 0 → 0 | 200 | 0/25 |
| `/app/federation/clients` | 352 → 352 | 33 → 25 | 0 → 0 | 0 → 0 | 200 | 0/25 |
| `/app/federation/live` | 148 → 163 | 11 → 11 | 0 → 0 | 1 → 1 | 200 | 0/24 |
| `/app/federation/live ?run=hardware (HDFLRUN)` | 1872 → 1882 | 107 → 75 | 1 → 1 | 1 → 1 | 200 | 0/25 |
| `/app/federation/live ?run=recorded evidence` | 2136 → 2151 | 135 → 87 | 1 → 1 | 2 → 2 | 200 | 0/25 |
| `/app/federation/live ?run=synthetic live (FL10RUN)` | – → 1895 | – → 81 | – → 0 | – → 2 | 200 | 0/25 |
| `/app/federation/privacy` | 218 → 233 | 9 → 9 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/federation/rounds` | 77 → 92 | 9 → 9 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/history` | 154 → 154 | 13 → 4 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/history/<session>` | 91 → 91 | 3 → 3 | 0 → 0 | 0 → 0 | 404 | 0/24 |
| `/app/models` | 226 → 262 | 13 → 13 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/monitoring` | 350 → 350 | 4 → 4 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory` | 613 → 613 | 28 → 28 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/evidence` | 816 → 816 | 32 → 15 | 0 → 0 | 0 → 0 | 200 | 0/25 |
| `/app/observatory/federation` | 291 → 291 | 17 → 17 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/fl10` | 2136 → 2151 | 135 → 87 | 1 → 1 | 2 → 2 | 200 | 0/25 |
| `/app/observatory/model` | 519 → 519 | 17 → 10 | 1 → 1 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/outcomes` | 732 → 732 | 42 → 15 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/provenance` | 544 → 544 | 4 → 4 | 0 → 0 | 0 → 0 | 200 | 0/23 |
| `/app/observatory/replay` | 88 → 88 | 5 → 5 | 1 → 1 | 0 → 0 | 200 | 0/23 |
| `/app/observatory/scenarios` | 383 → 383 | 14 → 14 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/storyboard` | 194 → 194 | 6 → 6 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/observatory/tour` | 199 → 199 | 23 → 23 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/research/fl` | 537 → 537 | 11 → 11 | 0 → 0 | 0 → 0 | 200 | 0/24 |
| `/app/research/ml` | 350 → 350 | 17 → 17 | 0 → 0 | 1 → 1 | 200 | 0/24 |
| `/app/system` | 65 → 97 | 4 → 4 | 0 → 0 | 0 → 0 | 200 | 0/24 |

## Layout health by viewport (after)

| viewport | routes | horizontal overflow | console errors | failed requests |
|---|---|---|---|---|
| desktop | 29 | 0 | 1 | 2 |
| laptop | 29 | 0 | 1 | 2 |
| phone | 29 | 0 | 1 | 2 |
| tablet | 29 | 0 | 1 | 2 |

External hosts contacted: `delicate-civet-2247.clerk.accounts.dev`
