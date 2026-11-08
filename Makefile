.PHONY: install lint format test check collect

install:
	uv sync && uv run pre-commit install

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src

format:
	uv run ruff check --fix . && uv run ruff format .

test:
	uv run pytest

check: lint test

# Poll buses and trams every 30 seconds into ./data/bronze
collect:
	uv run ztm-ingest --type 1 2 --interval 30
