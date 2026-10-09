# NHM-UNIFIED-LIVE-FEDERATION-STUDIO-001 — dependency audit (AFTER migration, before and after cleanup)

Performed only after the unified Studio was working and verified in a real browser (`reports/unified_live_fl/browser/studio_browser_verification.json`) and by backend/frontend tests. Decisions use the classes required by the master prompt. **No route was deleted; one route became a redirect; nothing unique was lost.**

## Feature parity of the one retired page (`/app/observatory/fl10`)

`OLD FEATURE → NEW LOCATION → VERIFIED BY`

| Old FL10 page feature | New location in the Studio | Verified by |
|---|---|---|
| Experiment overview cards (source, status, accepted updates, example exposures, final candidate, selected state, holdout, timing) | Analysis ▸ OVERVIEW (`RunOverview`) + RUN STATUS strip + candidate panel | browser: `overview facts show the run's own source, accepted updates and limits` (3- and 10-round) |
| R3 vs R10 headline table with difference and the ranking-vs-probability warning | Analysis ▸ COMPARISON (`RoundComparison`, defaults to the predeclared pair; R0→R3 for the default run) | browser: `comparison defaults…`, `difference equals the stored point difference` |
| Round selector, "compare any two rounds", "metric across rounds" | Round explorer (R0…R10, follow live / return to live) + COMPARISON | browser: round selection / rapid switching / comparison update |
| Overview tab figures FIG20, FIG04, FIG09; Training tab FIG02/03/12/13/19; Classification FIG04–10; Clients FIG11/12/14/15; R3-vs-R10 FIG16/15/20; Internals FIG01/17/18/19 | all 20 figures across OVERVIEW / PERFORMANCE / TRAINING / CLIENTS / MATRICES / COMPARISON (+ index in FIGURES & EXPORTS) | browser: `all 20 figures are reachable from the tabs` |
| All 12 tables with CSV/JSON/Markdown | same tabs + FIGURES & EXPORTS | browser: `all 12 tables are reachable from the tabs`; API tests |
| Per-client round table and the two matching holdout participants | Analysis ▸ CLIENTS (`ClientHistory`, `RoundClientPanel`) | browser: `client history lists every committed round`, `two holdout participants…` |
| Research bridge (frozen real-ECG lane, TAB10 boundaries, TAB11 exposed-holdout reference, links to outcomes/evidence) | Analysis ▸ COMPARISON (`ResearchBridge`) + OVERVIEW (TAB10) + TAB11 | browser: `scientific research bridge is shown as a separate frozen lane` |
| Exports (SVG, PNG 300 dpi, CSV, provenance, tables) + verification manifest with SHA256 | FIGURES & EXPORTS (`ExportPanel`, re-hashes each download against the manifest, manifest download) | browser: downloads verify; API tests (hash-verified routes incl. `provenance`) |
| Live start of Mode A and Mode B + job progress and failure message | Federation Studio entry (3/10 selector, source mode) + RUN STATUS strip (fail-closed, "restart from R0") | browser: genuine 10-round start; `tests/test_studio_api.py` |
| Recorded verified runs A/B | run selector (recorded runs open as labelled REPLAY evidence; typed journal reconstructed from the recorded run report) | browser: recorded-A journey; API tests |
| 3-round baseline panel (R1–R3 equal frozen digests) | FIG18 lineage / TAB08 (frozen-equality column) for every run; link to the original federation page unchanged | specs parity test |
| Interpretation limits | OVERVIEW limits list | browser |

## Final route decisions

| Route | Decision | Reason / evidence |
|---|---|---|
| `/app/federation` | **KEEP — extended** | entry + 3/10 selector; original run form untouched for 3 rounds |
| `/app/federation/live` | **KEEP — primary, shared by both lengths** | original components retained; new sections appended |
| `/app/federation/rounds`, `/clients`, `/privacy` | **KEEP** | distinct per-run state/privacy/client-identity views, still work for 3-round runs |
| `/app/observatory/fl10` | **REDIRECT** (→ `/app/federation/live?run=recorded-A`, `?run=` preserved) and **REMOVE FROM NAVIGATION** | all unique functionality migrated (table above); file retained so bookmarks/docs/locks do not dangle; frozen-lock re-pin handled by the additive successor |
| `/app/observatory/storyboard` | **KEEP (retain as deep link) + cross-link to the Studio** | unique 8-step guided narrative and a distinct SITE_00 live-link control (monitoring + parity, no federation) not reproduced in the Studio; deleting it would lose content |
| `/app/observatory/outcomes` | **PROTECTED — CANNOT DELETE** | frozen scientific comparisons (V1/V2, FedAvg/FedProx, IID/non-IID, INTERNAL_TEST, INCART, uncertainty, centralized-vs-federated); byte-unchanged (guard test) |
| `/app/observatory/federation`, `/[client_id]` | **KEEP** | cohort/window/fault inspection, FedAvg arithmetic, per-batch; `[client_id]` deep inspection is **PROTECTED** |
| `/app/observatory/federation-replay` | **KEEP** | event-journal scrubber (distinct); its `buildSnapshots` pattern was reused, page untouched |
| `/app/observatory/evidence`, `/research`, `/model`, `/provenance`, `/replay`, `/scenarios`, `/tour`, `/app/observatory` | **KEEP** | default for unique research/educational features; only the home page's FL10 link text was repointed to the Studio |

## Links, tests and dependencies migrated
- Observatory home: link → Federation Studio (guard test: no `href="/app/observatory/fl10"` remains anywhere). Storyboard: added Studio link. `route-policy.ts` legacy `/fl/*` aliases unchanged.
- API consumers: `fl10*` client methods and `/observatory/fl10/*` routes are **kept** (API is not removed with its page); the Studio adds `/product/v1/studio/*`.
- Tests migrated/added: `studio/__tests__/{studio,components,routes-consolidation}.test.ts`, `tests/test_studio_{specs,isolation,observer,api}.py`, `tests/test_successor_chain_governance.py`; no existing test was removed or weakened (the two "no performance claim"/"diagnos*" guards were satisfied by changing the new copy, not the guards).
- Historical tool: `scripts/fl10_browser_smoke.mjs` (FL10 evidence generator for the retired page) is kept as historical evidence tooling; the Studio verification is `scripts/studio_browser_verify.mjs`.
- Locks: no historical lock was edited. The files changed after `NHM_FL10_001` (frontend files, `fl10/runner.py` additive progress emits, `api/observatory_fl10.py`, `api/product_app_observatory_v1.py`, verifier compat modules) are re-pinned only by the new additive successor lock.
