# analytics/ — High-Performance Analytics (Layer 2)

**Built in:** Weeks 6, 11

ClickHouse columnar store + DuckDB in-process queries + dbt-core tested transformations. Rolls minute-grain telemetry into 1-min / 15-min / hourly / daily / monthly cubes for sub-second dashboard response.

## Will contain
- `clickhouse/` — DDL init scripts (mounted into the ClickHouse container)
- `dbt/` — the dbt project (models, tests, sources)
  - `models/staging/` — cleaned telemetry
  - `models/marts/` — consumption, demand, cost cubes
- `duckdb/` — ad-hoc analytical query helpers

## QA
Every dbt model carries tests (`unique`, `not_null`, `accepted_values`, freshness). Target: 100% of models tested, `dbt test` green in CI.

## Success criteria
- Wk 6: consumption + demand cubes feed Grafana
- Wk 11: cost domain (ToU rate engine) added
