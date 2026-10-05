# CAPSTONE_LOCAL_BUFFER_BINDING_V1 (CAP-006)

How the frozen `LOCAL_TRAINING_BUFFER_CONTRACT_V1` is bound for the simulated capstone, **without changing the contract**.

* **Storage mode:** deterministic local in-memory regeneration. Nothing is written to central SQLite; no `.npy/.npz`/checkpoint is committed.
* **Records:** only TRAINABLE windows (`federated.virtual_client_source_v1.is_trainable`) become `TrainingBufferRecord`s, so `quality_eligible` is always `true`. Excluded windows stay visible as counts in the dataset manifest and are never padded or relabelled.
* **`model_input_ref`:** `LOCALREF:<dataset_sha[:16]>:<position>:<input_digest[:16]>` - an opaque local reference; the float32 `[1,2500]` tensor lives in the buffer's private store and only the owning client may resolve it (logical isolation on one laptop - not process/VM/hardware isolation).
* **`window_id`:** `<client_id>-W<right_edge_us:012d>`; **batch id:** `WEARABLE_SIM_FL_BATCH_0001__<client_id>__<dataset_sha[:12]>` (a deterministic engineering batch, not a real collection batch); **provenance id:** `WEARABLE_SIM_FL_COHORT_V1/WEARABLE_SIM_V1/<client>/<participant>/<dataset_sha[:16]>`.
* **Label:** `WEARABLE_SIM_EVENT_WINDOW_V1` from source `SIMULATION_TRUTH_ENGINEERING` only. It is NOT `AAMI_SVF_WINDOW_V1` and has no S/V/F, arrhythmia or clinical meaning. Labels never come from model predictions, monitoring state or thresholds.
* **Product meaning:** the eight clients are the frozen synthetic research partitions `SIM_FL_SITE_00..07` / `SIM_P000101..108` (WEARABLE_SIM_FL_COHORT_V1). They are not the logged-in user, not a patient, and no personalised model exists. Local training starts from `FL_INIT_V2`, never `MODEL_V2_FINAL`; a client update is a model delta, not a global/candidate/released model.
* **Scope:** local training only - no aggregation, no coordinator call, no SecAgg, no federation run, no candidate (CAP-007).
