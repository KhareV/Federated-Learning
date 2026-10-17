# Recorded hardware demo FL

This opt-in engineering demonstration is separate from `MODEL_V2_FINAL`, AAMI-SVF evaluation, and the G1 Generalisation lane.

## Data flow

1. ESP32 or the explicit synthetic test publisher writes `ecg`, `bpm`, `spo2`, BSON `timestamp`, and MongoDB `_id` to Atlas.
2. A Clerk-owned NHM hardware session accepts only documents newer than its start high-water mark and saves a bounded trace in SQLite.
3. After Stop, Studio snapshots the selected owner's trace. The snapshot is immutable for that run.
4. Non-overlapping one-second windows with at least ten messages produce twelve unvalidated engineering features. No resampling or 360 Hz claim occurs.
5. `SYNTHETIC_ASSIGNED_FOR_DEMO_V1` assigns balanced `NORMAL_MONITORED_PATTERN` and `POTENTIAL_ECTOPY_ASSOCIATED_PATTERN` labels (synthetic-assigned, provenance unchanged) deterministically from the window ID and recorded seed.
6. A disjoint label-stratified holdout is selected before training. Remaining windows are assigned once to eight chronological logical clients.
7. `HARDWARE_DEMO_MODEL_V1`, a one-layer binary classifier, performs genuine local SGD. FedAvg or FedProx (`mu = 0.1`) produces sample-count-weighted committed states for 3 or 10 rounds.
8. Optional `ROUND-1 SECAGG+ SHADOW` performs Flower protected aggregation and compares it with the authoritative plain aggregate. It makes no production privacy or anonymity claim.

The eight clients are logical partitions of recorded data. They do not represent eight devices, patients, or hospitals. Labels have no clinical meaning, and reported metrics do not establish medical performance.

## Commands

```bash
# Real Atlas synthetic publisher. URI is read only from the environment.
.venv-studio311/bin/python -m scripts.publish_hardware_test \
  --count 1200 --rate 20 --pause-at 25 --pause-duration 7

# Full service-level Atlas scenarios A and B, including 3/10-round demo FL.
.venv-studio311/bin/python -m scripts.verify_hardware_atlas_scenarios \
  --env-file .env --out reports/hardware/final_demo

# Real Chrome and Clerk scenarios. The users file stays outside Git.
.venv-studio311/bin/python -m scripts.verify_hardware_connected_browser \
  --env-file .env --users-file /path/outside/git/clerk-test-users.json \
  --out reports/hardware/final_demo/browser
```

For the physical demonstration, start the ESP32 and confirm Render is adding documents to the current `records_YYYY-MM-DD` collection. Then start NHM monitoring. The start call establishes a high-water mark, so only documents inserted afterward appear. Starting NHM first is also supported: it remains `WAITING FOR DATA` until the ESP32 begins writing. Stop ends only the owner-scoped NHM session; it does not stop the ESP32 or modify Atlas.
