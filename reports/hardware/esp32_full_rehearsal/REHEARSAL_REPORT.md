# ESP32 digital-twin rehearsal report

Target: **local replica of the ingestion server** (not the deployed Render service) → real Atlas (isolated `nhm_rehearsal`
database) → real NHM backend → real Chrome + Clerk. Physical ESP32: **NOT_RUN**. Staging Render: **NOT_RUN** (service
source and deployment unavailable). `health_db` was never written. Machine-readable: `release_classification.json`.

## Evidence levels

| Item | Level |
|---|---|
| Nominal chain, 18-scenario fault matrix (protocol level) | VERIFIED_LOCAL_RENDER_REPLICA |
| 10-minute protocol soak | VERIFIED_LOCAL_RENDER_REPLICA |
| Browser Scenario A + B + recorded-hardware FL (3/10 rounds, FedAvg/FedProx, round-1 SecAgg+ shadow) | VERIFIED_LOCAL_RENDER_REPLICA |
| 10-minute browser soak | VERIFIED_LOCAL_RENDER_REPLICA |
| Earlier direct-injection scenarios (`reports/hardware/final_demo`) | VERIFIED_DIRECT_ATLAS_INJECTION |
| Deployed Render, physical ESP32 | NOT_RUN |

## Defect found and fixed during the rehearsal

First smoke run: **FAILED** – 425 documents stored, 421 consumed. Cause: with several inserts in flight a lower `_id`
became visible after a higher one and the `_id > mark` cursor skipped it. Fix: 5 s look-back below the high-water mark
(never below the session start mark). Reruns: 678/678 and 10,149/10,149 consumed exactly once.

One scenario expectation was wrong and corrected before the accepted run: S08 restarted the server after 4 s, which
resolves at the 5 s stale threshold; it now uses an 8 s outage (the first fault-matrix run recorded 17/18 and S08 FAILED;
the S08 rerun in `20261015T131807Z_faults` passed).

## Fault matrix (expected behaviour was declared before execution; see each scenario's `expected`)

| Id | Scenario | Result |
|---|---|---|
| S01 | Nominal, NHM waiting before the device | PASS |
| S02 | Handshake rejected → accepted | PASS |
| S03 | Server unreachable at power-on, up 9 s later | PASS |
| S04 | 2 s stall, TCP survives (delayed burst, no STALE) | PASS |
| S05 | 9 s network loss, reconnect (STALE → LIVE) | PASS |
| S06 | Clean close and reconnect | PASS |
| S07 | Producer killed abruptly (STALE, session ACTIVE, Stop freezes) | PASS |
| S08 | Ingestion server restarted (8 s outage) | PASS (after expectation fix) |
| S09 | Atlas inserts failing ~7 s (frames lost and counted) | PASS |
| S10 | Malformed JSON, missing ECG, out-of-range values | PASS |
| S11 | ECG 2048 placeholder, BPM/SpO₂ 0 | PASS |
| S12 | Bursty timing (3 frames / 150 ms) | PASS |
| S13 | Midnight rollover mid-session | PASS |
| S14 | NHM backend restart mid-session (INTERRUPTED, no replay into new session) | PASS |
| S15 | Double start / double stop / immediate stop | PASS |
| S16 | Two users on the shared source, cross-access refused | PASS |
| S17 | Device transmitting first (high-water exclusion, second session) | PASS |
| S18 | NHM cannot reach MongoDB | PASS |

## Latency (milliseconds, one host, monotonic clocks)

| Stage | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| Emulator send → replica receipt | 10,149 | 0.44 | 0.59 | 0.82 | 8.1 |
| Replica receipt → Atlas insert ack | 10,149 | 76.6 | 145.5 | 240.1 | 971.1 |
| Atlas ack → NHM consumption (800 ms poll) | 10,149 | 588.9 | 1,093.8 | 1,238.7 | 1,840.4 |
| Emulator send → NHM consumption | 10,149 | 673.8 | 1,191.0 | 1,364.8 | 2,265.4 |
| Atlas ack → newest on-screen record (browser) | 75 | 101.8 | 171.3 | 701.3 | 701.3 |
| Emulator send → newest on-screen record (browser) | 75 | 181.1 | 420.4 | 760.8 | 760.8 |

Local-host figures: they exclude real internet/Render/Wi-Fi delay. The browser rows measure the freshness of the newest
record on screen at each refresh, not per-document delay (older documents in a batch wait up to one 800 ms poll).
Acceptance bound used: end-to-end ≤ poll interval (0.8 s) + Atlas ack p99 (0.24 s) + margin ≈ 2 s; the stale threshold
(5 s) is ≥ 2× that.

## Soak

* Protocol: 10 min, 10,149 frames at 16.9 Hz (first third 16.91 Hz, last third 16.91 Hz), 0 lost, 0 duplicated, 0 poll errors.
* Retention: record counter 10,149; stored trace 2,000 readings (118.2 s) – exactly the documented cap.
* Browser: 10 min, 20 samples, no error banner, plotted points capped at 300, DOM nodes flat at 783 after 90 s, JS heap
  41–71 MB sawtooth with no upward trend.

## What this does not establish

The deployed Render behaviour; real Wi-Fi/Render/Atlas latency; the sensors and radio; the device's real frame rate;
any physiological or clinical property of the signal. All data are synthetic engineering patterns.
