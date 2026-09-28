PYTHON ?= .venv/bin/python
PYTHONPATH := src:.

.PHONY: lint test snapshot smoke evidence phase1 registries coverage t002-evidence phase2 contracts t003-evidence phase3 t004-deferral t004-evidence phase4 fixture-t005 t005-smoke t005-evidence phase5 acquire-mitdb validate-mitdb t006-evidence phase6

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src tests scripts simulation deployment fusion api datasets

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
