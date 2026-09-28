# Hardware/Data Contract V1

## 1. Contract identity

```text
contract_id: HARDWARE_DATA_CONTRACT_V1
spec_version: 2.2
status: DRAFT_FOR_G1_VERIFICATION
```

This contract is a versioned interface skeleton established at T003. It is **not** fully frozen.
T004 performs bench hardware verification and closes G1; only then may `status` become `FROZEN`.
`manifests/freeze_registry_v1.csv` row `F02` remains `NOT_FROZEN` until that happens.

This document distinguishes three states of knowledge and never collapses one into another:

| State | Meaning |
|---|---|
| `LOCKED_BY_SPEC` | A methodological/project decision fixed by v2.2 (e.g. canonical target sampling rates, quality-state names). |
| `OBSERVED` | A fact directly seen in current system output whose meaning is not yet verified (e.g. the shape of a Mongo document). |
| `VERIFICATION_REQUIRED` | A physical/device fact with no evidence yet (e.g. actual ADC resolution). |

In particular: an intended **250 Hz project sampling target** (`LOCKED_BY_SPEC`) is never read as a
claim that current hardware has been measured at 250 Hz (`VERIFICATION_REQUIRED` until T004).

## 2. Sensor roles

### AD8232 — analog single-channel ECG front end

```text
role: analog single-channel ECG front end
pipeline: ECG -> ESP32 acquisition -> raw ADC counts
canonical project sampling target: 250 Hz              [LOCKED_BY_SPEC]
```

Physical details (gain, analog filtering, electrode placement) are `VERIFICATION_REQUIRED`; see the
registry in Section 9.

### MAX30102 — red/IR PPG sensing

```text
role: red/IR PPG sensing
canonical target: 100 Hz red + IR                       [LOCKED_BY_SPEC]
```

Register configuration and other physical details are `VERIFICATION_REQUIRED`.

### SpO2

A derived scalar. Never laboratory ground truth. Carries:

```text
spo2_pct
spo2_valid
algorithm_version / provenance                          [VERIFICATION_REQUIRED]
```

### Heart rate

ECG-derived heart rate and PPG-derived pulse rate are kept separate and are never silently
collapsed when they disagree:

```text
hr_ecg_bpm
pr_ppg_bpm
```

### ESP32

```text
canonical responsibility: acquisition, monotonic timestamps, sample indexing,
                           packet sequencing, transport
```

Gateway timestamps are receive-time metadata only and must not replace acquisition timestamps.

## 3. Timestamp contract

Two distinct time concepts, never conflated:

### Device/session time — `timestamp_us`

```text
type: int64
meaning: microseconds since device session start
used for: ordering, synchronization, window boundaries, gap detection, runtime inference timing
```

### Wall clock — `start_utc`

Optional session metadata only. Must not be required for within-session alignment.

### `sample_index`

Monotonically increasing source sample index. Future packet/gap logic (`GAP_POLICY_V1`) uses
`sample_index` and timestamp discontinuities together. `GAP_POLICY_V1` is **not implemented** at
T003 — this contract only reserves the identifier and defers actual gap-fill/mask processing to the
preprocessing task.

## 4. Session manifest contract

Canonical session-level fields (v2.2):

```text
participant_id       pseudonymous; demographics must never be inferred from it
session_id           uniquely identifies one acquisition session
device_id            pseudonymous hardware identity
firmware_version
sensor_config_hash   identifies frozen hardware/register/ADC configuration once known;
                      for current hardware this remains unavailable until T004 and must
                      never be fabricated from guessed hardware constants
start_utc
activity              one of: rest_seated, standing, walking, small_motion, unknown
dataset_id
contract_version
```

## 5. Canonical sample schema

Implemented as JSON Schema Draft 2020-12 at `contracts/sample_schema_v1.json`. See that file for the
authoritative field list, types, and enums. Summary:

- Raw values (`ecg_raw`, `ppg_red_raw`, `ppg_ir_raw`) are ADC counts, never calibrated physical
  units. `ecg_raw` is not millivolts until a separately versioned calibrated field is introduced.
- Derived values (`spo2_pct`, `hr_ecg_bpm`, `pr_ppg_bpm`) are physiological estimates, never raw
  sensor readings.
- Quality enums: `VALID`, `DEGRADED`, `UNUSABLE` (`SQ01`, Section 8.1 of v2.2). `UNUSABLE`
  suppresses physiological alerting and yields `RECHECK_SENSOR` at the application layer.
- Missing modalities use explicit `null` / validity fields (`ppg_red_raw = null`,
  `ppg_ir_raw = null`, `spo2_pct = null`, `spo2_valid = false`), never magic numeric sentinels.
  Values such as `0`, `1024`, `2048`, or `-1` are never interpreted as "missing" unless a future
  verified firmware contract explicitly defines such a sentinel.

## 6. Observed MongoDB V0 compatibility

The current MongoDB output does **not** satisfy the canonical V1 contract. This section makes the
gap explicit for T004; it does not implement any translation.

Observed document (see `docs/OBSERVED_MONGODB_SCHEMA_V0.md`):

```javascript
{
  _id: ObjectId(...),
  bpm: NumberInt(...),
  spo2: NumberInt(...),
  ecg: NumberInt(...),
  timestamp: ISODate(...)
}
```

| Mongo V0 field | V1 candidate destination | Current status |
|---|---|---|
| `_id` | provenance/source metadata | OBSERVED |
| `ecg` | `ecg_raw` candidate | VERIFICATION_REQUIRED |
| `bpm` | unknown derived/raw value (candidate `hr_ecg_bpm` or `pr_ppg_bpm`) | VERIFICATION_REQUIRED |
| `spo2` | unknown derived/raw value (candidate `spo2_pct`) | VERIFICATION_REQUIRED |
| `timestamp` | gateway/wall/device timestamp — origin unknown | VERIFICATION_REQUIRED |

The current Mongo V0 shape lacks at least the following canonical fields, based on the fixture at
`tests/fixtures/mongodb_observed_v0.json` and `docs/OBSERVED_MONGODB_SCHEMA_V0.md`; no existing
repository code has been found that proves otherwise:

```text
participant_id
session_id
device_id
firmware_version
sample_index
device timestamp_us
PPG red/IR raw channels
quality states (ecg_quality, ppg_quality)
sensor_config_hash
provenance/version identifiers (contract_version, preprocess_version, source)
```

This contract is **not** weakened to match the current `bpm`/`spo2`/`ecg`/`timestamp` shape. The
canonical schema is driven by v2.2 engineering requirements; the current hardware/backend path will
later be adapted or versioned to satisfy it, as evidenced by T004.

## 7. Verification-required registry

Every item below is a physical/device fact with **no measured evidence yet**. Each remains
`VERIFICATION_REQUIRED` until T004 produces bench measurement, firmware/backend inspection, or
explicit unavailable-status evidence. No later task may silently replace an entry's status with a
value other than `VERIFICATION_REQUIRED` without recording that evidence.

| # | Item | Status |
|---|---|---|
| 1 | Exact ESP32 variant | VERIFICATION_REQUIRED |
| 2 | ADC resolution | VERIFICATION_REQUIRED |
| 3 | ADC attenuation/reference voltage | VERIFICATION_REQUIRED |
| 4 | AD8232 actual gain | VERIFICATION_REQUIRED |
| 5 | AD8232 analog filtering | VERIFICATION_REQUIRED |
| 6 | Electrode placement | VERIFICATION_REQUIRED |
| 7 | MAX30102 register configuration | VERIFICATION_REQUIRED |
| 8 | Actual achieved ECG sample rate | VERIFICATION_REQUIRED |
| 9 | Actual achieved PPG sample rate | VERIFICATION_REQUIRED |
| 10 | Timer/sampling jitter | VERIFICATION_REQUIRED |
| 11 | Timestamp producer/origin (device vs. gateway/API vs. MongoDB) | VERIFICATION_REQUIRED |
| 12 | Transport packet format | VERIFICATION_REQUIRED |
| 13 | CRC/checksum behavior | VERIFICATION_REQUIRED |
| 14 | BPM derivation algorithm | VERIFICATION_REQUIRED |
| 15 | SpO2 derivation algorithm | VERIFICATION_REQUIRED |
| 16 | Algorithm/firmware versions | VERIFICATION_REQUIRED |
| 17 | Raw-count-to-physical-unit scaling | VERIFICATION_REQUIRED |

`HW01` (v2.2 Sections 4-5 and 43.1): G1 cannot pass until each row above has bench/firmware/backend
evidence or an explicit unavailable status with a versioned limitation. This contract does not
assert or imply any of these facts.

## 8. Contract identifiers

```text
SPEC_VERSION = 2.2
HARDWARE_DATA_CONTRACT_V1
SAMPLE_SCHEMA_V1
LABEL_SCHEMA_V1
AAMI_SVF_WINDOW_V1
AAMI_SVF_MAP_V1
API_SCHEMA_V1
```

Referenced but not implemented or frozen at T003: `PREPROC_V1`, `MODEL_V1`, `CAL_V1`,
`ALERT_POLICY_V1`, `GAP_POLICY_V1`.
