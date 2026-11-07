.PHONY: install lint format test check collect

install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pre-commit install

lint:
	ruff check . && ruff format --check . && mypy src

format:
	ruff check --fix . && ruff format .

test:
	pytest

check: lint test

# Poll buses and trams every 30 seconds into ./data/bronze
collect:
	ztm-ingest --type 1 2 --interval 30
