# ESP32 network emulation and end-to-end rehearsal

Goal: make the physical ESP32 demonstration "a change of telemetry producer" instead of a new integration project,
by exercising the same network and cloud write path wherever that is possible, and by being exact about what this
does **not** prove.

## What is and is not verified

| Segment | Status in this repository |
|---|---|
| ESP32 sensors, wiring, I2C, ADC, TFT, BLE, Wi-Fi radio | **Not verified.** Needs the physical device. |
| ESP32 firmware → WebSocket frames (wire format, timing rule, reconnect rule) | Emulated from the sketch (`scripts/emulate_esp32_ws.py`). A model, not a measurement of the device. |
| **Render ingestion service** | **Not verified.** Its source/deployment was not available. A *local replica* (`scripts/render_replica_server.py`) built only from the sketch and the observed Atlas schema stands in. Evidence from it is `VERIFIED_LOCAL_RENDER_REPLICA`, never "Render verified". |
| Atlas write → NHM backend → browser → History → recorded-hardware FL | Verified against real Atlas (isolated `nhm_rehearsal` database) and real Chrome + Clerk. |
| Production hardware collections (`health_db.records_*`) | Never written. The replica refuses `health_db`; rehearsal NHM reads only `nhm_rehearsal`. |

Evidence levels used in reports: `VERIFIED_DIRECT_ATLAS_INJECTION`, `VERIFIED_WEBSOCKET_TO_STAGING_RENDER_TO_ATLAS`
(not reachable: no staging Render exists), `VERIFIED_LOCAL_RENDER_REPLICA`, `VERIFIED_PHYSICAL_ESP32_PRODUCTION`
(not reached), `NOT_RUN`, `FAILED`.

## Components

* `scripts/emulate_esp32_ws.py` – WebSocket client with the sketch's behaviour: path `/`, TLS when `wss://`, compact
  text frame `{"bpm":%d,"spo2":%d,"ecg":%d}` (byte-identical to the `snprintf`), BPM/SpO₂ `0` when unavailable, ECG
  `2048` while a lead-off pin is high, a frame only when `millis() - lastNetworkSend > 50` at a loop iteration (so the
  period is 50 ms **plus** loop work, not exactly 50 ms), reconnect every 5 s (`setReconnectInterval(5000)`).
  It has no database credentials. Plan steps: `run`, `pause`, `drop` (TCP reset), `stall` (TCP survives, delayed
  burst), `disconnect`, `unavail`, `burst`, `malformed`, `kill`. It records every attempt, hand-off, disconnect,
  reconnect and transport error with monotonic timestamps. A frame "handed to the transport" is not proof that
  MongoDB stored it.
* `scripts/render_replica_server.py` – WebSocket server shaped like the ingestion service: stores
  `{bpm, spo2, ecg, timestamp (server UTC Date)}` in daily collections `records_YYYY-MM-DD` of the rehearsal
  database; permissive about field types (so NHM's own validation is exercised); fault switches by flag file
  (rejected handshakes, failing inserts); simulated clock to cross midnight in seconds; JSONL event log. Everything
  beyond the sketch and the observed schema (validation, concurrency, idle timeout, timezone of the date) is an
  **assumption** exposed as a flag.
* `scripts/hardware_chain.py` – managed replica/emulator processes, the real NHM hardware service + authenticated
  REST routes polled like the browser (800 ms), and cross-stage correlation.
* `scripts/rehearse_hardware_demo.py` – one-command rehearsal (smoke / faults / soak / full).
* `scripts/hardware_preflight.py` – read-only operator preflight.
* `scripts/verify_hardware_connected_browser.py --producer ws` – real Chrome + Clerk + emulator → replica → Atlas.

## Commands

```bash
# 0. services (separate terminal)         PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.run_nhm
# 1. preflight (read-only)
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.hardware_preflight
# 2. smoke rehearsal (~1 min)             nominal chain + loss/duplicate accounting + latency
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.rehearse_hardware_demo --mode smoke
# 3. fault matrix (~10 min)               18 scenarios, expectations written before execution
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.rehearse_hardware_demo --mode faults
# 4. soak                                  
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.rehearse_hardware_demo --mode soak --soak-minutes 10
# 5. browser Scenario A/B + recorded-hardware FL via the emulator (needs Clerk test users json)
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.verify_hardware_connected_browser --producer ws --users-file <users.json>
# 6. everything                           
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.rehearse_hardware_demo --mode full --users-file <users.json>
```

Live logs: launcher output prints the workspace; product log is `<workspace>/logs/product.log`. Rehearsal evidence is
written under `reports/hardware/esp32_full_rehearsal/<run>/` (per-scenario replica + emulator JSONL logs, redacted:
no URIs, tokens or passwords).

## Findings from the rehearsal

1. **A real data-loss defect was found and fixed.** With four inserts in flight (as a Node `insertOne`-per-message
   server would have), a lower `_id` could become visible after a higher one; the reader's `_id > mark` cursor then
   skipped it permanently (4 of 425 documents in the first smoke run, all the ones with slower inserts). The reader now
   re-reads a 5 s window below its high-water mark, never below the session's start mark; duplicates are dropped by the
   `(session_id, document_id)` key. Regression test: `tests/test_hardware_rollover.py::test_late_lower_object_id_...`.
   After the fix: 678 of 678 and 10,149 of 10,149 stored documents were consumed exactly once.
2. **The device rate is not 20 Hz.** Following the sketch's rule the emulator's steady-state rate is ≈ 17 Hz
   (≈ 59 ms period). The "50 ms" value is a lower bound. Real figures must come from the physical device.
3. **A short Wi-Fi stall arrives as a burst** and the server stamps all of it with the receipt time, so the chart
   shows a gap followed by a compressed cluster. That is the data as stored; NHM does not invent samples.
4. **Reconnection is slow by design**: ≥ 5 s after the loss is noticed, so any real outage longer than ~0 s that
   resets TCP is at least ~5 s of missing data and will show STALE (threshold 5 s).
5. **BPM/SpO₂ 0 is "unavailable"** (no finger / not yet valid); NHM shows "Unavailable", never 0%.
6. **ECG 2048 cannot be interpreted as "leads off"**: it is also a legal ADC value and the payload has no lead-off
   flag. NHM stores/plots it and makes no contact claim. A lead-off bit in the payload would fix this (firmware change,
   optional).
7. **Retention is bounded, and the live demo must respect it**: the session trace keeps the newest 2,000 readings
   (≈ 118 s at 17 Hz). A longer recording keeps counting but only the newest ~2 minutes are stored for History and
   for recorded-hardware FL. History now says "(newest N retained)". Recommended demo recording: 60–100 s.
8. **Interrupted sessions are never silently active again**: on backend start every `ACTIVE` session becomes
   `INTERRUPTED` (data kept, eligible for FL). `Start` is idempotent, so a double click or a reload re-attaches
   instead of orphaning a session, and the Monitor resumes the user's active session after a page reload.

9. **Leaving the Monitor page does not stop the session, and does not record in the background.** The backend has
   no collector thread: readings are ingested only inside authenticated polls (every 800 ms while the Monitor is open).
   Leaving the page only detaches timers; the session stays `ACTIVE`, a returning Monitor re-attaches to the same
   session id, and the next polls catch up from MongoDB using the session's saved high-water mark (500 documents per
   poll). Verified in real Chrome + Clerk (15 s away, 252 readings written meanwhile, all counted exactly once,
   `VERIFIED_LOCAL_RENDER_REPLICA`). Limits: the trace keeps the newest 2,000 readings; if MongoDB's own retention
   removes documents while the page is away they cannot be recovered; a session whose owner never returns stays
   `ACTIVE` until Stop or a backend restart (then `INTERRUPTED`). Only the explicit Stop button ends a session.

## Bounded values (current)

| Value | Setting | At ~17 Hz |
|---|---|---|
| Browser poll interval | 800 ms | – |
| Stale threshold | 5 s since last accepted record | – |
| Chart buffer | 300 readings | ≈ 18 s |
| Session trace (SQLite) | newest 2,000 readings | ≈ 118 s |
| Reader batch | 500 documents per poll | – |
| Reader look-back | 5 s below the high-water mark | – |
| Collection discovery | every 2 s, two newest `records_YYYY-MM-DD` | – |

## Not covered / remaining risks

* The physical sensors and radio. The checklist in `HARDWARE_HANDOVER_CHECKLIST.md` lists what to collect.
* The deployed Render service (cold start, idle timeout, concurrency, error behaviour, collection-date timezone).
  A staging instance of the real server pointed at an isolated collection is still required for
  `VERIFIED_WEBSOCKET_TO_STAGING_RENDER_TO_ATLAS`.
* Clerk token expiry is exercised only by the multi-minute browser soak (Clerk session tokens are short-lived and
  refresh automatically); an explicit forced-expiry test was not run.
* All data in these runs is synthetic engineering test data. Nothing here is a physiological or clinical claim.
