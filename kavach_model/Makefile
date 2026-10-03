PYTHON ?= .venv/bin/python

.PHONY: setup fetch enrich audit features train evaluate predict test
setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install --no-cache-dir -r $(if $(wildcard requirements.lock.txt),requirements.lock.txt,requirements.txt)
fetch:
	$(PYTHON) -m rice_model.fetch
enrich:
	$(PYTHON) -m rice_model.enrich
audit:
	$(PYTHON) -m rice_model.audit
features:
	$(PYTHON) -m rice_model.features
train: features
	OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 $(PYTHON) -m rice_model.train
evaluate:
	$(PYTHON) -m rice_model.audit
	OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 $(PYTHON) -m rice_model.evaluate
predict:
	$(PYTHON) -m rice_model.inference --district "South 24 Parganas" --season Winter --cutoff-date 2022-07-31
test:
	$(PYTHON) -m pytest -q
