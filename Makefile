PYTHON ?= .venv/bin/python
PYTHONPATH := src

.PHONY: lint test snapshot smoke evidence phase1 registries coverage t002-evidence phase2 contracts t003-evidence phase3 t004-deferral t004-evidence phase4

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src tests scripts

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
