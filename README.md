# Warsaw Transport Lakehouse

Real-time ingestion and analytics of Warsaw public transport (ZTM) open data on
Azure + Databricks + dbt.

> Status: Phase 1, ingestion. See [the project plan](docs/PLAN.md) and `docs/adr/` for design decisions.

## Architecture (target)

```
Warsaw Open Data API
      |
ztm-ingest (Python, timer-triggered)
      |
ADLS Gen2  bronze  (immutable raw JSON, Hive-partitioned)
      |  Databricks Auto Loader
Delta silver  (typed, UTC, deduplicated, quality-checked)
      |  dbt
Delta gold  (speed, bunching, punctuality marts)
      |
Power BI
```

## Quick start

```bash
make install                 # venv, dependencies, pre-commit hooks
cp .env.example .env         # then put your API key in .env
ztm-ingest --type 1 --once   # one poll of buses -> data/bronze/...
make collect                 # continuous: buses + trams every 30 s
make check                   # lint + types + tests
```

## Principles

- Config only via environment variables; secrets never in code, logs or git.
- Bronze is append-only and replayable; all cleaning happens downstream.
- Everything is tested, linted, typed, and checked in CI on every PR.
- Infrastructure will be Terraform so the whole project can be rebuilt after the
  Azure student credit ends.
