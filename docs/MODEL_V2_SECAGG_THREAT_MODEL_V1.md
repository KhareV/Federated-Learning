# MODEL_V2 SecAgg+ Threat Model (extension) -- MODEL_V2_SECAGG_THREAT_MODEL_V1

Phase: V2-FL-004 (gate V2FLG3). Extends, and does not replace, `docs/privacy_threat_model.md`
(historical T028, frozen, unchanged). Config: `SECAGG_CONFIG_V2`. Flower 1.39.0.

## What is evaluated
A controlled, single-host, in-memory simulation of Flower `SecAggPlusWorkflow` +
`secaggplus_mod` aggregating the eight `CLIENTS_IID_V1` client updates of a reconstructed
MODEL_V2 FedAvg IID round 1 (TRAIN only; FL_INIT_V2). Parameters are the historical T028 values.

## Adversary and observation boundary
Honest-but-curious aggregation server observing the **Flower application aggregation interface**
only (`FLOWER_APPLICATION_SERVER_AGGREGATION_INTERFACE_V1`). Clients are honest and all participate
(no dropout). Masked vectors, SecAgg+ key/share metadata and client identifiers may be visible to
the server and are reported, not hidden.

## Supported claim (narrow)
Within the configured Flower SecAgg+ controlled simulation, the protected application-level
server aggregation interface does not receive an individual participating client's clear
model-update array while forming the aggregate, and the protected aggregate matches the
unprotected reference within the predeclared numerical tolerance (max abs <= 1e-4, relative
L2 <= 1e-4).

## Explicitly unsupported claims
Anonymity; differential privacy; model-inversion resistance; membership-inference resistance;
malicious-client resistance; transport security / TLS; authentication / authorization; OS,
process or host isolation (single-host simulation); HIPAA compliance; hospital privacy;
institution-scale security; production security certification. The aggregate itself is revealed.

## Data locality
Audited at the instrumented message boundary: no raw ECG waveform, no AAMI labels and no client
minibatches appear in server-bound application messages. Host/process isolation is not claimed.

## Overhead
Runtime = aggregation protocol only (`time.perf_counter`; 1 warm-up + 10 measured trials per
path). Bytes = `FLOWER_APPLICATION_PAYLOAD_BYTES_V1` (deterministic Flower message protobuf;
not network bytes; excludes framing/TCP/TLS). No deployment-latency claim.

## Evidence hygiene
Private keys, raw secret shares and unmasked individual client updates are never persisted.
