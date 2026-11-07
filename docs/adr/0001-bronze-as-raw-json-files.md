# ADR 0001: Bronze layer is immutable raw JSON files in object storage

- Status: accepted
- Date: 2026-11-07

## Context
The vehicle-location API returns the *last known position of every vehicle* on each call.
It has no history endpoint, so anything we do not store is lost forever.

## Decision
Every poll is written as one immutable JSON file (`_meta` + untouched `payload`) to
`vehicle_positions/type=<n>/date=<d>/hour=<h>/<utc_ts>.json`. No cleaning, no deduplication,
no timezone conversion at this stage.

## Consequences
- Replayability: silver can be rebuilt from bronze at any time after a bug fix.
- Cheap and simple to ingest; Databricks Auto Loader picks up new files incrementally.
- Many small files (about 1-2 per minute per vehicle type). Acceptable for this volume;
  Auto Loader and later compaction (OPTIMIZE on silver) handle it.
- Event Hubs/Kafka deliberately **not** used yet: there is no consumer needing sub-minute
  latency. Revisit if a real-time use case appears.
