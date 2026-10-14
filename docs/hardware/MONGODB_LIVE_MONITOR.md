# NHM hardware telemetry demonstration

## Actual Atlas schema observed 2026-10-14

Database `health_db` contains daily append-only collections named `records_YYYY-MM-DD`. The observed collections were `records_2026-09-14` (2,960 documents), `records_2026-09-15` (640), `records_2026-09-16` (33), `records_2026-10-10` (307), and `records_2026-10-13` (53). Each examined latest record had numeric `bpm`, `spo2`, `ecg`, BSON Date `timestamp`, and ObjectId `_id`. Only the default `_id_` index was present. The newest examined production record was on 2026-10-13 at 08:54:30.836 UTC; no October 14 collection was present during this audit. Current device transmission was not verified.

The sketch sends no timestamp, so the stored `timestamp` must have been added downstream. The Render source code was not available in this repository, so server generation cannot be independently audited. The browser labels it **stored server ingestion time**. For the daily single-writer stream, the adapter discovers the two lexicographically newest `records_YYYY-MM-DD` collections, merges their indexed ObjectId order and establishes the maximum `_id` at session start. It refreshes the collection list every two seconds, so a newly created daily collection is included without assuming whether Render uses UTC, IST or another date convention. This avoids replaying old records, including old records without `timestamp`. A document with no BSON Date timestamp is skipped. A producer with multiple concurrent ObjectId generators or client-supplied out-of-order IDs would need an explicit server sequence or change stream before this cursor can be treated as strict insert order.

No Render patch is required for the observed schema. If a future Render version omits the date, add `timestamp: new Date()` to each inserted measurement before `insertOne`, preserving the three device fields, collection naming, and MongoDB-generated `_id`. There is no destructive migration or TTL index. The built-in `_id_` index serves each bounded cursor query; the UI uses the stored timestamp for its horizontal scale. The observed records are all away from a day boundary, so they cannot establish Render’s date timezone. Render source code is still needed to confirm that convention; the reader does not depend on it.

## Data path and limits

ESP32 → existing Render WebSocket `/` → daily MongoDB collection → authenticated FastAPI `/product/v1/hardware/sessions` REST routes → Monitor browser poll every 800 ms → bounded 300-reading chart. On start, the backend marks the current newest ObjectId across both daily collections. Each poll fetches at most 500 newer documents per active daily collection and accepts at most 500 in merged global ObjectId order. It validates ECG in ADC range 0..4095, converts BPM 20..255 and SpO₂ 1..100, and treats zero as unavailable. Invalid ECG or missing/invalid timestamp records are skipped. The browser sorts the bounded chart by stored timestamp and breaks ECG lines for gaps over one second. `STALE DATA` begins after five seconds without an accepted reading; this is a demo threshold allowing roughly 100 expected 50 ms transmissions plus cloud delay, not a connectivity proof. A MongoDB query failure becomes `MONGODB UNAVAILABLE`; the next poll can recover.

SQLite keeps owner-scoped session metadata and the latest 2,000 accepted samples per session. The total accepted count persists even after old trace points are pruned. Session creation and stop never write MongoDB. Restart changes abandoned active sessions to `INTERRUPTED`. No V2 inference, calibration, quality verdict, clinical classification, or FL training runs on this low-rate feed. The shared, unauthenticated ingest feed is not proof of device identity or the user's physiological identity. The current sketch uses ECG 2048 when leads are off, so that value must not be interpreted as verified ECG contact. The crude device SpO₂ estimate is displayed as unverified.

## Local setup

Install the optional package in the product backend environment: `python -m pip install -r requirements-hardware.txt`. In the ignored root `.env` (never commit it), set:

```env
NHM_HARDWARE_MONGO_ENABLED=true
NHM_HARDWARE_MONGO_URI=<ROTATED_ATLAS_URI>
NHM_HARDWARE_MONGO_DATABASE=health_db
NHM_HARDWARE_MONGO_COLLECTION=records_*
```

The `records_*` setting discovers the current and previous daily collections. An existing setting such as `records_2026-10-13` also enables the same discovery, so no midnight restart is required. For the injection test use the exact `nhm_integration_test` name instead. Keep the existing Clerk variables and product SQLite path. Rotate the MongoDB and Wi-Fi credentials exposed in the conversation before deployment, plus any exposed Clerk sessions/tokens. The Atlas URI is server-side only. No hardware auth or pairing was added.

The current connected monitoring and federation WebSockets authenticate with a fresh Clerk session token in their first frame. The token is absent from the WebSocket URL. This updates the connected behavior described in the historical Clerk runbooks without editing those byte-frozen documents.

Activate a Python 3.11 environment first (`source .venv-studio311/bin/activate` in this workspace). From the repository root, run `PYTHONPATH=src:. python -m scripts.run_nhm --preflight-only`, then `PYTHONPATH=src:. python -m scripts.run_nhm` (the latter builds and starts inference, product backend, and frontend using the ignored root `.env`). Product and inference logs are written under the launcher workspace shown at startup. Use `tail -f <workspace>/logs/product.log` or `tail -f <workspace>/logs/inference.log`. For a direct backend console, export the same Clerk and hardware environment variables first, then run `PYTHONPATH=src:. python -m scripts.run_observatory_product --host 127.0.0.1 --port 8002`; the corresponding frontend dev command is `cd frontend && npm run dev`.

## Reproducible Atlas injection

Use a rotated URI supplied only through the environment. The publisher always writes `health_db.nhm_integration_test` and tags synthetic readings. Never configure the production collection for this test.

```sh
NHM_HARDWARE_MONGO_COLLECTION=nhm_integration_test python -m scripts.run_nhm
NHM_HARDWARE_MONGO_URI="$NHM_HARDWARE_MONGO_URI" python -m scripts.publish_hardware_test --count 20 --interval 0.05
NHM_HARDWARE_MONGO_URI="$NHM_HARDWARE_MONGO_URI" python -m scripts.verify_hardware_atlas
```

The automated verifier starts a real Atlas-backed session, injects tagged records, checks high-water exclusion, ID/value mapping, invalid values, unavailable vital values, delayed timestamps, dedupe, stale state, recovery, stop, fresh start, owner isolation and restart history. It deletes only the IDs it inserted. The manual publisher leaves its tagged test records for visual inspection; remove only those identified records after documenting them. To complete the separate browser gate, sign in with a Clerk test user, start the hardware mode showing `SYNTHETIC TEST SOURCE`, insert readings, capture the Monitor and History, then repeat with a second Clerk user for isolation. Return the collection setting to the actual daily production name and repeat with the physical ESP32 before claiming physical end-to-end success.

## Final verification status, 2026-10-14

A read-only production check at 17:15:32 UTC again found `records_2026-10-13` as the newest daily collection, with 53 records and latest `timestamp` 2026-10-13 08:54:30.836 UTC (`_id` `6acdf1c6eaaf3baec8bed6b6`). The ESP32 was explicitly unavailable for this verification turn, so physical transmission and device stoppage/recovery were not tested.

The final real Atlas injection verifier rerun passed after the rollover and duplicate-count fixes: seven readings accepted; pre-start, invalid, and post-stop records excluded; stale/recovery, owner isolation, and restart history passed; 13 of 13 inserted test records removed by ID. The genuine Clerk browser evidence, including exact SVG geometry and screenshots, is in `reports/hardware/browser/verification.json`. The connected simulated Monitor, WebSocket replay, History, three-round federation, Research, System, and logout checks are in `reports/hardware/browser/clerk_connected_summary.json`. These results verify software and cloud-read behavior; physical-device transmission remains unverified.
