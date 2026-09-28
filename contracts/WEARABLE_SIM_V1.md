# WEARABLE_SIM_V1 — Synthetic Wearable Engineering Contract

## 1. Identity

```text
contract_id: WEARABLE_SIM_V1
kind: engineering/simulation contract, not a clinical dataset specification
status: DRAFT — contract/boundary only; the generation engine is not implemented at T004
spec_version: 2.2
```

`WEARABLE_SIM_V1` is a new, first-class identifier. It does **not** replace, alias, or redefine
`WEARABLE_V1`. `WEARABLE_V1` (v2.2's real synchronized wearable domain-validation dataset) remains
reserved exclusively for future real hardware/domain sessions, gated by T004's eventual canonical
hardware verification and G16. Every artifact produced under `WEARABLE_SIM_V1` must be traceable to
this identifier and must never be presented, logged, or reported as `WEARABLE_V1` evidence.

## 2. Purpose

`WEARABLE_SIM_V1` exists to let the entire hardware-independent software stack be developed and
exercised before physical ESP32/AD8232/MAX30102 hardware is available.

**Allowed uses:**

```text
software development
streaming pipeline testing
causal preprocessing tests
gap handling tests
quality logic
synchronization
multimodal context
alert state machine
gateway replay
API testing
dashboard testing
fault injection
transport simulation
longitudinal virtual-user testing
load/stress testing
reproducible demonstrations
```

**Never allowed as primary evidence for:**

```text
clinical accuracy
real wearable sensitivity
real wearable specificity
clinical prevalence
medical efficacy
real sensor calibration
real device-domain validation
```

## 3. Mandatory provenance marking

Every synthetic record must be unmistakably marked as synthetic. At minimum, any future simulated
canonical record includes:

```text
dataset_id = WEARABLE_SIM_V1
source = a SYNTHETIC_* provenance value (e.g. SYNTHETIC_PHYSIOLOGY, SYNTHETIC_MITDB_REPLAY)
simulation_version
simulation_seed
```

Synthetic participants are never identified as, or described using language implying, actual human
volunteers. `participant_id` values under this contract use the `SIM_P######` namespace (Section 8)
and are never drawn from, or confused with, real dataset patient identifiers.

## 4. Relationship to primary science (non-negotiable)

- **MODEL_V1**: the primary supervised ECG classifier is trained, validated, calibrated, internally
  tested, and externally evaluated exclusively via the locked real pathway — MIT-BIH (patient
  split → training → validation → calibration → internal test) and INCART (external). Synthetic
  wearable physiology under this contract never replaces that evidence, at any stage.
- **Federated learning**: the primary FL efficacy experiment's eight simulated research sites are
  built exclusively from whole real MIT-BIH training patients. Synthetic wearable virtual patients
  are never substituted into that experiment. They may be used later only for system
  infrastructure/routing/load-test demonstrations, and any such result must be explicitly labeled
  engineering evidence, never an efficacy or generalization claim.

## 5. Simulator modes

The engine (implementation begins at T005+) supports these explicit modes. Each mode's records
carry a `source` value identifying it, per Section 3.

| Mode | Description | Notes |
|---|---|---|
| `SYNTHETIC_PHYSIOLOGY` | Fully procedurally generated, internally coherent ECG/PPG/context signals. | No real-patient input. |
| `MITDB_REPLAY` | Real MIT-BIH ECG replayed through simulated wearable/device/transport behavior. | Provenance retains the public dataset identity; must never imply the ECG was physically captured by an ESP32. |
| `BIDMC_REPLAY` | Real synchronized BIDMC ECG/PPG context replayed through simulated wearable transport/device behavior. | Multimodal synchronization/context engineering only; not AAMI-SVF efficacy evidence. |
| `FAULT_INJECTION` | Known deterministic sensor/transport faults. | For quality/state-machine/robustness testing. |
| `LONGITUDINAL_COHORT` | Persistent synthetic participant identities over long virtual histories. | For longitudinal/session-continuity testing. |
| `LIVE_SPEED_REPLAY` | Simulation emitted approximately in real time. | For gateway/API/dashboard demonstrations. |
| `ACCELERATED_REPLAY` | Same deterministic session replayed faster than real time. | For automated testing throughput. |

## 6. Synthetic event boundary

The simulator may eventually produce patient-like ECG/event scenarios: normal-dominant rhythm,
S-like / V-like / F-like event scenarios, irregular timing, high-rate/low-rate periods,
artifact-heavy sessions, and sensor-failure sessions. These synthetic event labels may support:

```text
software correctness
stress tests
quality tests
state-machine tests
dashboard demonstrations
```

They do **not** and never will replace the real MIT-BIH/INCART labels for final AUPRC,
sensitivity, specificity, patient-level generalization, or external validation. No synthetic-event
result may be reported alongside, or in place of, those metrics.

## 7. Three-layer simulation architecture

The future simulation engine (not implemented at T004) is architecturally three layers:

### Layer A — latent physiology

Produces ideal/internal signals and physiological timing: ECG waveform, cardiac event timing, PPG
pulse timing, pulse rate, slow SpO2 trajectory, activity state.

### Layer B — sensor/device observation

Transforms latent signals into simulated device observations.

- ECG effects: baseline wander, motion artifact, EMG-like noise, gain variation, offset, ADC noise,
  clipping, flatline, lead-off, dropout.
- PPG effects: motion artifact, poor contact, ambient-light-like contamination, clipping,
  saturation, dropout, red/IR degradation.

### Layer C — transport/system behavior

Simulates packet loss, burst loss, duplicates, latency, short gaps, long gaps, network disconnect,
reconnect, device restart, session restart, clock drift, timestamp jitter.

T004 defines this architecture and its boundaries only; the engine itself is out of scope here.

## 8. Virtual participant model

```text
SIM_P000001
SIM_P000002
...
```

A virtual participant has persistent parameters across sessions, conceptually organized as:

```text
participant_id
simulation_seed

physiology_profile:
  baseline HR
  HR variability tendency
  ECG morphology profile
  PPG morphology profile
  pulse-transit timing
  slow SpO2 baseline/dynamics

behavior_profile:
  activity patterns
  motion tendency
  session schedule
  contact instability

device_profile:
  ADC offset/gain variation
  simulated clipping tendency
  PPG response variation
  clock drift
  transport reliability
```

These are simulator parameters chosen for engineering coverage. Their distributions are **not**
described as epidemiologically representative unless a later task explicitly sources them from real
population data under change control.

## 9. Longitudinal session model

```text
participant -> day -> session -> activity intervals -> latent physiology
            -> sensor observation -> transport behavior -> canonical record
```

Activity states align with the existing project vocabulary:

```text
rest_seated
standing
walking
small_motion
unknown
```

A synthetic session manifest specifies: `participant_id`, `session_id`, `duration`, `seed`,
`activities`, `device profile`, `scheduled physiological events`, `scheduled sensor faults`,
`scheduled transport faults`.

## 10. Truth channel separation

The simulator maintains two conceptually distinct streams:

- **`ObservedRecord`** — what normal NHM software receives. Shaped like
  `contracts/sample_schema_v1.json`, with the provenance fields from Section 3.
- **`SimulationTruth`** — internal ground truth, potentially containing `true_activity`,
  `latent_hr`, `latent_spo2`, `scheduled_fault`, `actual_fault_active`, `packet_should_drop`,
  `true_signal_quality`, `source_mode`.

**Production NHM components (preprocessing, quality logic, fusion, model inference, API, dashboard)
must never read, import, or otherwise depend on `SimulationTruth`.** Only tests, simulator
self-validation, and controlled engineering evaluation may consume it. This boundary exists
specifically to prevent hidden leakage of synthetic ground truth into anything that resembles
production decision logic.

## 11. Deterministic generation

The simulator must be deterministic:

```text
simulator_version + cohort_manifest + participant seed + session seed + scenario configuration
  = reproducible output
```

No global untracked random state. Seeds and configurations are saved alongside generated evidence.
A simulator behavior change that would invalidate previously generated results requires a version
bump (Class B for a non-scientific engineering-simulation revision; Class C only if it were ever
used as primary scientific evidence, which Section 4 prohibits).

## 12. Dataset size profiles

Logical profiles for future implementation (T005 chooses smoke-scale defaults; no final patient
counts are hardcoded here):

```text
WEARABLE_SIM_SMOKE   small deterministic fixture cohort
WEARABLE_SIM_DEV     moderate development cohort
WEARABLE_SIM_FULL    large longitudinal research-demo cohort
WEARABLE_SIM_STRESS  very large procedural/load-test cohort
```

The design supports hundreds to thousands of virtual participants procedurally.

## 13. Materialization policy

Preferred philosophy: `manifest + configuration + seed = reproducible generated stream`. Large
datasets are generated only when needed, not by default. When materialized, prefer efficient
columnar formats (Parquet/Arrow) over large JSON files. Generated large data stays outside Git.

Git retains: generator code, configs, seeds, manifests, small golden fixtures, hashes/evidence. No
`pyarrow`/`pandas` dependency is added at T004; that decision belongs to the task that first needs
it.

## 14. Contract identifiers

```text
WEARABLE_SIM_V1
WEARABLE_SIM_SMOKE
WEARABLE_SIM_DEV
WEARABLE_SIM_FULL
WEARABLE_SIM_STRESS
```

Reserved and distinct: `WEARABLE_V1` (real hardware, not defined or altered by this contract).

## 15. What T004 does not implement

This contract defines interfaces and boundaries only. T004 does not implement: the physiological
waveform generator, MIT-BIH/BIDMC loaders, dataset downloads, AAMI mapping code, preprocessing,
MODEL_V1, Flower/FedAvg/FedProx/SecAgg+, gateway inference, the FastAPI runtime, the dashboard, new
ESP32 firmware, or a real MongoDB adapter. Implementation begins with the T005 vertical slice and
grows through subsequent software-track tasks.

## 16. T005 vertical-slice fixture representation note

`contracts/sample_schema_v1.json` describes one canonical sample; it does not yet define a
multi-rate synchronization or storage convention for ECG (250 Hz target) and PPG (100 Hz target)
arriving at different nominal rates. Rather than inventing an unreviewed synchronization contract
to simplify the T005 fixture, the golden fixture (`tests/fixtures/session_v1.jsonl`, generated by
`simulation/wearable.py` via `simulation/fixtures.py`) uses the narrowest representation compatible
with the existing contract: each `ObservedRecord` line stands for one discrete scenario segment
sample, with ECG and PPG/context fields co-occurring on the same record purely for smoke-test
illustration. This is **not** a claim that a physical device emits ECG and PPG in a single
synchronized record at those rates, and the sparse handful of samples per segment is not evidence
of measured sampling rate, jitter, or cross-sensor synchronization — those remain
`VERIFICATION_REQUIRED` under `contracts/HARDWARE_DATA_CONTRACT_V1.md` §7. Exact multi-rate
synchronization and resampling semantics are deferred to T011 (causal preprocessing) through T013
(windowing), which own `PREPROC_V1`/`GAP_POLICY_V1`.
