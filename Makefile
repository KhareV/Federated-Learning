PYTHON ?= .venv/bin/python
PYTHONPATH := src

.PHONY: lint test snapshot smoke evidence phase1 registries coverage t002-evidence phase2

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
