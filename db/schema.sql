-- =============================================================================
-- AQI Pipeline — PostgreSQL Schema
-- Layers: raw → staging → cleaned → gold (analytical)
-- Meta:   ingestion tracking
-- =============================================================================

-- ── Schema creation ──────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS cleaned;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS meta;

-- =============================================================================
-- META LAYER — Pipeline tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.ingestion_log (
    log_id          SERIAL PRIMARY KEY,
    run_id          UUID NOT NULL,
    source          VARCHAR(100) NOT NULL,          -- 'openaq' | 'openmeteo'
    extraction_date DATE NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL,            -- 'success' | 'failed' | 'partial'
    row_count       INTEGER DEFAULT 0,
    rejected_count  INTEGER DEFAULT 0,
    error_message   TEXT,
    file_path       TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_log_date   ON meta.ingestion_log(extraction_date);
CREATE INDEX IF NOT EXISTS idx_ingestion_log_source ON meta.ingestion_log(source);


-- =============================================================================
-- RAW LAYER — Exact API payloads, never modified
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.openaq_measurements (
    id              BIGSERIAL PRIMARY KEY,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extraction_date DATE NOT NULL,
    run_id          UUID NOT NULL,
    -- OpenAQ v3 measurement fields (stored as received)
    location_id     INTEGER,
    location_name   TEXT,
    city            TEXT,
    country         VARCHAR(10),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    parameter       VARCHAR(50),      -- pm25, pm10, no2, o3, co, so2
    value           DOUBLE PRECISION,
    unit            VARCHAR(20),
    measured_at     TIMESTAMPTZ,
    is_mobile       BOOLEAN DEFAULT FALSE,
    -- Raw JSON payload for auditability
    raw_payload     JSONB
);

CREATE INDEX IF NOT EXISTS idx_raw_openaq_measured_at   ON raw.openaq_measurements(measured_at);
CREATE INDEX IF NOT EXISTS idx_raw_openaq_location      ON raw.openaq_measurements(location_id);
CREATE INDEX IF NOT EXISTS idx_raw_openaq_parameter     ON raw.openaq_measurements(parameter);
CREATE INDEX IF NOT EXISTS idx_raw_openaq_extraction    ON raw.openaq_measurements(extraction_date);


CREATE TABLE IF NOT EXISTS raw.openmeteo_weather (
    id              BIGSERIAL PRIMARY KEY,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extraction_date DATE NOT NULL,
    run_id          UUID NOT NULL,
    city            TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    measured_at     TIMESTAMPTZ,
    -- Weather variables
    temperature_2m          DOUBLE PRECISION,  -- °C
    relative_humidity_2m    DOUBLE PRECISION,  -- %
    wind_speed_10m          DOUBLE PRECISION,  -- km/h
    wind_direction_10m      DOUBLE PRECISION,  -- degrees
    precipitation           DOUBLE PRECISION,  -- mm
    surface_pressure        DOUBLE PRECISION,  -- hPa
    cloud_cover             DOUBLE PRECISION,  -- %
    raw_payload             JSONB
);

CREATE INDEX IF NOT EXISTS idx_raw_weather_measured_at ON raw.openmeteo_weather(measured_at);
CREATE INDEX IF NOT EXISTS idx_raw_weather_city        ON raw.openmeteo_weather(city);


-- =============================================================================
-- STAGING LAYER — Normalized, not yet validated/joined
-- =============================================================================

CREATE TABLE IF NOT EXISTS staging.measurements (
    id              BIGSERIAL PRIMARY KEY,
    raw_id          BIGINT REFERENCES raw.openaq_measurements(id),
    staged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extraction_date DATE NOT NULL,
    -- Normalized fields
    location_id     INTEGER NOT NULL,
    station_name    VARCHAR(255) NOT NULL,        -- title-cased, trimmed
    city            VARCHAR(100) NOT NULL,
    country         VARCHAR(10) NOT NULL DEFAULT 'IN',
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    parameter       VARCHAR(20) NOT NULL,          -- lowercase standard name
    value_ugm3      DOUBLE PRECISION NOT NULL,     -- always in µg/m³
    measured_at_utc TIMESTAMPTZ NOT NULL,
    measured_at_ist TIMESTAMPTZ NOT NULL           -- UTC+5:30
);

CREATE INDEX IF NOT EXISTS idx_staging_measured_at ON staging.measurements(measured_at_utc);
CREATE INDEX IF NOT EXISTS idx_staging_station     ON staging.measurements(location_id);
CREATE INDEX IF NOT EXISTS idx_staging_parameter   ON staging.measurements(parameter);
CREATE INDEX IF NOT EXISTS idx_staging_city        ON staging.measurements(city);


CREATE TABLE IF NOT EXISTS staging.weather (
    id              BIGSERIAL PRIMARY KEY,
    raw_id          BIGINT REFERENCES raw.openmeteo_weather(id),
    staged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    city            VARCHAR(100) NOT NULL,
    measured_at_utc TIMESTAMPTZ NOT NULL,
    measured_at_ist TIMESTAMPTZ NOT NULL,
    temperature_2m          DOUBLE PRECISION,
    relative_humidity_2m    DOUBLE PRECISION,
    wind_speed_10m          DOUBLE PRECISION,
    wind_direction_10m      DOUBLE PRECISION,
    precipitation           DOUBLE PRECISION,
    surface_pressure        DOUBLE PRECISION,
    cloud_cover             DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_staging_weather_city ON staging.weather(city);
CREATE INDEX IF NOT EXISTS idx_staging_weather_time ON staging.weather(measured_at_utc);


-- =============================================================================
-- CLEANED LAYER — Validated, deduplicated, quality-checked records
-- =============================================================================

CREATE TABLE IF NOT EXISTS cleaned.air_quality (
    id              BIGSERIAL PRIMARY KEY,
    staging_id      BIGINT REFERENCES staging.measurements(id),
    cleaned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location_id     INTEGER NOT NULL,
    station_name    VARCHAR(255) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    country         VARCHAR(10) NOT NULL DEFAULT 'IN',
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    parameter       VARCHAR(20) NOT NULL,
    value_ugm3      DOUBLE PRECISION NOT NULL,
    measured_at_utc TIMESTAMPTZ NOT NULL,
    measured_at_ist TIMESTAMPTZ NOT NULL,
    -- AQI sub-index for this pollutant
    aqi_sub_index   DOUBLE PRECISION,
    -- Quality flags
    is_valid        BOOLEAN NOT NULL DEFAULT TRUE,
    validation_note TEXT,
    UNIQUE (location_id, parameter, measured_at_utc)
);

CREATE INDEX IF NOT EXISTS idx_cleaned_aq_station   ON cleaned.air_quality(location_id);
CREATE INDEX IF NOT EXISTS idx_cleaned_aq_city      ON cleaned.air_quality(city);
CREATE INDEX IF NOT EXISTS idx_cleaned_aq_parameter ON cleaned.air_quality(parameter);
CREATE INDEX IF NOT EXISTS idx_cleaned_aq_time      ON cleaned.air_quality(measured_at_utc);


CREATE TABLE IF NOT EXISTS cleaned.weather (
    id              BIGSERIAL PRIMARY KEY,
    staging_id      BIGINT REFERENCES staging.weather(id),
    cleaned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    city            VARCHAR(100) NOT NULL,
    measured_at_utc TIMESTAMPTZ NOT NULL,
    measured_at_ist TIMESTAMPTZ NOT NULL,
    temperature_2m          DOUBLE PRECISION,
    relative_humidity_2m    DOUBLE PRECISION,
    wind_speed_10m          DOUBLE PRECISION,
    wind_direction_10m      DOUBLE PRECISION,
    precipitation           DOUBLE PRECISION,
    surface_pressure        DOUBLE PRECISION,
    cloud_cover             DOUBLE PRECISION,
    UNIQUE (city, measured_at_utc)
);

CREATE INDEX IF NOT EXISTS idx_cleaned_weather_city ON cleaned.weather(city);
CREATE INDEX IF NOT EXISTS idx_cleaned_weather_time ON cleaned.weather(measured_at_utc);


-- Rejected records log
CREATE TABLE IF NOT EXISTS cleaned.rejected_records (
    id              BIGSERIAL PRIMARY KEY,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_table    VARCHAR(50),       -- 'staging.measurements' | 'staging.weather'
    source_id       BIGINT,
    rejection_reason TEXT NOT NULL,
    original_value  TEXT
);


-- =============================================================================
-- GOLD / ANALYTICAL LAYER — Aggregated, analysis-ready tables
-- =============================================================================

-- Hourly station-level AQI
CREATE TABLE IF NOT EXISTS gold.hourly_station_aqi (
    id              BIGSERIAL PRIMARY KEY,
    location_id     INTEGER NOT NULL,
    station_name    VARCHAR(255) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    hour_utc        TIMESTAMPTZ NOT NULL,
    hour_ist        TIMESTAMPTZ NOT NULL,
    -- Pollutant averages (µg/m³)
    pm25_avg        DOUBLE PRECISION,
    pm10_avg        DOUBLE PRECISION,
    no2_avg         DOUBLE PRECISION,
    o3_avg          DOUBLE PRECISION,
    co_avg          DOUBLE PRECISION,
    so2_avg         DOUBLE PRECISION,
    -- AQI
    aqi             INTEGER,
    aqi_category    VARCHAR(50),       -- Good / Satisfactory / Moderate / Poor / Very Poor / Severe
    dominant_pollutant VARCHAR(20),
    UNIQUE (location_id, hour_utc)
);

CREATE INDEX IF NOT EXISTS idx_gold_hourly_city ON gold.hourly_station_aqi(city);
CREATE INDEX IF NOT EXISTS idx_gold_hourly_time ON gold.hourly_station_aqi(hour_utc);


-- Daily city-level AQI (primary analytics table)
CREATE TABLE IF NOT EXISTS gold.daily_city_aqi (
    id              BIGSERIAL PRIMARY KEY,
    city            VARCHAR(100) NOT NULL,
    date_ist        DATE NOT NULL,
    -- Pollutant 24-hour averages (µg/m³)
    pm25_avg        DOUBLE PRECISION,
    pm10_avg        DOUBLE PRECISION,
    no2_avg         DOUBLE PRECISION,
    o3_avg          DOUBLE PRECISION,
    co_avg          DOUBLE PRECISION,
    so2_avg         DOUBLE PRECISION,
    -- AQI
    aqi             INTEGER,
    aqi_category    VARCHAR(50),
    dominant_pollutant VARCHAR(20),
    -- Station count used in aggregation
    station_count   INTEGER,
    UNIQUE (city, date_ist)
);

CREATE INDEX IF NOT EXISTS idx_gold_daily_city ON gold.daily_city_aqi(city);
CREATE INDEX IF NOT EXISTS idx_gold_daily_date ON gold.daily_city_aqi(date_ist);


-- Station-level metadata / dimension table
CREATE TABLE IF NOT EXISTS gold.dim_stations (
    location_id     INTEGER PRIMARY KEY,
    station_name    VARCHAR(255) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    country         VARCHAR(10) NOT NULL DEFAULT 'IN',
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    first_seen      DATE,
    last_seen       DATE,
    is_active       BOOLEAN DEFAULT TRUE
);


-- Pollutant contribution summary (for pie/bar charts)
CREATE TABLE IF NOT EXISTS gold.pollutant_summary (
    id              BIGSERIAL PRIMARY KEY,
    city            VARCHAR(100) NOT NULL,
    date_ist        DATE NOT NULL,
    parameter       VARCHAR(20) NOT NULL,
    avg_value       DOUBLE PRECISION,
    aqi_sub_index   DOUBLE PRECISION,
    contribution_pct DOUBLE PRECISION,
    UNIQUE (city, date_ist, parameter)
);

CREATE INDEX IF NOT EXISTS idx_gold_pollutant_city ON gold.pollutant_summary(city);
CREATE INDEX IF NOT EXISTS idx_gold_pollutant_date ON gold.pollutant_summary(date_ist);


-- Weather + AQI correlation table (enriched daily view)
CREATE TABLE IF NOT EXISTS gold.weather_aqi_daily (
    id              BIGSERIAL PRIMARY KEY,
    city            VARCHAR(100) NOT NULL,
    date_ist        DATE NOT NULL,
    aqi             INTEGER,
    aqi_category    VARCHAR(50),
    -- Weather (daily averages)
    temp_avg        DOUBLE PRECISION,
    humidity_avg    DOUBLE PRECISION,
    wind_speed_avg  DOUBLE PRECISION,
    precipitation_sum DOUBLE PRECISION,
    UNIQUE (city, date_ist)
);

CREATE INDEX IF NOT EXISTS idx_gold_weather_aqi_city ON gold.weather_aqi_daily(city);
CREATE INDEX IF NOT EXISTS idx_gold_weather_aqi_date ON gold.weather_aqi_daily(date_ist);


-- =============================================================================
-- VIEWS — Convenience query helpers
-- =============================================================================

-- Latest AQI per city
CREATE OR REPLACE VIEW gold.v_latest_city_aqi AS
SELECT DISTINCT ON (city)
    city,
    date_ist,
    aqi,
    aqi_category,
    dominant_pollutant,
    pm25_avg,
    pm10_avg,
    no2_avg,
    o3_avg
FROM gold.daily_city_aqi
ORDER BY city, date_ist DESC;


-- 7-day rolling average AQI per city
CREATE OR REPLACE VIEW gold.v_rolling_7day_aqi AS
SELECT
    city,
    date_ist,
    aqi,
    AVG(aqi) OVER (
        PARTITION BY city
        ORDER BY date_ist
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS aqi_7day_avg,
    aqi_category
FROM gold.daily_city_aqi
ORDER BY city, date_ist;
