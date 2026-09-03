# Power BI Hand-off Guide — Views 3 & 5

Power BI Desktop is a GUI tool; this is a build guide, not a `.pbix` file. Views 1/2
(Grafana) and View 4 (Streamlit) are already implemented in code — these are the
two remaining RFP views.

## Connecting Power BI to ClickHouse

ClickHouse doesn't have a native Power BI connector, so use the **ODBC** route:

1. Install the [ClickHouse ODBC driver](https://github.com/ClickHouse/clickhouse-odbc/releases)
   (`clickhouse-odbc-*-win64.msi`).
2. Windows: **ODBC Data Sources (64-bit)** → **Add** → `ClickHouse ODBC Driver (Unicode)` →
   Server `localhost` (or the B1s VM's public IP once deployed), Port `8123`,
   Database `wattwise`, User `wattwise`, Password from `.env` /
   `analytics/clickhouse/001_init_schema.sql`'s compose defaults.
3. Power BI Desktop → **Get Data** → **ODBC** → pick the DSN you just made.

**Fallback if the ODBC driver is flaky:** export the query results to CSV/Parquet
(`clickhouse-client --query "..." --format CSVWithNames > out.csv`, or via
`clickhouse_connect` in a one-off Python script) and use **Get Data → Text/CSV**
or **Get Data → Parquet**. Re-run the export and **Refresh** in Power BI when the
underlying data changes — no live query, but it unblocks the view if the ODBC
path doesn't cooperate before the deadline.

All tables referenced below are defined in
[`analytics/clickhouse/001_init_schema.sql`](../analytics/clickhouse/001_init_schema.sql).
The `cost` domain rows come from `ml/cost_engine.py`'s `add_cost_domain()` — make
sure whatever job writes to `wattwise.telemetry` has run `add_cost_domain()` first
(the Streamlit app calls `generate_with_cost()`, which does this).

---

## View 3 — Cost Analysis

**Contents (blueprint §8):** ₹ by facility/domain, ToU rate breakdown,
month-to-date projection.

### Query 1 — Cost by facility (card/matrix)
```sql
SELECT
    facility_id,
    toStartOfMonth(ts)              AS month,
    sum(value)                      AS total_cost_inr
FROM wattwise.telemetry
WHERE domain = 'cost'
GROUP BY facility_id, month
ORDER BY month, facility_id;
```
Visual: **Matrix** (rows = facility_id, columns = month, values = total_cost_inr),
or a **card** filtered to the current month for a single "MTD total" tile.

### Query 2 — Peak vs off-peak split (ToU breakdown)
`ml/cost_engine.py`'s `TouRateConfig` defines peak hours as **9am–6pm on
weekdays** (`peak_rate_per_kwh` ₹12 vs `offpeak_rate_per_kwh` ₹5.5, with a 15%
weekend discount). Reproduce that bucketing in SQL:
```sql
SELECT
    facility_id,
    multiIf(
        (toHour(ts) >= 9 AND toHour(ts) < 18) AND (toDayOfWeek(ts) < 6), 'peak',
        'off_peak'
    ) AS rate_period,
    sum(value) AS cost_inr
FROM wattwise.telemetry
WHERE domain = 'cost'
GROUP BY facility_id, rate_period
ORDER BY facility_id, rate_period;
```
Visual: **Stacked bar** (x = facility_id, y = cost_inr, legend = rate_period).

### Query 3 — Month-to-date projection
Linear projection = (cost so far this month / days elapsed) × days in month. Note:
`daysInMonth()` is **not** a real ClickHouse function (confirmed on 24.8 —
throws `UNKNOWN_FUNCTION`, closest suggestion is `DAYOFMONTH`, also wrong) —
use a date-arithmetic `dateDiff` instead:
```sql
SELECT
    facility_id,
    sum(value) AS cost_mtd_inr,
    dateDiff('day', toStartOfMonth(now()), now()) + 1 AS days_elapsed,
    dateDiff('day', toStartOfMonth(now()), toStartOfMonth(now()) + INTERVAL 1 MONTH) AS days_in_month,
    sum(value) / (dateDiff('day', toStartOfMonth(now()), now()) + 1)
        * dateDiff('day', toStartOfMonth(now()), toStartOfMonth(now()) + INTERVAL 1 MONTH) AS projected_month_cost_inr
FROM wattwise.telemetry
WHERE domain = 'cost' AND ts >= toStartOfMonth(now())
GROUP BY facility_id;
```
Visual: **Card** or **gauge** per facility (actual MTD vs. projected).

### Query 4 — Peak demand charge (from `ml/cost_engine.py::peak_demand_charge`)
```sql
SELECT
    facility_id,
    toStartOfMonth(ts)   AS month,
    max(value)           AS peak_kw,
    max(value) * 150.0   AS demand_charge_inr   -- Rs 150/kW, TouRateConfig.demand_charge_per_kw
FROM wattwise.telemetry
WHERE domain = 'demand'
GROUP BY facility_id, month;
```

---

## View 5 — Cross-Facility Benchmarking (bonus)

**Contents (blueprint §8):** kWh per sq.ft, normalized energy intensity.

### Facility square footage — one real value, two need your input
Only **office** has a documented reference in this repo:
[`ingestion/simulator.py:27`](../ingestion/simulator.py) — `base_kw: 45.0  #
typical 5,000 sqft office`. **Warehouse and datacentre have no square-footage
value anywhere in the codebase** — only `base_kw` (80.0 and 120.0 respectively),
which is a load figure, not a floor-area figure, and shouldn't be back-converted
into an implied sqft (that would make the "intensity" metric circular — you'd be
computing kWh/sqft from a sqft you derived from kWh). Fill in real or
representative values before building this view:

| Facility | sq.ft | Source |
|---|---|---|
| office | 5,000 | `ingestion/simulator.py:27` comment |
| warehouse | *(you decide)* | Typical mid-size warehouses run 50,000–150,000 sqft — pick a number and note it's an assumption, not measured data |
| datacentre | *(you decide)* | Typical small/edge data halls run 5,000–20,000 sqft — same caveat |

Put these in a small manual table in Power BI (**Enter Data**) named
`facility_area`, columns `facility_id`, `sqft`, and relate it to the query below
on `facility_id`.

### Query — kWh per facility (join to `facility_area` in Power BI)
```sql
SELECT
    facility_id,
    toStartOfMonth(ts)  AS month,
    sum(value)          AS total_kwh
FROM wattwise.telemetry
WHERE domain = 'consumption'
GROUP BY facility_id, month
ORDER BY month, facility_id;
```
In Power BI, add a calculated column: `energy_intensity = total_kwh / sqft`
(kWh/sq.ft/month).

Visuals:
- **Bar chart**: facility_id (x) vs energy_intensity (y), one bar per facility —
  the direct cross-facility comparison the view is named for.
- **Scatter**: sqft (x) vs total_kwh (y), one point per facility, to show whether
  consumption scales with size or a facility is an outlier (datacentre will be,
  by design — it runs ~24/7 near-constant load per `ingestion/simulator.py`'s
  `peak_hours: (0, 24)`).
