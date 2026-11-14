.PHONY: install lint format test dbt dbt-fixture check collect

install:
	uv sync && uv run pre-commit install

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src

format:
	uv run ruff check --fix . && uv run ruff format .

test:
	uv run pytest

# Build and test the dbt models on everything collected in ./data/bronze
dbt:
	cd dbt && uv run dbt build

# Same, on the small committed fixture (what CI runs)
dbt-fixture:
	cd dbt && ZTM_BRONZE_ROOT=../tests/fixtures/bronze ZTM_DUCKDB_PATH=fixture.duckdb uv run dbt build

check: lint test dbt-fixture

# Poll buses and trams every 30 seconds into ./data/bronze
collect:
	uv run ztm-ingest --type 1 2 --interval 30
