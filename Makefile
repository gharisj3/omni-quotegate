PYTHON ?= python

.PHONY: setup test lint demo
setup:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

demo:
	$(PYTHON) scripts/demo_quote_flow.py
