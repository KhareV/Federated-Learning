# Faculty demonstration: operator checklist

Durations are measured in the rehearsal on this laptop (local services, Atlas, Chrome). Network and Render
cold-start time on the day are the main unknowns; budget the margin shown.

## Before the room (T-15 min)

| # | Step | Measured | Done |
|---|---|---|---|
| 1 | `PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.run_nhm` (builds frontend, starts inference/product/frontend) | ≈ 90 s | ☐ |
| 2 | `python -m scripts.hardware_preflight` → must say `SOFTWARE READY` and `source: PRODUCTION HARDWARE` (never `STAGING TEST` for the real demo) | 5 s | ☐ |
| 3 | Power the ESP32 (leads + MAX30102 on); TFT shows the green Wi-Fi dot | device dependent | ☐ |
| 4 | Preflight again: `FRESH RECORDS ARRIVING`. Remember: this does not prove a sensor is attached | 5 s | ☐ |
| 5 | Sign in with Clerk; Monitor → *Live hardware (MongoDB)*; the header must **not** say "SYNTHETIC TEST SOURCE" | 20 s | ☐ |

If step 4 says `NO FRESH RECORDS`: fix the device/Wi-Fi/Render first. Do **not** switch to synthetic data without
saying so; the fallback is the labelled simulated wearable (*Simulated wearable* source), shown as simulation.

## Live segments (suggested ≈ 10 min)

| Segment | What to show / say | Time |
|---|---|---|
| 1. Start | Click *Start Monitoring*. State `WAITING FOR DATA` → `LIVE DATA RECEIVED` within ~1–2 s if the device is already transmitting. Old records are excluded by the high-water mark. | 0:30 |
| 2. Waveform | Real MongoDB ECG points against server ingestion time; point count, latest MongoDB id, raw ADC value. State the limits: ~17 readings/s, no verified ADC rate, no filtering. | 1:30 |
| 3. Vitals | Device BPM and device-reported SpO₂ (unverified, `0` shown as Unavailable). Signal-quality panel is descriptive (range, gaps, 2048 placeholder share). | 1:00 |
| 4. Experimental V2 | Scroll to the amber *EXPERIMENTAL · RESAMPLED · NOT VALID* panels: windows appear after ~15 s of data. Say it is a software demonstration of the model path on resampled data, not a result. | 1:00 |
| 5. Stale/recovery (optional) | Briefly cover the Wi-Fi or unplug power: `STALE DATA` after 5 s, session stays active; restore: recovery within ~5 s reconnect + association. | 1:30 |
| 6. Stop + History | *Stop Monitoring* → *View saved History*. Hardware table shows readings, duration, rate, source. Stopped count does not move while the device keeps sending. | 1:00 |
| 7. Federation | Federation → *Training data: Recorded hardware* → select the captured session → *Starting model* (fresh or warm start) → FedAvg, 3 rounds → *Create and start*. Eight logical clients, synthetic labels, real optimiser steps. Run completes in < 2 s locally. | 2:00 |
| 8. FedProx + shadow | Repeat with FedProx and *Round-1 SecAgg+ shadow* (completes in < 2 s locally). Say: "shadow verification; the authoritative aggregate stays plain". | 1:00 |
| 9. Evidence | Open previously verified 10-round / Generalisation evidence rather than re-running scientific experiments. | 1:00 |

Record **60–100 s** in segment 1–6 if the same session is to feed segment 7: only the newest 2,000 readings
(≈ 118 s at 17 Hz) are retained; History says "(newest N retained)".

Navigating away from Monitor (e.g. to History) does **not** stop the session. Records written while you are away are
picked up from MongoDB when you return to Monitor (the page shows STALE for a moment, then catches up). Nothing is
recorded in the background by NHM itself; only *Stop Monitoring* ends the session.

## Say explicitly

* The labels in the federated demo are synthetic and assigned for demonstration; nothing is clinically meaningful.
* Resampled V2 output is experimental and not valid for this signal chain.
* A successful database read is not proof that the physical sensor is attached.
* The deployed Render service and the physical device were verified separately from the software rehearsal
  (state which of those checks has actually been completed).

## If something goes wrong

| Symptom | Likely cause | Action |
|---|---|---|
| Stays `WAITING FOR DATA` | device off / Wi-Fi / Render cold start | check TFT dot and Render log; the app is waiting, not broken |
| `STALE DATA` | no accepted record for 5 s | transient Wi-Fi/Render; it recovers on its own |
| `MONGODB UNAVAILABLE` | Atlas/network from the laptop | check the laptop network; session is kept |
| Page blank after a rebuild | a build replaced files under the running preview server | restart `run_nhm` |
| Sign-in form does not appear | Clerk dev instance slow | reload once; verify `CLERK_*` in `.env` |
