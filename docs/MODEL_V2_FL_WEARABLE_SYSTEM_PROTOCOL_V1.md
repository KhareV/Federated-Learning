# V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1 (V2-FL-005, gate V2FLG4) -- ENGINEERING ONLY

Machine-readable protocol: `configs/model_v2/v2_fl_wearable_system_protocol_v1.yaml`.
Command: `python -m scripts.run_v2_fl_005_system_demo [--preflight|--verify|--canonical]`.

## What this is
A software/systems exercise: deterministic WEARABLE_SIM_V1 virtual clients (`WEARABLE_SIM_FL_COHORT_V1`,
8 clients, SIM_P000101..108, 480 s sessions, 360 Hz simulation input convention) are converted by the
production-like ECG stream path into client-local MODEL_V2 training windows, trained for three FedAvg
rounds from `FL_INIT_V2` through a typed envelope/router/coordinator, with exactly-once commits,
arrival-order canonicalization, restart/resume, deterministic replay and a one-round Flower SecAgg+
shadow (`WEARABLE_SIM_FL_SECAGG_COMPAT_V1`). The 24 local trainings are engineering calls, not
scientific candidate fits; the final state is disposable (no checkpoint, no gateway export, no cutover).

## What this is not
No efficacy metric is computed (no AUPRC/AUROC/F1/sensitivity/specificity/accuracy). Labels
(`WEARABLE_SIM_EVENT_WINDOW_V1`, scheduled SYNTHETIC / ENGINEERING EVENT timestamps) exist only inside
the client-local adapter and are NOT AAMI_SVF_WINDOW_V1. Events are S-like/V-like/F-like engineering
perturbations with no physiological-morphology claim.

## Source-replacement boundary (VIRTUAL_FL_CLIENT_SOURCE_V1)
The synthetic generator is one implementation of the local `ObservedRecordSource`. The dataset
builder, client trainer, update envelope, router, aggregator, SecAgg compatibility layer and round
coordinator depend only on the ObservedRecord contract and on model-update envelopes, never on
generator internals or SimulationTruth. A different future local source implementing the same
contract can replace the generator without changing server routing, aggregation or secure
aggregation. No hardware implementation or claim is made.

## Claim boundary
The deterministic WEARABLE_SIM_V1 virtual-client cohort was successfully converted through the
production-like ECG stream path into isolated client-local MODEL_V2 training windows and exercised
through a three-round federated software workflow. Routing, exactly-once aggregation, restart/resume,
deterministic replay and one-round Flower SecAgg+ compatibility passed. This is software and systems
engineering evidence only; it is not AAMI-SVF efficacy, clinical evidence, real-wearable validation
or a model-promotion result.

## SecAgg shadow max_weight (disclosed pre-freeze decision)
SECAGG_CONFIG_V2 (max_weight 4096, sized for 1436-example real clients) is unchanged. The compat
binding overrides exactly one parameter, `max_weight = next_power_of_two(2 * 93) = 256`, derived only
from the cohort's structural example counts. Pre-freeze dry runs (max_weight 4096 failed the 1e-4
tolerances; exploratory 1024/256/128) are NOT canonical evidence. After the method freeze no further
change is permitted; a canonical failure is preserved, never re-tuned.
