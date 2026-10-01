# Hardware Deferred Execution Plan

## 1. Status

```text
task_id: T004
canonical_objective: Bench hardware verification and firmware packet contract
execution_status: BLOCKED
block_reason: BLOCKED_HARDWARE
hardware_available: false
g1_status: NOT_PASSED
hardware_contract_frozen: false
```

Physical ESP32/AD8232/MAX30102 hardware is currently unavailable for bench testing. T004's
canonical objective — eliminating hardware semantics uncertainty through bench measurement — cannot
be honestly satisfied without the physical system. This is an execution-path change forced by
hardware availability, not a redefinition of T004 and not permission to fabricate hardware evidence.

The canonical execution-plan recovery for this exact risk (`board/firmware unavailable`) is:

> continue software with fixtures; block wearable evidence

This document records that recovery path being taken.

## 2. What remains true

- `T004` (canonical hardware verification) is **BLOCKED**, not PASS, not SUPERSEDED, not redefined.
- `G1` (Hardware/Data Contract) remains **NOT_STARTED** (not PASS) in `manifests/gate_registry_v1.csv`.
- `F02` (hardware/data contract freeze) remains **NOT_FROZEN** in `manifests/freeze_registry_v1.csv`.
- Every item in the `contracts/HARDWARE_DATA_CONTRACT_V1.md` §7 verification-required registry
  (ESP32 variant, ADC resolution, ADC attenuation/reference, AD8232 gain/filtering, electrode
  placement, MAX30102 register configuration, achieved ECG/PPG sample rates, timer jitter,
  timestamp origin, transport packet format, CRC/checksum behavior, BPM/SpO2 derivation,
  firmware/algorithm versions, raw-count scaling) remains `VERIFICATION_REQUIRED`. None of these
  facts is inferred from source code alone; all require bench measurement.
- `G16` (Wearable Validation, real hardware) remains **NOT_STARTED**; it is explicitly blocked by
  this deferral, not silently skipped.
- `WEARABLE_V1` (v2.2's real synchronized wearable domain-validation dataset) remains reserved for
  future physical hardware sessions. Nothing in this task substitutes for it.

## 3. What is unblocked

The execution plan's own recovery text draws a line between hardware evidence (blocked) and
software work that does not require physical hardware (not blocked). Concretely:

- T005 (`Fixture vertical slice 0`) and the hardware-independent software track may proceed.
- The prerequisite chain `T005: T003` does not include T004, so T005 is not structurally blocked by
  this deferral.
- Software development, streaming-pipeline testing, causal preprocessing tests, gap handling,
  quality-state logic, synchronization, multimodal context, alert state-machine, gateway replay, API
  testing, dashboard testing, fault injection, transport simulation, and reproducible demonstrations
  may all proceed using deterministic fixtures and the new `WEARABLE_SIM_V1` engineering contract
  (`contracts/WEARABLE_SIM_V1.md`) instead of real hardware.
- The primary supervised-learning and federated-learning science tracks were never dependent on this
  hardware; see Section 5.

## 4. Hardware-dependent claims blocked

```text
G1 hardware verification
real WEARABLE_V1 evidence
G16 wearable validation
physical timing/jitter evidence
real ADC scaling evidence
```

No report, contract, or code produced under this deferral may claim any of the above as resolved.

## 5. Scientific grounding preserved

`WEARABLE_SIM_V1` (Section 6 below and `contracts/WEARABLE_SIM_V1.md`) is a software-engineering
simulation aid. It does not and cannot substitute for real data in the project's primary scientific
claims:

- **MODEL_V1** (the primary supervised ECG classifier) remains trained, validated, calibrated,
  internally tested, and externally evaluated exclusively on the locked real public ECG pathway:
  MIT-BIH (patient split → training → validation → calibration → internal test) and INCART
  (external evaluation). Synthetic wearable physiology never replaces this evidence.
- **Federated learning**'s primary efficacy experiment uses exactly the locked eight simulated
  research sites built from whole real MIT-BIH training patients. Synthetic wearable virtual
  patients are never substituted into that experiment; if used at all, it is only for system
  infrastructure/load-test demonstrations, explicitly labeled as engineering evidence and never
  reported as an efficacy result.

## 6. WEARABLE_SIM_V1 — one-paragraph summary

`WEARABLE_SIM_V1` is a new engineering/simulation identifier, fully specified in
`contracts/WEARABLE_SIM_V1.md` and `configs/simulation/WEARABLE_SIM_V1.yaml`. It exists so the
software stack — streaming ingestion, causal preprocessing, quality logic, alert state machine,
gateway, API, and dashboard — can be developed and tested end-to-end without physical hardware. It
is not a clinical dataset, is never presented as real wearable validation, and is architecturally
required to keep an internal "simulation truth" channel that production code never consumes. It is
distinct from and does not replace `WEARABLE_V1`, which stays reserved for real hardware sessions
once T004's canonical bench verification actually happens.

## 7. Resume condition

```text
resume_condition: Physical ESP32/AD8232/MAX30102 system available for bench testing
```

When hardware becomes available, T004's canonical objective is executed as originally specified:
bench measurement of every `VERIFICATION_REQUIRED` item, 10-minute trace capture, rate/jitter/CRC/
sequence tests, and a versioned `contracts/HARDWARE_DATA_CONTRACT_V1.md` update with
`status: FROZEN` only once every required field has evidence or an explicit unavailable-status
limitation. Only then may `G1` and `F02` move to PASS/FROZEN.

## 8. CI policy during this deferral

Automatic GitHub Actions (push/pull_request triggers) were intentionally disabled from T004 through
T032; `.github/workflows/t001.yml` triggered only on `workflow_dispatch` during that range. Local
Python 3.11 validation (`make phase4` and successors) was mandatory for every task in that range.

Automatic CI was restored at T033: `.github/workflows/t001.yml` now also triggers on `push` and
`pull_request`, adding two jobs (`t033-backend`, `t033-frontend`) scoped to git-tracked
checkpoints/artifacts/manifests only -- neither job acquires a raw PhysioNet dataset. End-to-end CI
lands at T034, clean-environment reproducibility CI at T035, and final release CI at T036. This is
an engineering-process decision, not a scientific one, and does not require Class C change control;
see `docs/CHANGE_CONTROL.md` Class B.
