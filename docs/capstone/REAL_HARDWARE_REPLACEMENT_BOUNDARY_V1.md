# REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1

Machine-readable: `contracts/capstone/real_hardware_replacement_v1.json`.

```
Today :  SimulatedWearableSource -> VirtualEdgeNode  -> DeviceSource/ObservedRecord -> existing runtime -> FL client
Future:  PhysicalWearableSource  -> RealEdgeGateway  -> same DeviceSource/ObservedRecord -> same runtime -> same FL client contract
```

Only the wearable source adapter (and its transport) and the edge host (phone/laptop/edge gateway)
change. Unchanged: ObservedRecord (`SAMPLE_SCHEMA_V1`), WearableStreamRuntime, PREPROC_V1, GAP_POLICY_V1,
QUALITY_V1, MODEL_V2_FINAL, GATEWAY_ARTIFACT_V2, CAL_V2, ALERT_POLICY_V1_MODEL_V2_BINDING, API_SCHEMA_V1,
session semantics, `PRODUCT_LIVE_EVENT_V1`, the FL client/federation contracts and model governance.

A sensor-class device is never assumed to run the PyTorch training stack: training runs on the edge host.

## VERIFICATION_REQUIRED (not invented)
BLE packet format, ADC scaling, real source rate, packet latency, clock drift, signal units, and the
real training-label source. New physiological data has no automatic label; future physical FL needs an
explicitly validated label source (verified annotation, clinician review, expert adjudication, or another
separately validated protocol). No real validation is claimed.
