# Live per-round evaluation: diagnostic-cohort policy

**Label shown with every live metric (verbatim):** `REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST`.

## Cohort
The observer scores each committed global state on the **frozen NHM_FL10_001 holdout** (`WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1`: 16 synthetic participants, 1 446 windows, two profiles for each of the eight site conditions). That cohort was examined by NHM_FL10_001, so it is *no longer untouched*; the earlier 8-participant showcase holdout was examined by NHM_FINAL_SHOWCASE_001. Reusing it was chosen over inventing a new cohort so that every checkpoint of every run is scored on the **same** windows (comparable across rounds and runs) without a new scientific campaign.

Because the cohort is reused:
- scores are **diagnostic**: no round, threshold, calibration, or candidate is selected from them (`round_selection = NONE`);
- viewing many runs, or re-running, is not independent statistical confirmation;
- nominal intervals (16 clusters) are descriptive and carry no significance claim;
- the claim boundary is `SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL` (synthetic engineering-event labels, not AAMI-SVF annotations; no clinical claim).

## What is verified before any score exists
Protocol and manifest bytes must equal the method-freeze digests recorded in the immutable `NHM_FL10_001` lock (and, when git is available, the bytes committed at `f91a96a`); every holdout dataset must equal its manifest entry; both classes must exist; **zero participant / session / window-input overlap** with the canonical training cohort and the previously exposed 8-participant holdout (recomputed in-process the first time the observer loads the holdout; before that the FL10 frozen evidence for the same cohort is shown and labelled as such). The committed state's digest is re-verified on the observer's private copy before scoring; a mismatch is a visible `FAILED`, never a score.

## What the observer does and never does
Does: receive an immutable copy of a committed state; score with the unchanged FL10 metric engine at the fixed rule `sigmoid(logit) >= 0.5`; store the full-precision logits (`predictions.csv`), curves, confusion counts, participant metrics and a typed record (`STUDIO_ROUND_EVALUATION_V1`) with run/round/state/cohort/protocol identity; publish it. Never: train, change gradients/optimizer/aggregation, tune the threshold, apply `CAL_V2`, change the deployed monitoring model, choose the next round, or reuse another run's numbers. Pending, undefined and failed values are shown as such (`QUEUED`, `EVALUATING`, `NOT YET AVAILABLE`, `UNDEFINED — reason`, `FAILED — reason`), never as zero.

## Training integrity (found and fixed during this work)
The frozen trainer draws Dropout masks from torch's process-wide RNG. `final_showcase.evaluate.logits_for` builds a *new model* per call, and building a model draws random initial weights from that same RNG, so scoring on another thread silently changed a run's committed state (observed as `PREFIX_PARITY_MISMATCH`, which the FL10 runner correctly fails closed on). `studio/isolated_eval.py` builds one template model before any run exists and only deep-copies it (no random draws). `tests/test_studio_isolation.py` proves training is bit-identical with continuous concurrent scoring, includes a control showing the old evaluator does perturb training, and proves the isolated logits equal the reference logits bit for bit.

## Reproducibility evidence
For the canonical cohort, a **new** run reproduces the recorded FL10 states and metrics exactly (equal committed digests R00–R10 and equal AUPRC/AUROC/F1/BCE/Brier/confusion counts). That equality is a consequence of determinism, measured on the new run; nothing is preloaded. Different source modes or future seeds would legitimately differ.

## Failure and restart semantics
A failed or interrupted evaluation stays `FAILED` with its reason; after a server restart, unfinished rounds are marked `INTERRUPTED_BY_RESTART` and are never re-scored silently. An interrupted 10-round run is never a candidate and restarts from R0 (cooperative cancellation at the next progress event on shutdown).
