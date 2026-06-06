## Why

Ops roadmap lists Prometheus; agent-api had no metrics exposition.

## What Changes

- `/metrics` endpoint, HTTP middleware, evolution webhook histogram
- `EVI_METRICS_ENABLED`; compose comment for future scrape

**Out of scope:** Prometheus container in compose.
