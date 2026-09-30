PYTHON ?= .venv/bin/python
PYTHONPATH := src:.

.PHONY: lint test snapshot smoke evidence phase1 registries coverage t002-evidence phase2 contracts t003-evidence phase3 t004-deferral t004-evidence phase4 fixture-t005 t005-smoke t005-evidence phase5 acquire-mitdb validate-mitdb t006-evidence phase6 acquire-incart acquire-nstdb acquire-bidmc validate-incart validate-nstdb validate-bidmc dataset-role-audit t007-evidence phase7 annotation-census t008-evidence phase8 mitdb-split t009-evidence phase9 leakage-audit t010-evidence phase10 resampler-coefficients resampler-causality t011-evidence phase11 filter-coefficients filter-causality gap-policy-tests t012-evidence phase12 window-tests quality-tests sync-tests build-mitdb-windows real-window-audit preproc-freeze-audit t013-evidence phase13 baseline-features baseline-train baseline-audit baseline-freeze-audit t014-evidence phase14 model-v1-tests model-v1-train model-v1-audit model-v1-candidates t015-evidence phase15 model-v1-freeze model-v1-vector model-v1-verify t016-evidence phase16 calibration-tests fit-cal-v1 verify-cal-v1 calibration-reproducibility t017-evidence phase17 t018-preflight internal-test-once internal-test-verify t018-evidence phase18 nstdb-protocol nstdb-robustness nstdb-verify t019-evidence phase19 t020-preflight external-incart-once external-incart-verify t020-evidence phase20 bidmc-context-protocol bidmc-context-tests bidmc-context-run bidmc-context-verify t021-evidence phase21 ecg-hr-v2-tests ecg-hr-v2-train-audit ecg-hr-v2-validation ecg-hr-v2-freeze c021-hr-a-evidence c021-hr-a alert-policy-tests alert-policy-verify t022-evidence phase22 bidmc-context-v2-tests bidmc-context-v2-run bidmc-context-v2-verify c021-hr-b-evidence c021-hr-b t023-preflight t023-bidmc t023-wearable-sim t023-verify t023-evidence phase23 fl-toy-tests flower-smoke fl-model-adapter-audit t024-evidence t024-verify phase24

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src tests scripts simulation deployment fusion api datasets features models training evaluation preprocessing

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest

snapshot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/snapshot_dependencies.py

smoke: snapshot
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/smoke_t001.py

evidence: smoke
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t001_evidence.py

phase1: lint test evidence

registries:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_t002_registries.py

coverage: registries
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_coverage_t002.py --first-pass-unmapped-count 0 --manual-review-completed

t002-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t002_evidence.py

phase2:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) evidence PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)

contracts:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_contracts_t003.py

t003-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t003_evidence.py

phase3:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)

t004-deferral:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_t004_deferral.py

t004-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t004_evidence.py

phase4:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)

fixture-t005:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t005_fixture.py

t005-smoke: fixture-t005
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/smoke_t005.py

t005-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t005_evidence.py

phase5:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)

# Network allowed; downloads/verifies the exact PhysioNet MIT-BIH v1.0.0 release into
# data/raw/mitdb/1.0.0/. Idempotent -- an already-verified local copy is not redownloaded.
acquire-mitdb:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/acquire_mitdb.py

# Offline. Requires local raw data already acquired via `make acquire-mitdb`.
validate-mitdb:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_mitdb_t006.py

t006-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t006_evidence.py

# phase6 does not invoke acquire-mitdb: normal local validation must not redownload the
# dataset on every run. Run `make acquire-mitdb` once (or after a verified-copy repair)
# before `make phase6`.
phase6:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)

# Network allowed; downloads/verifies the exact PhysioNet releases into
# data/raw/{incartdb,nstdb,bidmc}/1.0.0/. Idempotent. INCART is a large acquisition (~830 MB).
acquire-incart:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/acquire_incart.py

acquire-nstdb:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/acquire_nstdb.py

acquire-bidmc:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/acquire_bidmc.py

# Offline. Each requires its local raw data already acquired.
validate-incart:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_incart_t007.py

validate-nstdb:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_nstdb_t007.py

validate-bidmc:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_bidmc_t007.py

dataset-role-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_dataset_roles_t007.py

t007-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t007_evidence.py

# phase7 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets once before `make phase7`.
phase7:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)

# Offline. Requires the already-acquired/hash-verified local MITDB (T006) and INCART (T007)
# raw data; no download, no window-building, no split, no preprocessing.
annotation-census:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_annotation_census_t008.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_label_map_t008.py

t008-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t008_evidence.py

# phase8 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets (phase6/phase7) once before `make phase8`.
phase8:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)
	$(MAKE) annotation-census PYTHON=$(PYTHON)
	$(MAKE) t008-evidence PYTHON=$(PYTHON)

# Offline. Requires the already-acquired/hash-verified local MITDB (T006) raw data and the
# frozen AAMI_SVF_MAP_V1 mapper (T008/G4/F04); no download, no window-building, no
# preprocessing, no model training. Does not close G5/F05 -- that is T010's job.
mitdb-split:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_mitdb_split_t009.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_split_independence_t009.py

t009-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t009_evidence.py

# phase9 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets (phase6/phase7) once before `make phase9`.
phase9:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)
	$(MAKE) annotation-census PYTHON=$(PYTHON)
	$(MAKE) t008-evidence PYTHON=$(PYTHON)
	$(MAKE) mitdb-split PYTHON=$(PYTHON)
	$(MAKE) t009-evidence PYTHON=$(PYTHON)

# Offline. Independently recomputes G5 invariants from T006/T008/T009 artifacts (never trusts
# T009's own report), runs the synthetic window-leakage harness, and -- only if both pass --
# writes the MITDB_SPLIT_V1 freeze lock and verifies it. Never regenerates the candidate split.
leakage-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_split_leakage_t010.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_window_leakage_harness_t010.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_leakage_control_matrix_t010.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_mitdb_split_t010.py

t010-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t010_evidence.py

# phase10 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets (phase6/phase7) once before `make phase10`.
phase10:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)
	$(MAKE) annotation-census PYTHON=$(PYTHON)
	$(MAKE) t008-evidence PYTHON=$(PYTHON)
	$(MAKE) mitdb-split PYTHON=$(PYTHON)
	$(MAKE) t009-evidence PYTHON=$(PYTHON)
	$(MAKE) leakage-audit PYTHON=$(PYTHON)
	$(MAKE) t010-evidence PYTHON=$(PYTHON)

# Offline. Deterministically (re)generates the committed PREPROC_V1_RESAMPLER_V1 FIR
# coefficient package -- never redesigned at runtime, only regenerated here for provenance.
resampler-coefficients:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/design_resampler_t011.py

# Offline, synthetic signals only. Verifies F05 before/after, runs future-append/chunk-
# equivalence/direct-reference/impulse/clock/memory-bound proofs, and the forbidden-API audit.
resampler-causality:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_resampler_causality_t011.py

t011-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t011_evidence.py

# phase11 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets (phase6/phase7) once before `make phase11`.
phase11:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)
	$(MAKE) annotation-census PYTHON=$(PYTHON)
	$(MAKE) t008-evidence PYTHON=$(PYTHON)
	$(MAKE) mitdb-split PYTHON=$(PYTHON)
	$(MAKE) t009-evidence PYTHON=$(PYTHON)
	$(MAKE) leakage-audit PYTHON=$(PYTHON)
	$(MAKE) t010-evidence PYTHON=$(PYTHON)
	$(MAKE) resampler-coefficients PYTHON=$(PYTHON)
	$(MAKE) resampler-causality PYTHON=$(PYTHON)
	$(MAKE) t011-evidence PYTHON=$(PYTHON)

# Offline. Deterministically (re)generates the committed ECG/PPG causal SOS filter packages.
filter-coefficients:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/design_filters_t012.py

# Offline, synthetic signals only. Verifies F05 before/after; future-append/chunk-equivalence/
# impulse-causality/one-shot-reference/reset/pole-stability/forbidden-API proofs.
filter-causality:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_filter_causality_t012.py

# Offline, synthetic/known-rate source-index arithmetic only (software policy, not real
# hardware evidence). Boundary/short-gap-ZOH/long-gap-reset/future-append/determinism proofs.
gap-policy-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_gap_policy_tests_t012.py

t012-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t012_evidence.py

# phase12 does not invoke any acquire-* target: normal local validation must not redownload
# datasets on every run. Run the acquire-* targets (phase6/phase7) once before `make phase12`.
phase12:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) t002-evidence PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t003-evidence PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) t004-evidence PYTHON=$(PYTHON)
	$(MAKE) t005-smoke PYTHON=$(PYTHON)
	$(MAKE) t005-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) t006-evidence PYTHON=$(PYTHON)
	$(MAKE) validate-incart PYTHON=$(PYTHON)
	$(MAKE) validate-nstdb PYTHON=$(PYTHON)
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) dataset-role-audit PYTHON=$(PYTHON)
	$(MAKE) t007-evidence PYTHON=$(PYTHON)
	$(MAKE) annotation-census PYTHON=$(PYTHON)
	$(MAKE) t008-evidence PYTHON=$(PYTHON)
	$(MAKE) mitdb-split PYTHON=$(PYTHON)
	$(MAKE) t009-evidence PYTHON=$(PYTHON)
	$(MAKE) leakage-audit PYTHON=$(PYTHON)
	$(MAKE) t010-evidence PYTHON=$(PYTHON)
	$(MAKE) resampler-coefficients PYTHON=$(PYTHON)
	$(MAKE) resampler-causality PYTHON=$(PYTHON)
	$(MAKE) t011-evidence PYTHON=$(PYTHON)
	$(MAKE) filter-coefficients PYTHON=$(PYTHON)
	$(MAKE) filter-causality PYTHON=$(PYTHON)
	$(MAKE) gap-policy-tests PYTHON=$(PYTHON)
	$(MAKE) t012-evidence PYTHON=$(PYTHON)

# T013: these fixture reports are offline and do not rewrite historical T011/T012 evidence.
window-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_window_tests_t013.py

quality-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_quality_tests_t013.py

sync-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_sync_tests_t013.py

build-mitdb-windows:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_mitdb_windows_t013.py

# The partition-first builder writes and validates the real leakage audit as one transaction.
real-window-audit: build-mitdb-windows
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "import json; from pathlib import Path; p=Path('reports/t013/real_window_audit.json'); assert json.loads(p.read_text())['overall_status']=='PASS'"

preproc-freeze-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_preproc_t013.py

t013-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t013_evidence.py

# Complete local Python 3.11 T013 gate. No dataset download and no remote CI.
phase13:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	$(MAKE) window-tests PYTHON=$(PYTHON)
	$(MAKE) quality-tests PYTHON=$(PYTHON)
	$(MAKE) sync-tests PYTHON=$(PYTHON)
	$(MAKE) real-window-audit PYTHON=$(PYTHON)
	$(MAKE) preproc-freeze-audit PYTHON=$(PYTHON)
	$(MAKE) t013-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

# T014: waveform-only classical features; TRAIN fit and VALIDATION descriptive reporting.
baseline-features:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_baseline_features_t014.py

baseline-train:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m training.train_baselines --config configs/baseline_v1.yaml

baseline-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_baseline_reproducibility_t014.py

baseline-freeze-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_baseline_t014.py

t014-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t014_evidence.py

# Complete local Python 3.11 T014 gate. No dataset download, held-out waveform access, or CI.
phase14:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'"
	$(MAKE) baseline-train PYTHON=$(PYTHON)
	$(MAKE) baseline-audit PYTHON=$(PYTHON)
	$(MAKE) baseline-freeze-audit PYTHON=$(PYTHON)
	$(MAKE) t014-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

# T015 real training command. It executes exactly the fixed primary + two robustness seeds.
model-v1-train:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m training.train_central

model-v1-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_model_v1_architecture.py tests/test_model_v1_loss.py tests/test_model_v1_data_scope.py tests/test_model_v1_training.py tests/test_model_v1_seed_policy.py

model-v1-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/audit_model_v1_t015.py

# Verifies the already-completed real candidates without repeating the costly scientific run.
model-v1-candidates:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_model_v1_candidates_t015.py

t015-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t015_evidence.py

# Complete local Python 3.11 T015 gate. Candidate training is run once via model-v1-train;
# subsequent phase validation verifies its exact hashes and reload behavior without retraining.
phase15:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	$(MAKE) validate-mitdb PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'"
	$(MAKE) model-v1-tests PYTHON=$(PYTHON)
	$(MAKE) model-v1-audit PYTHON=$(PYTHON)
	$(MAKE) model-v1-candidates PYTHON=$(PYTHON)
	$(MAKE) t015-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

model-v1-freeze:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_model_v1_t016.py

model-v1-vector:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_model_v1_test_vector_t016.py --output tests/fixtures/model_v1_test_vector.npz

model-v1-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from models.model_freeze import verify_frozen_model_v1; assert verify_frozen_model_v1(Path('.'))['status']=='PASS'"
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from models.model_freeze import verify_frozen_model_v1; assert verify_frozen_model_v1(Path('.'))['status']=='PASS'"

t016-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t016_evidence.py

# Complete local Python 3.11 T016 gate. This target never invokes MODEL_V1 training.
phase16:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'"
	$(MAKE) model-v1-candidates PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_model_v1_freeze.py tests/test_model_v1_test_vector.py
	$(MAKE) model-v1-verify PYTHON=$(PYTHON)
	$(MAKE) t016-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

calibration-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_calibration_v1.py tests/test_calibration_scope.py tests/test_calibration_freeze.py

fit-cal-v1:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.calibration --fit-cal-v1

verify-cal-v1:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.calibration import verify_cal_v1; assert verify_cal_v1(Path('.'))['status']=='PASS'"

calibration-reproducibility:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_calibration_reproducibility_t017.py

t017-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t017_evidence.py

# Complete local Python 3.11 T017 gate. G10 remains open and INTERNAL_TEST stays sealed.
phase17:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; from models.model_freeze import verify_frozen_model_v1; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'"
	$(MAKE) calibration-tests PYTHON=$(PYTHON)
	$(MAKE) fit-cal-v1 PYTHON=$(PYTHON)
	$(MAKE) calibration-reproducibility PYTHON=$(PYTHON)
	$(MAKE) verify-cal-v1 PYTHON=$(PYTHON)
	$(MAKE) t017-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

t018-preflight:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; r=Path('.'); assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'"
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_internal_metrics.py tests/test_patient_cluster_bootstrap.py tests/test_internal_test_scope.py tests/test_internal_test_one_shot.py
	$(PYTHON) -m pip check

internal-test-once:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.internal_test --run-once

internal-test-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.internal_test --verify

t018-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t018_evidence.py

# Verification-only after the one-shot result exists; never invokes INTERNAL_TEST inference.
phase18:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'"
	$(MAKE) internal-test-verify PYTHON=$(PYTHON)
	$(MAKE) t018-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

nstdb-protocol:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.noise import verify_official_sources; assert verify_official_sources(Path('.'))['provider_hashes']=='PASS'"
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_nstdb_noise_protocol.py tests/test_nstdb_pairing.py tests/test_nstdb_scope.py

nstdb-robustness:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.noise --run

nstdb-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_noise_robustness_t019.py

t019-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t019_evidence.py

# Verification-only after the real NSTDB robustness results have been generated.
phase19:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; from evaluation.internal_test import verify_internal_test_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'; assert verify_internal_test_freeze(r)['status']=='PASS'"
	$(MAKE) nstdb-protocol PYTHON=$(PYTHON)
	$(MAKE) nstdb-verify PYTHON=$(PYTHON)
	$(MAKE) t019-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

t020-preflight:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from preprocessing.freeze import verify_preproc_freeze; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; from evaluation.internal_test import verify_internal_test_freeze; from evaluation.external_incart import verify_source_contract, validate_method_config; r=Path('.'); assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'; assert verify_internal_test_freeze(r)['status']=='PASS'; assert verify_source_contract(r)['status']=='PASS'; validate_method_config(r)"
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_external_incart_protocol.py tests/test_external_incart_patient_groups.py tests/test_external_incart_scope.py tests/test_external_incart_one_shot.py tests/test_patient_cluster_bootstrap.py
	$(PYTHON) -m pip check

external-incart-once:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.external_incart --run-once

external-incart-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.external_incart --verify

t020-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t020_evidence.py

# Verification-only after the one-shot INCART result exists; never invokes model inference.
phase20:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; from evaluation.internal_test import verify_internal_test_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'; assert verify_internal_test_freeze(r)['status']=='PASS'"
	$(MAKE) external-incart-verify PYTHON=$(PYTHON)
	$(MAKE) t020-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

bidmc-context-protocol:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/design_bidmc_context_resamplers_t021.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from evaluation.bidmc_context import validate_config, verify_bidmc_source; assert validate_config()['context_contract_id']=='BIDMC_CONTEXT_V1'; assert verify_bidmc_source()['status']=='PASS'"

bidmc-context-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_bidmc_context_alignment.py tests/test_bidmc_context_resampling.py tests/test_bidmc_rate_estimators.py tests/test_bidmc_context_quality.py tests/test_bidmc_context_scope.py tests/test_bidmc_context_results.py

bidmc-context-run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.bidmc_context --run

bidmc-context-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.bidmc_context --verify

t021-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t021_evidence.py

phase21:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) coverage PYTHON=$(PYTHON)
	$(MAKE) contracts PYTHON=$(PYTHON)
	$(MAKE) t004-deferral PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from pathlib import Path; from evaluation.leakage_audit import verify_frozen_split; from preprocessing.freeze import verify_preproc_freeze; from models.baseline_freeze import verify_baseline_freeze; from models.model_freeze import verify_frozen_model_v1; from evaluation.calibration import verify_cal_v1; from evaluation.internal_test import verify_internal_test_freeze; from evaluation.external_incart import verify_external_freeze; r=Path('.'); assert verify_frozen_split(r)['status']=='PASS'; assert verify_preproc_freeze(r)['status']=='PASS'; assert verify_baseline_freeze(r)['status']=='PASS'; assert verify_frozen_model_v1(r)['status']=='PASS'; assert verify_cal_v1(r)['status']=='PASS'; assert verify_internal_test_freeze(r)['status']=='PASS'; assert verify_external_freeze(r)['status']=='PASS'"
	$(MAKE) validate-bidmc PYTHON=$(PYTHON)
	$(MAKE) bidmc-context-tests PYTHON=$(PYTHON)
	$(MAKE) bidmc-context-verify PYTHON=$(PYTHON)
	$(MAKE) t021-evidence PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

ecg-hr-v2-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_ecg_hr_context_v2.py tests/test_ecg_hr_reference_v2.py tests/test_ecg_hr_selection_v2.py tests/test_ecg_hr_scope_v2.py

ecg-hr-v2-train-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.ecg_hr_v2 --partition TRAIN --output reports/c021_hr_a

ecg-hr-v2-validation:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.ecg_hr_v2 --partition VALIDATION --output reports/c021_hr_a

ecg-hr-v2-freeze:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_ecg_hr_v2_c021.py

c021-hr-a-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_c021_hr_a_evidence.py

# Verification-only after ECG_HR_CONTEXT_V2 is frozen; never accesses raw validation ECG.
c021-hr-a:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_c021_hr_a.py
	$(PYTHON) -m pip check

alert-policy-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_state_machine_t005.py tests/test_fusion_state_machine_v1.py tests/test_alert_episode_manager_v1.py tests/test_alert_policy_context_v1.py tests/test_alert_policy_scope_v1.py tests/test_alert_policy_freeze_v1.py

alert-policy-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_t022.py

t022-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t022_evidence.py

phase22:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_t022.py
	$(PYTHON) -m pip check

bidmc-context-v2-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_bidmc_context_v2.py tests/test_bidmc_hr_v2_scope.py tests/test_bidmc_context_v2_freeze.py

bidmc-context-v2-run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.bidmc_context_v2 --run

bidmc-context-v2-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_c021_hr_b.py

c021-hr-b-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_c021_hr_b_evidence.py

# Verification-only after BIDMC_CONTEXT_V2 is frozen; never reads raw BIDMC.
c021-hr-b:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) bidmc-context-v2-verify PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

t023-preflight:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/freeze_t023_method.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_t023_monitor_arms.py tests/test_t023_perturbations.py tests/test_t023_episode_metrics.py tests/test_t023_scope.py

# The frozen runner executes both data arms once and emits separately scoped outputs.
t023-bidmc t023-wearable-sim:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m evaluation.quality_aware_alerts --run

t023-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_t023.py

t023-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t023_evidence.py

phase23:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) t023-verify PYTHON=$(PYTHON)
	$(PYTHON) -m pip check

fl-toy-tests:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_fl_aggregation_t024.py tests/test_fl_state_transport_t024.py tests/test_fl_scope_t024.py

flower-smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_flower_scaffold_t024.py

fl-model-adapter-audit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/test_model_fl_adapter_t024.py

t024-evidence:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_t024_evidence.py

t024-verify:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify_t024.py

phase24:
	$(MAKE) lint PYTHON=$(PYTHON)
	$(MAKE) test PYTHON=$(PYTHON)
	$(MAKE) t023-verify PYTHON=$(PYTHON)
	$(MAKE) fl-toy-tests PYTHON=$(PYTHON)
	$(MAKE) flower-smoke PYTHON=$(PYTHON)
	$(MAKE) fl-model-adapter-audit PYTHON=$(PYTHON)
	$(MAKE) t024-evidence PYTHON=$(PYTHON)
	$(MAKE) t024-verify PYTHON=$(PYTHON)
	$(PYTHON) -m pip check
