# Project plan

Real-time ingestion and analytics of Warsaw public transport (ZTM) open data. Design decisions are recorded in [`docs/adr/`](adr/).

## Goals

- Collect every vehicle position the Warsaw open data API publishes. The API has no history, so anything not stored is lost.
- Turn the raw feed into analytics on speed, bunching and punctuality.
- Build it the way a production data platform is built: tested, typed, CI on every PR, infrastructure as code, secrets never in code.

## Guiding principles

- **Cost first.** The project runs on an Azure for Students subscription (about $100 credit). Nothing runs 24/7 except the cheap ingestion function.
- **Local first.** Get end-to-end results on a laptop for $0 before adding cloud complexity.
- **Small, finishable phases.** Each phase ends with something demo-able and a merged PR.
- **Minimum to finish is Phases 1–7.** Phases 8–9 are bonuses.

## Architecture

```
Warsaw Open Data API (dane.um.warszawa.pl)
      |  ztm-ingest (Python; Azure Functions timer, every 30 s)
ADLS Gen2 bronze   immutable raw JSON, Hive-partitioned
      |  Lakeflow Declarative Pipeline (Auto Loader)
Delta silver       typed, UTC, deduplicated, quality-checked
      |  dbt
Delta gold         speed, bunching, punctuality marts
      |
Power BI
```

---

## Phase 1: Ingestion (local)

Project setup
- [x] Python package `ztm_ingest`, `src/` layout, `pyproject.toml`
- [x] ruff, mypy strict, pytest with coverage, pre-commit, GitHub Actions CI
- [x] uv for environments (`uv sync`, `uv run`) so setup works on Windows, macOS and Linux
- [x] Same ruff version pinned in pre-commit and the dev dependencies

Configuration
- [x] All settings from `ZTM_*` environment variables (pydantic-settings), API key as `SecretStr`
- [ ] Cross-field validation in `Settings` (e.g. the Azure URL is required for the azure backend)

API client
- [x] POST to `dane.um.warszawa.pl` with the key in the `Authorization` header, never in the URL
- [x] Retries with exponential backoff on network errors, 429 and 5xx; no retry on 4xx
- [x] Error messages that redact the key and are truncated; unknown responses reported by shape only

Bronze storage
- [x] One immutable JSON file per poll (`_meta` + untouched `payload`), Hive-partitioned path
- [x] Local writer (atomic rename) and Azure Blob writer (`DefaultAzureCredential`)
- [x] `_meta.source` taken from the configured API URL
- [ ] `requested_at_utc` and `received_at_utc` in `_meta`; partition by received time
- [ ] Azure writer unit test with a mocked container client

Collector
- [x] `ztm-ingest` CLI: one-shot or interval polling, graceful shutdown on SIGINT/SIGTERM
- [ ] A single failed poll (API or storage) is logged and never stops the loop; `--type` limited to 1 and 2
- [x] Structured JSON logs including `vehicle_type`, `records`, `location`
- [ ] Tests isolated from the developer's `.env`

Data
- [ ] Run the collector for a few hours, confirm live field names, commit an anonymized `tests/fixtures/sample_response.json`
- [ ] **GTFS schedule ingest** (`ztm_ingest/gtfs.py`, `ztm-ingest gtfs`): daily zip to `bronze/gtfs/date=…/` (needed for punctuality)

**Done when:** `make check` is green. A live `uv run ztm-ingest --type 1` writes a file with the correct `_meta`, and its log lines are JSON. Tests pass with a broken `.env` present.

## Phase 2: Analytics locally with dbt + DuckDB ($0)

- [ ] New `dbt/` project using `dbt-duckdb`, reading local bronze JSON with `read_json`.
- [ ] Staging: `stg_vehicle_positions` (explode payload, Warsaw time → UTC, dedupe) and `stg_gtfs_*`.
- [ ] Marts: `fct_segment_speed`, `fct_bunching`, `fct_punctuality`.
- [ ] dbt tests (unique, not_null, accepted ranges). CI runs `dbt build` on the committed fixture.

Expect small SQL dialect edits when porting to Databricks in Phase 6. Use dbt cross-database macros where possible to keep them small.

**Done when:** `dbt build` passes locally and in CI.

## Phase 3: Check the student subscription (half a day, by hand)

- [ ] In the Azure portal, create a Databricks workspace. Run one single-node job and check whether serverless compute is available.
- [ ] Check vCPU quotas and region restrictions.
- [ ] Look at Cost Management the next day, then delete the test resources.

If anything is blocked, change Phases 4–6 before writing code.

## Phase 4: Infrastructure as code (Terraform, `infra/`)

- [ ] Remote state, resource group, ADLS Gen2 (`bronze` / `silver` / `gold`), Key Vault, Log Analytics + App Insights, Function App.
- [ ] **Cost guardrails in the first apply**: budget alerts at $10 / $25 / $50, auto-terminate of 10–15 min on all cluster policies, and a lifecycle rule moving bronze files older than 30 days to cool storage.
- [ ] Managed identity with blob write access to bronze (fits the `DefaultAzureCredential` code in the Azure writer).
- [ ] Databricks workspace + Unity Catalog, applied only when Phase 6 starts.
- [ ] GitHub Actions: `terraform fmt` / `validate` / `plan` on PR via OIDC (no stored secrets).

**Done when:** `terraform plan` is clean in CI.

## Phase 5: Deploy ingestion

- [ ] Azure Functions **Flex Consumption** timer (`*/30 * * * * *`) calling `run_once` for buses and trams, plus a daily GTFS trigger. A thin `function_app/` wrapper; logic stays in `ztm_ingest`.
- [ ] Key Vault reference for `ZTM_API_KEY`.
- [ ] Alert when no blobs have landed in 10 min during daytime.

**Done when:** new blobs appear under `bronze/vehicle_positions/type=1/date=<today>/` every 30 s.

## Phase 6: Databricks silver + gold (time-boxed: about 3–4 weeks of Azure Databricks)

Iterate first locally and/or on Databricks Free Edition. Use Azure Databricks for integration and the demo, then pause the job or destroy the workspace with Terraform.

- [ ] **Lakeflow Declarative Pipeline** (silver): Auto Loader on bronze, explode, UTC, dedupe, with expectations (Warsaw bounding box, nulls, stale pings). Triggered mode, not continuous.
- [ ] Port the Phase 2 dbt models to `dbt-databricks` (gold reads silver).
- [ ] **Databricks Workflows** nightly job: GTFS → silver pipeline → dbt task. Serverless or job compute only.
- [ ] Deploy with **Databricks Asset Bundles** from GitHub Actions.

**Done when:** hourly row counts reconcile bronze vs. silver, the nightly job succeeds, and the Databricks marts match the DuckDB marts on the same day's data.

## Phase 7: Serve and document

- [ ] Power BI Desktop in **import mode** on a small gold extract (not DirectQuery on a running SQL warehouse). Screenshots or a short demo video in the README.
- [ ] README: architecture diagram, cost notes, runbook, "rebuild from zero" (`terraform apply` + replay from bronze).
- [ ] ADR 0002 (compute and cost choices), ADR 0003 (local DuckDB, then Databricks).

## Phase 8 (optional): Extras

- [ ] Open-Meteo weather ingest (reuse the client/writer pattern) and a weather vs. delay mart.
- [ ] H3 hexagon speed heatmap using the Databricks built-in `h3_*` functions.

## Phase 9 (stretch, only if credit remains): Streaming

- [ ] The Function also publishes to Event Hubs (Kafka protocol). Spark Structured Streaming produces live bunching alerts. Run it for a time-boxed demo, then shut it down.
