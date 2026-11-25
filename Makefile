PY ?= python

film:
	$(PY) -m pipeline film

film-gpu:
	$(PY) -m pipeline film --gpu

test:
	$(PY) -m pytest -q

.PHONY: film film-gpu test
