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
Requires [uv](https://docs.astral.sh/uv/).


```bash
uv sync                                  # create .venv and install dependencies
uv run pre-commit install                # git hooks: lint + format on every commit
cp .env.example .env                     # then put your API key in .env
uv run ztm-ingest --type 1               # one poll of buses -> data/bronze/...
uv run ztm-ingest --type 1 2 --interval 30   # continuous: buses + trams every 30 s
uv run pytest                            # tests (make check on Mac/Linux: lint + types + tests)
```


## Principles

- Config only via environment variables; secrets never in code, logs or git.
- Bronze is append-only and replayable; all cleaning happens downstream.
- Everything is tested, linted, typed, and checked in CI on every PR.
- Infrastructure will be Terraform so the whole project can be rebuilt after the
  Azure student credit ends.

## Data sources

**Vehicle positions:** Miasto Stołeczne Warszawa, via the Warsaw open data portal
([dane.um.warszawa.pl](https://dane.um.warszawa.pl/en)). Downloaded continuously since
November 2026; the download time of every file is recorded in its `_meta.received_at_utc`.

**Timetable (GTFS):**
- Data provided by: Zarząd Transportu Miejskiego w Warszawie ([ztm.waw.pl](https://ztm.waw.pl))
- GTFS provided by: Mikołaj Kuranowski ([mkuran.pl/gtfs](https://mkuran.pl/gtfs/))
- Bus shapes based on data from: © OpenStreetMap contributors, under the
  [ODbL license](https://www.openstreetmap.org/copyright)

Raw downloads are stored unmodified in bronze; all derived tables are this project's own processing.
