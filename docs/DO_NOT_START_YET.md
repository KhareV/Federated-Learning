# Do Not Start Yet

This is the human-readable view of `manifests/do_not_start_v1.csv`. The CSV is normative for
automated enforcement. A blocked item may use only its explicitly listed fixture work.

| Work item | Blocked until / gate | Allowed fixture work |
|---|---|---|
| Real ML training | Target, split, and preprocessing freeze / G4, G5, G6 | Toy shapes and fixed synthetic training fixtures. |
| FedAvg conclusions | MODEL_V1 lock and analytical aggregation / G8, G11 | Toy aggregation and serialization. |
| FedProx | FedAvg and non-IID correctness / G11, G12 | mu=0 objective fixture. |
| SecAgg+ | Plain aggregation correctness / G11 | Threat-model and reference-interface fixtures. |
| Quantization | MODEL_V1 and gateway characterization / G8, G15 | Toy export harness. |
| MCU inference optimization | Gateway benchmark / G15 | Operator inventory and memory-budget template. |
| Dashboard cosmetics | Runtime/API contract / G18 | Accessible low-fidelity state fixtures. |
| Large wearable data collection | Canonical ingest/sync and ethics verification / G1, G16 | Sanitized replay fixtures and minimal bench dry run. |
| Final report polishing | Stable reproducibility/integration evidence / G20, G21 | Report skeleton and evidence links. |
| Extra model architectures | Predeclared question and change approval / G8 | Test doubles only. |
| Extra datasets | Versioned Class C scope revision / G0 | Preserve local files without core use. |
| Clinical claims | Never permitted / G0, G22 | Research-target and engineering wording only; diagnostic, decision-support, treatment, and clinical-readiness claims remain prohibited. |

These controls do not authorize work when a gate passes; they only remove one prerequisite. Normal
task sequencing, ethics, source authority, and change control still apply.
