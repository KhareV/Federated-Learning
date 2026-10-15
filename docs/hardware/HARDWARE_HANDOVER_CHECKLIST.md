# Physical ESP32 handover checklist (for the hardware teammate)

The emulator and the local replica cannot prove the sensors, wiring, I2C, ADC, TFT, BLE or the Wi-Fi radio work, nor
that the deployed Render service behaves like the replica. This list is what must be collected and run on the real
hardware before anyone says "physical hardware verified".

## 1. Things to hand over

| Item | Why |
|---|---|
| Final ESP32 sketch (the exact file flashed) | confirm payload, 50 ms rule, reconnect interval, lead-off handling |
| Render service source **and** deploy version/commit | the replica is only a guess; real validation/batching/timezone unknown |
| WebSocket host, port, path as actually used | the sketch uses `beginSSL(host, 443, "/")` |
| Timezone used to name `records_YYYY-MM-DD` | NHM does not assume UTC; this confirms rollover behaviour |
| Does the server insert one document per frame, and with how many in flight? | out-of-order commits were found with 4 in flight (reader now tolerates 5 s) |
| Render idle-timeout / free-tier spin-down behaviour | a cold start looks like several seconds of WAITING |
| Measured frame rate from the device (serial log timestamps) | rehearsal models ≈ 17 Hz; the real value decides chart density |
| Any ECG lead-off flag | the payload has none, so `2048` cannot be read as "leads off" |
| MAX30102 warm-up / finger-placement time before BPM/SpO₂ become non-zero | BPM/SpO₂ are `0` until valid |
| Known Wi-Fi reliability issues (hotspot sleep, DHCP, captive portal) | each causes the 5 s reconnect pattern |

## 2. Optional staging step (strongly recommended)

Deploy a second instance of the **real** Render service with `MONGODB_DATABASE=nhm_rehearsal` (any isolated
database/collection prefix), then run the emulator against its URL:

```bash
PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.emulate_esp32_ws \
    --url wss://<staging-host>/ --plan "run:60,drop:9,run:30" --run-tag STAGING-1
```

Point NHM at that database (`NHM_HARDWARE_MONGO_DATABASE=nhm_rehearsal`, `NHM_HARDWARE_MONGO_COLLECTION=records_*`).
Only then may evidence be labelled `VERIFIED_WEBSOCKET_TO_STAGING_RENDER_TO_ATLAS`. Never aim the emulator at the
production Render URL: it would write synthetic data into the production collections.

## 3. Physical smoke test (production pipeline)

1. Run `python -m scripts.hardware_preflight` – expect `SOFTWARE READY`, source `PRODUCTION HARDWARE`.
2. Power the ESP32 with ECG leads and MAX30102 attached. Watch the TFT: green Wi-Fi dot, BPM/SpO₂ fields.
3. Preflight again: `FRESH RECORDS ARRIVING`. (Still not proof of a sensor; it could be any writer.)
4. NHM → Monitor → *Live hardware (MongoDB)* → Start Monitoring. Check `WAITING` → `LIVE DATA RECEIVED`.
5. Compare three newest MongoDB document `_id`/`ecg`/`bpm`/`spo2` values (Atlas UI) with "Latest received" on the page.
6. Touch/remove an electrode and the finger: expect ECG/BPM/SpO₂ changes; note that `2048`/`0` are placeholders.
7. Power-cycle the ESP32 or disable Wi-Fi for > 5 s: expect `STALE DATA`; restore: expect recovery within one
   5 s reconnect period plus Wi-Fi association time, session still ACTIVE.
8. Stop Monitoring → History shows the saved session; start a second session and confirm the first is unchanged.
9. Federation → Training data: *Recorded hardware* → pick the session → run 3-round FedAvg (labels are synthetic).
10. Save: serial log excerpt, Render log excerpt with accepted frames, three Atlas document IDs, screenshots.

Only after steps 1–10 are done on the physical device may a report use `VERIFIED_PHYSICAL_ESP32_PRODUCTION`.
