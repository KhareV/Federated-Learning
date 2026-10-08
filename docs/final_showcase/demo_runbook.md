# Faculty demo runbook (7–10 minutes)

**Boundary to say first:** "Everything on the synthetic screens is a software demonstration on simulated data. The scientific outcomes are frozen research evidence. Nothing here is clinical, and no hardware is used."

## Before the session (2 min, off stage)
1. `python -m scripts.run_observatory_clerk_connected --env-file .env --build` (real sign-in, ports 8001/8002/4173), or DEMO: `python -m scripts.run_observatory_product --port 8002` + `npm run dev` (5173). Keys come from the environment/untracked `.env`; never show them.
2. Sign in, open **Observatory → Federated learning storyboard** and **FL research outcomes** in two tabs.
3. Fallback ready: `reports/final_showcase/recorded_run/recorded_verified_run.json` (shown on the storyboard as "Recorded verified run" when no live run exists).

## Script
| Min | Screen | What to do / say | If it fails |
|---|---|---|---|
| 0:00–1:00 | Storyboard 1–2 | Four lanes: A monitoring, B scientific FL, C synthetic engineering FL, H historical reference. Lane labels are on every screen. | Use the recorded run text. |
| 1:00–3:00 | Storyboard → **Start live-monitored SITE_00 run** | Opt-in: a new monitoring session streams real records, real inference answers, the emitted windows become SITE_00's training buffer. Point at phase, inference HTTP 200 count, parity checks. Takes about a minute. | Blocked state is truthful (no run is started). Say "recorded verified run" and read the recorded parity. |
| 3:00–4:30 | Storyboard 3–6 | Local batches → eight updates → weighted FedAvg → global state; raw data never leaves a client. Federation page shows per-client contribution. | Skip to step 6. |
| 4:30–6:00 | Storyboard 7 / Outcomes → synthetic evaluation | Independent holdout of eight unseen participants, protocol frozen before results. Ranking improves (AUPRC/AUROC) but the fixed 0.5 operating point predicts everything positive — **say this plainly**. | Open `TAB3_SYNTHETIC_GLOBAL`. |
| 6:00–8:30 | Outcomes (scientific) | Select dataset/algorithm/condition; training evolution from the real round log; centralized vs federated matrix and the four defensible readings. | Use FIG2/FIG5 PNGs from `reports/final_showcase/publication/figures/`. |
| 8:30–10:00 | Wrap-up | Limitations: 6 and 8 clusters, nominal intervals, exposed datasets, no paired interval vs centralized, simulated data. Point to the traceability table. | — |

## Labels you must read aloud
- "RECORDED VERIFIED RUN" whenever replaying stored output.
- "SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION" on lane C metrics.

## Do not
Claim superiority of federated over centralized; claim clinical validity; tune a threshold live; show keys or tokens.
