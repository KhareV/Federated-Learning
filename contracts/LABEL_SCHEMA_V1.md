# Label Schema V1

## 1. Identity

```text
target_id: AAMI_SVF_WINDOW_V1
mapping_id: AAMI_SVF_MAP_V1
spec_version: 2.2
```

Implementation (the Python mapper) belongs to T008. Census verification belongs to T008. This
document defines the frozen target semantics only.

## 2. Prediction unit

One prediction unit is exactly:

```text
one participant/session
+ one 10-second ECG window
+ prediction timestamp at right edge t
+ quality
+ target/provenance
```

Window interval: `[t - 10 seconds, t]`.

Prediction cadence (later, at runtime): every 5 seconds.

## 3. Target semantics

```text
1 = SVF_CONTAINING_WINDOW
0 = N_ONLY_WINDOW
```

**Positive** (`SVF_CONTAINING_WINDOW`): at least one mapped S/V/F beat and no Q/unknown/unmappable/
paced beat in the window.

**Negative** (`N_ONLY_WINDOW`): all eligible mapped beats are N and no excluded beat exists.

**Excluded** windows (produce no core target label):

```text
Q
unknown
unmappable
paced
fewer than 5 mappable beats
UNUSABLE training window
```

**Runtime UNUSABLE behavior**: `RECHECK_SENSOR`.

## 4. Claim boundary

The target is strictly descriptive of the observed ECG window. It is **not**:

- a future forecast;
- disease probability;
- a conventional beat-classifier output;
- a diagnosis of arrhythmia or heart disease.

Any exposed probability, UI text, or report referencing this target must identify it as an observed-
window research target with a right-edge timestamp, per `R01.2`/`CB01`.

## 5. AAMI_SVF_MAP_V1 — frozen allowlist

```text
N, L, R, e, j -> N
A, a, J, S    -> S
V, E          -> V
F             -> F
/, f, Q       -> Q / excluded
```

Any beat symbol not explicitly allowlisted above is `UNMAPPABLE` and excluded from the core target.

Non-beat markers are `NOT_A_BEAT`: ignored by beat-class target mapping, but may later be used for
quality/provenance signals.

This table is implemented in Python at T008 (`datasets/labels.py`), with unit tests covering every
allowlisted, paced, unknown, unmapped, and non-beat symbol for both MIT-BIH and INCART.

> A mapping change requires a new mapping version and is a scientific/change-control event
> (Class C under `docs/CHANGE_CONTROL.md`), not a local refactor.

## 6. Contract identifiers

```text
LABEL_SCHEMA_V1
AAMI_SVF_WINDOW_V1
AAMI_SVF_MAP_V1
```
