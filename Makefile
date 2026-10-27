# Thin wrappers around scripts that can also be run directly.

PYTHON ?= python3

.PHONY: help data build story pages paper test lint serve ontology

help:
	@echo "make data   - download the public OSHA and EPA files into data/raw"
	@echo "make build  - link sources, write outputs/summary.json and docs/data/*.json"
	@echo "make pages  - rebuild the story page and re-apply the shared header"
	@echo "make paper  - regenerate the tables in docs/paper.md from outputs/summary.json"
	@echo "make test   - run the tests (real-data tests skip if data/raw is empty)"
	@echo "make serve  - serve docs/ on http://localhost:8000"
	@echo "make ontology - build the ontology from the committed data, export to build/ontology"

data:
	$(PYTHON) scripts/download_data.py

build:
	$(PYTHON) scripts/build_data.py

pages:
	$(PYTHON) scripts/build_story.py
	$(PYTHON) scripts/apply_header.py docs/index.html docs/method.html

paper:
	$(PYTHON) scripts/paper_tables.py

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

lint:
	ruff check .

serve:
	cd docs && $(PYTHON) -m http.server 8000

ontology:
	PYTHONPATH=src $(PYTHON) -m chempeers.ontology --out build/ontology
