# NHM_HARDWARE_V2_OBSERVATORY_001 — pretrained V2 on recorded hardware, hardware in the Observatory, site-wide extension audit

Research prototype. Not a clinical claim. Physical ESP32 and the deployed Render service are **not** verified; every hardware result below is
`VERIFIED_LOCAL_RENDER_REPLICA` (ESP32 WebSocket emulator → local ingestion replica → Atlas rehearsal database `nhm_rehearsal`). `health_db` was not written.

## 1. What was asked and what was done

| # | Request | Result |
|---|---------|--------|
| 1 | `ILLEGAL_DEVICE_TRANSITION:STOPPED->SCANNING` on synthetic monitoring | Fixed (Device page offered Scan in `STOPPED` / `DISCONNECTED`; the frozen lifecycle forbids it). Buttons now follow the frozen table; a stopped device offers **Reconnect**. |
| 2 | Pretrained V2 for recorded-hardware runs | Implemented as a real engine (`studio/hardware_v2.py`), not a relabel. |
| 3 | Session replay / trace for hardware sessions | Window trace (`/app/observatory?hw=`) and session replay (`/app/observatory/replay?session=`) work on recorded hardware. |
| 4 | Run the earlier simulated tests to show hardware still works | See §5. |
| 5 | Find what else is software-only and extend it | See §4. |
| 6 | Source mode: use the signal of the user's monitoring session | Implemented: a completed History session becomes one client's data (synthetic-assigned labels, as for hardware); the live-monitored cohort site (SITE_00…SITE_07) stays as the other signal choice. |

## 2. Defect and extension ledger

### 2.1 Device lifecycle (`STOPPED → SCANNING`)
* Root cause: `device/+page.svelte` enabled **Scan** for `DETACHED`, `STOPPED` and `DISCONNECTED`; `contracts/capstone/device_source_v1.json` allows `SCANNING` only from `DETACHED` and `ERROR`. A finished session leaves the device `STOPPED`, whose only legal moves are `CONNECTED` (link kept) and `DETACHED`.
* Fix: `frontend/src/lib/product/device-lifecycle.ts` mirrors the frozen table; Scan / Connect / Reconnect / Disconnect are enabled exactly where the table permits. The Monitor page offers **Reconnect device** when the device is `STOPPED`. A pytest pins the TypeScript table to the frozen contract JSON.

### 2.2 Pretrained V2 for recorded hardware
The tabular hardware demo model cannot take V2 weights, so a V2 hardware run is a different model family built from the same machinery as a synthetic V2 run:

* windows: recorded readings are resampled onto the V2 source grid (linear interpolation between real readings only, documented ADC-scaling **assumption**) and the **unchanged** `PREPROC_V1` runtime builds and grades 10 s windows; only windows graded VALID and complete train (the synthetic cohort's `is_trainable` rule);
* split: per-session chronological holdout block, **time-purged** so no training window overlaps a holdout window (asserted in tests);
* labels: deterministic, balanced, seeded and **synthetic** (recorded telemetry has no ground truth);
* topology: **one recorded client plus the seven canonical synthetic peers** (SIM_FL_SITE_01..07, the unchanged cohort datasets). This replaces the earlier eight-way split of one recording, which read as eight fake devices. The recorded client uses at most 93 windows (the canonical cohort's largest client), which keeps the frozen round-1 SecAgg+ shadow applicable as it is for a synthetic run; the earlier `shadow_runner` addition to `fl10/runner.py` was therefore removed. The recorded client's labels are synthetic-assigned, the peers keep their event-window labels, and the UI names both;
* training: the unchanged FL10 runner (`Coordinator`, `train_local_epoch_v2`, FedAvg/FedProx) starting from the digest-verified `MODEL_V2_FINAL` state; R0 equals frozen V2;
* round-1 SecAgg+ shadow: the frozen shadow only accepts the canonical cohort's example counts, so `fl10.runner.run_training` gained one **additive, default-off** parameter `shadow_runner`; hardware runs pass the generic Flower SecAgg+ harness of the recorded-hardware demo. Authoritative aggregation stays plain;
* evaluation: isolated V2 scorer on the holdout block (diagnostic only); the committed states are also mirrored to the existing **unseen-cohort generalisation lane** (frozen V2 baseline, paired participant-cluster intervals);
* quality gate honesty: under the documented scaling a large-amplitude signal is graded `CLIPPING → UNUSABLE` and a run is **refused with the counts and reasons** (nothing is relabelled). The starter shows a preview (`/studio/hardware-demo/v2-preview`) before a run can start.
* retention: NHM keeps the newest 2000 readings of a session (about 100–118 s), i.e. roughly 21 windows; a V2 run needs 16 training + 4 holdout windows, so one full session is the minimum and the preview says so.

### 2.3 Hardware in the Observatory
`product/observatory/hardware_trace.py` reuses `reconstruct_window` (the same stage observers as the synthetic Observatory) with the resampled records as the source, then relabels units/limitations/claim boundary. Windows are scored by the released service **once per window** (cached per window content, shared with the Monitor page). Findings fixed on the way: the released service demands monotonic timestamps per session id, so scoring uses one inference session per window (an out-of-order trace was impossible with a shared id; covered by a test that traces windows in shuffled order).

### 2.4 Live-monitored site choice
`studio/site_monitor.py` generalises the frozen `monitor_site00` to any cohort site without editing it (site 0 delegates to the original function). Sites 3 and 4 reproduce their canonical datasets (parity measured in tests).

### 2.5 History monitoring session as the signal of one client
`studio/session_source.py` regenerates a COMPLETED simulated session's windows from its frozen scenario and seed (the Observatory relies on the same determinism; no new monitoring session, no new inference) and makes the VALID, complete windows the local data of the chosen client; the other seven stay canonical. A scenario session has no scheduled engineering events, so labels are **synthetic-assigned** (deterministic, balanced), exactly as for recorded hardware, and every surface says so. Tested for all five frozen scenarios, with owner / state / forgery refusals, and end to end through the real runner (buffer trace verified) and in a real browser.

### 2.6 Federation journal replay
The page waited for the server to close the journal, which only happens after evaluations and export settle (minutes after a run is `COMPLETED`), and reported the idle socket as a disconnect. Replay now starts at the terminal event and authenticates with the Clerk token like the live page.

## 3. Scientific and design boundaries

1. **V2 on hardware is experimental and not valid**: validated on MIT-BIH ECG, not on this signal chain; the ADC scaling is unverified; labels are synthetic; the holdout is a diagnostic of the same recording, not an independent test.
2. The unseen-cohort lane scores the **synthetic** G1 cohort; for a hardware run it answers "did fine-tuning on this recording move V2 on a standard unseen task", nothing more.
3. A History session carries no event truth, so its labels are synthetic-assigned (as for recorded hardware); metrics on them are not comparable to the cohort's event task.
4. Hardware replay "policy state changes" are derived from consecutive per-window results; there is no persisted monitoring state machine for hardware, and the page says so.

## 4. Site-wide audit: software-only features and what was done

| Surface | Before | Now |
|---|---|---|
| Observatory signal path (`/app/observatory`) | frozen scenarios and simulated sessions only | + recorded hardware sessions |
| Session replay (`/app/observatory/replay`) | completed simulated sessions only | + recorded hardware sessions (bounded scoring batches, progress shown) |
| Federation journal replay | only the original 3-round runs | all completed runs: 3-round, FL10, recorded hardware; client namespace, round jumps and source names follow the run |
| History (hardware rows and detail) | evidence + "use in FL" | + Replay and Trace links; Monitor offers Replay after Stop |
| Federation starter | hardware: fresh / warm start only | + pretrained V2 (preview, refusal, FedAvg/FedProx, SecAgg shadow) |
| Live page for a hardware run | no Generalisation tab | pretrained-V2 hardware runs have it; tabular runs state why not |
| Run context / labels / badges | `SITE_00` hard-wired | monitored site named; hardware V2 lineage and data sentence |
| About / Models copy | "no model inference on hardware" | states the experimental, resampled, not-valid use |
| Device page | simulated lifecycle only | unchanged by design (no device auth, no new IoT platform); lifecycle bug fixed |
| Scenario / fault lab, research, evidence, tour | frozen synthetic or scientific evidence | **not extended on purpose**: they describe frozen scenarios and published results, not user data |
| Per-client frozen-cohort window trace | frozen synthetic clients | not extended: hardware clients' windows are reachable through the new window trace |

## 5. Verification (final file set)

| Gate | Result |
|---|---|
| Complete Python suite (`PYTHONPATH=src:.`) | **3480 passed, 1 skipped, 0 failed** |
| Frontend tests | **413 passed** (3 skipped) |
| `svelte-check` | 0 errors |
| Production build, direct-load HTTP gate | pass |
| `git diff --check` | clean |
| Browser a11y audit (28 routes × 4 viewports) | 112 entries, 0 tool errors; 0 outside-viewport / obscured / hidden / no-ring stops; 0 semantic defects |
| Successor locks | `NHM_HARDWARE_V2_OBSERVATORY_001` (bf335bb, pushed) and `NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001` (chains from it); predecessor locks untouched |

Real-browser gates (Chrome, Clerk test users; hardware gates use the ESP32 emulator → local replica → `nhm_rehearsal`, `VERIFIED_LOCAL_RENDER_REPLICA`):

* `--hardware-v2`: PASS (one recorded client + seven peers; replay, trace, V2 preview, FedProx + SecAgg shadow with the frozen shadow, generalisation 4/4, federation replay of the run).
* `--history-source`: PASS (a completed simulated session from History as the signal of SITE_02; synthetic-assigned labels named; overview and federation replay open).
* Earlier hardware tests re-run on the final code: Scenario A/B + owner probe, run-switch, away lifecycle all PASS; earlier on the V2 build: rehearsal smoke 1/1, faults 18/18, UI tour 116 route visits.

## 5b. Simulated end-to-end hardware journey (sketch-faithful)

The supplied firmware sketch was used to model the device: compact `{"bpm","spo2","ecg"}` frames at about 17 Hz, **mock BPM `random(72, 82)` refreshed every 2 s (never measured)**, SpO₂ from `110 − 25·red/ir` kept only above 80 (zeros without a finger), ECG from an AD8232 front end (flat 2048 placeholder with the leads off). `scripts/emulate_esp32_ws.py` gained `--vitals sketch` and the `sketch` / `sketch_highgain` patterns.
Chain: emulator → local Render replica → Atlas rehearsal database `nhm_rehearsal` → NHM backend → real Chrome with real Clerk test users (`python -m scripts.verify_hardware_connected_browser --producer ws --journey`; verdict `reports/hardware/simulated_journey/journey_verdict.json`). **23/23 checks PASS** on three recordings (two ~127 s sessions with a 6 s finger removal and a 6 s leads-off stretch; one high-gain session):

* live monitoring: records arrive and plot; BPM is 72–81 (the mock); SpO₂ 90–100 %; finger removal shows "Unavailable" (not 0); leads-off shows the 2048 placeholder; Stop keeps the count; the Mongo-side count equals the replica's inserts for every recording;
* History links; Observatory session replay of a recording (18 of 21 windows scored, the 3 windows over the flat leads-off stretch rejected with no invented result) and window trace (a rejected window has no model result);
* tabular hardware FL: FedAvg and FedProx + SecAgg shadow complete, eight recorded clients;
* pretrained-V2 FL: the **high-gain recording is refused with the CLIPPING reason**; the two good recordings train as one recorded client + seven peers, with metrics and generalisation 4/4.

Defect found and fixed: **Stop did not do a final catch-up poll**, so documents already stored in Atlas just before Stop could be lost to the 800 ms poll cadence (and a back-to-back next session could pick up the previous recording's late tail). `HardwareSessions.stop` now ingests what is already stored before closing the session; documents stored afterwards are still excluded (test added).

## 6. Limitations

* No NVDA / VoiceOver session; static-host SPA fallback is deployment-dependent; Live Federation is long (unchanged).
* Physical ESP32 and deployed Render unverified.
* A pretrained-V2 hardware run needs a recording the quality gate accepts; large-amplitude recordings are refused (by design) until the ADC scaling is verified.
* The warm start from an earlier V2 hardware run is not offered (only fresh/warm for the tabular model, and the pretrained checkpoint for V2).
* One monitored site per run; several simultaneously monitored sites are not offered.
