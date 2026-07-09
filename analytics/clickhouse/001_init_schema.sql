-- WattWise AI — ClickHouse schema
-- Auto-executed on container first start

CREATE DATABASE IF NOT EXISTS wattwise;

-- Raw telemetry table (minute-grain)
CREATE TABLE IF NOT EXISTS wattwise.telemetry (
    facility_id     LowCardinality(String),
    device_id       String,
    device_class    LowCardinality(String),
    domain          LowCardinality(String),
    ts              DateTime64(3, 'UTC'),
    value           Float64,
    unit            LowCardinality(String),
    metadata        String DEFAULT '{}'
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (facility_id, device_id, domain, ts)
TTL toDateTime(ts) + INTERVAL 18 MONTH
SETTINGS index_granularity = 8192;

-- 15-minute demand aggregation view (for peak detection)
CREATE TABLE IF NOT EXISTS wattwise.demand_15min (
    facility_id     LowCardinality(String),
    ts_bucket       DateTime,
    avg_kw          Float64,
    max_kw          Float64,
    p95_kw          Float64
) ENGINE = SummingMergeTree()
ORDER BY (facility_id, ts_bucket);

-- Anomaly events log
CREATE TABLE IF NOT EXISTS wattwise.anomaly_events (
    event_id        UUID DEFAULT generateUUIDv4(),
    facility_id     LowCardinality(String),
    device_id       String,
    ts              DateTime64(3, 'UTC'),
    domain          LowCardinality(String),
    observed_value  Float64,
    expected_value  Float64,
    anomaly_score   Float64,
    stage           LowCardinality(String),  -- 'pyod' | 'lstm_ae' | 'confirmed'
    narrative       String DEFAULT '',
    created_at      DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (facility_id, ts)
TTL created_at + INTERVAL 12 MONTH;

-- Forecast results
CREATE TABLE IF NOT EXISTS wattwise.forecasts (
    facility_id     LowCardinality(String),
    forecast_ts     DateTime,
    generated_at    DateTime DEFAULT now(),
    horizon_hours   UInt8,
    predicted_kw    Float64,
    lower_bound     Float64,
    upper_bound     Float64,
    model           LowCardinality(String)   -- 'chronos' | 'darts'
) ENGINE = MergeTree()
ORDER BY (facility_id, forecast_ts);
