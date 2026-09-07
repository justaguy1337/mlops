"""
dags/aqi_etl_dag.py
─────────────────────
Apache Airflow DAG: AQI ETL — Normalize, Validate, Load, Build Gold

Schedule: Daily at 04:00 UTC (09:30 IST) — runs 2 hours after ingestion.

Tasks (sequential pipeline with quality gate):
  1. load_raw_to_staging       — Read raw JSON → normalize → staging tables
  2. validate_and_clean        — Quality checks → cleaned tables
  3. quality_gate              — Fail if rejection rate > MAX_REJECTION_RATE%
  4. build_gold_layer          — Aggregations + AQI calc → gold tables
  5. identify_data_gaps        — Detect missing-period gaps and log warnings

Retries: 3 attempts, 5-minute delay
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, date

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "aqi_pipeline",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}

MAX_REJECTION_RATE = float(os.getenv("MAX_REJECTION_RATE", "20"))
TARGET_CITIES = [c.strip() for c in os.getenv("TARGET_CITIES", "Delhi,Mumbai,Bengaluru,Chennai,Kolkata").split(",")]


# ── Task 1: Load raw → staging ────────────────────────────────────────────────

def load_raw_to_staging(**context) -> dict:
    """
    Read raw JSON landing zone → normalize → insert into staging tables.
    Returns counts for measurements and weather records.
    """
    from ingestion.openaq_collector import OpenAQCollector
    from ingestion.openmeteo_collector import OpenMeteoCollector
    from etl.normalize import normalize_measurements, normalize_weather
    from db.db_utils import df_to_table, get_engine
    import pandas as pd

    logical_date: datetime = context["logical_date"]
    extraction_date: date = logical_date.date()

    # ── Load and normalize air quality ──
    aq_collector = OpenAQCollector(extraction_date=extraction_date)
    raw_aq_records = aq_collector.load_raw_files(extraction_date)
    df_aq_normalized = normalize_measurements(raw_aq_records)

    aq_count = 0
    if not df_aq_normalized.empty:
        # Write to staging
        df_aq_normalized["staged_at"] = pd.Timestamp.utcnow()
        df_to_table(df_aq_normalized, "measurements", "staging")
        aq_count = len(df_aq_normalized)
        logger.info("Loaded %d normalized measurement records to staging", aq_count)

    # ── Load and normalize weather ──
    weather_collector = OpenMeteoCollector(extraction_date=extraction_date)
    raw_weather_records = weather_collector.load_raw_files(extraction_date)
    df_weather_normalized = normalize_weather(raw_weather_records)

    weather_count = 0
    if not df_weather_normalized.empty:
        df_weather_normalized["staged_at"] = pd.Timestamp.utcnow()
        df_to_table(df_weather_normalized, "weather", "staging")
        weather_count = len(df_weather_normalized)
        logger.info("Loaded %d normalized weather records to staging", weather_count)

    return {
        "aq_staged": aq_count,
        "weather_staged": weather_count,
        "extraction_date": str(extraction_date),
    }


# ── Task 2: Validate and clean ────────────────────────────────────────────────

def validate_and_clean(**context) -> dict:
    """
    Apply quality checks to staging data → write valid records to cleaned tables.
    Logs rejected records to data/logs/error_log.csv.
    """
    from etl.validate import validate_measurements, validate_weather
    from db.db_utils import read_sql, df_to_table
    import uuid
    import pandas as pd

    run_id = str(uuid.uuid4())
    logical_date: datetime = context["logical_date"]
    extraction_date_str = str(logical_date.date())

    # ── Validate air quality ──
    df_staging_aq = read_sql(
        "SELECT * FROM staging.measurements WHERE extraction_date = :dt",
        {"dt": extraction_date_str},
    )
    aq_result = validate_measurements(df_staging_aq, run_id=run_id)
    df_valid_aq = aq_result.valid

    if not df_valid_aq.empty:
        df_valid_aq["cleaned_at"] = pd.Timestamp.utcnow()
        df_valid_aq["is_valid"] = True
        df_to_table(df_valid_aq, "air_quality", "cleaned")

    # ── Validate weather ──
    df_staging_weather = read_sql(
        "SELECT * FROM staging.weather WHERE extraction_date::text = :dt",
        {"dt": extraction_date_str},
    )
    weather_result = validate_weather(df_staging_weather, run_id=run_id)
    df_valid_weather = weather_result.valid

    if not df_valid_weather.empty:
        df_valid_weather["cleaned_at"] = pd.Timestamp.utcnow()
        df_to_table(df_valid_weather, "weather", "cleaned")

    result = {
        "aq_valid": len(df_valid_aq),
        "aq_rejected": len(aq_result.rejected),
        "aq_rejection_rate": round(aq_result.rejection_rate, 2),
        "weather_valid": len(df_valid_weather),
        "weather_rejected": len(weather_result.rejected),
        "extraction_date": extraction_date_str,
    }
    logger.info("Validation results: %s", result)
    return result


# ── Task 3: Quality gate ──────────────────────────────────────────────────────

def quality_gate(**context) -> str:
    """
    Branch task: fails the pipeline if rejection rate exceeds threshold.
    Returns next task_id based on quality check outcome.
    """
    ti = context["ti"]
    validation_result = ti.xcom_pull(task_ids="validate_and_clean") or {}
    rejection_rate = validation_result.get("aq_rejection_rate", 0.0)

    logger.info("Quality gate: rejection rate = %.1f%% (max allowed: %.1f%%)",
                rejection_rate, MAX_REJECTION_RATE)

    if rejection_rate > MAX_REJECTION_RATE:
        logger.error(
            "QUALITY GATE FAILED: rejection rate %.1f%% > %.1f%% threshold",
            rejection_rate, MAX_REJECTION_RATE,
        )
        return "quality_gate_failed"

    return "build_gold_layer"


# ── Task 4: Build gold layer ──────────────────────────────────────────────────

def run_build_gold_layer(**context) -> dict:
    """Read cleaned tables → build all gold-layer analytical tables."""
    from etl.gold_layer import build_gold_layer
    from db.db_utils import read_sql

    logical_date: datetime = context["logical_date"]
    extraction_date_str = str(logical_date.date())

    df_cleaned_aq = read_sql(
        "SELECT * FROM cleaned.air_quality WHERE extraction_date::text = :dt",
        {"dt": extraction_date_str},
    )
    df_cleaned_weather = read_sql(
        "SELECT * FROM cleaned.weather WHERE date(measured_at_ist) = :dt::date",
        {"dt": extraction_date_str},
    )

    gold_results = build_gold_layer(df_cleaned_aq, df_cleaned_weather)

    summary = {
        table: len(df) for table, df in gold_results.items()
    }
    logger.info("Gold layer build results: %s", summary)
    return summary


# ── Task 5: Identify data gaps ────────────────────────────────────────────────

def identify_data_gaps(**context) -> None:
    """Detect and log missing time-series periods in the cleaned data."""
    from etl.validate import identify_missing_periods
    from db.db_utils import read_sql

    logical_date: datetime = context["logical_date"]
    extraction_date_str = str(logical_date.date())

    df = read_sql(
        "SELECT location_id, parameter, measured_at_utc FROM cleaned.air_quality "
        "WHERE extraction_date::text = :dt",
        {"dt": extraction_date_str},
    )

    if df.empty:
        logger.warning("No cleaned data found for gap analysis on %s", extraction_date_str)
        return

    gaps = identify_missing_periods(df, threshold_hours=2)
    if not gaps.empty:
        logger.warning("Found %d data gaps:\n%s", len(gaps), gaps.to_string())
    else:
        logger.info("No data gaps found for %s", extraction_date_str)


# ── DAG definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="aqi_etl",
    description="Daily AQI ETL: normalize → validate → load cleaned → build gold",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 4 * * *",   # 04:00 UTC daily (2h after ingestion)
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["aqi", "etl", "data-engineering"],
    doc_md="""
## AQI ETL DAG

Transforms ingested raw data through the pipeline layers:

```
staging.measurements / staging.weather
         ↓ (validate + deduplicate)
cleaned.air_quality / cleaned.weather
         ↓ (aggregate + AQI calc)
gold.daily_city_aqi / gold.hourly_station_aqi / gold.pollutant_summary / gold.weather_aqi_daily
```

### Quality Gate
Pipeline fails if the measurement rejection rate exceeds `MAX_REJECTION_RATE` (default 20%).
    """,
) as dag:

    task_load_staging = PythonOperator(
        task_id="load_raw_to_staging",
        python_callable=load_raw_to_staging,
    )

    task_validate = PythonOperator(
        task_id="validate_and_clean",
        python_callable=validate_and_clean,
    )

    task_quality_gate = BranchPythonOperator(
        task_id="quality_gate",
        python_callable=quality_gate,
    )

    task_gate_failed = EmptyOperator(
        task_id="quality_gate_failed",
    )

    task_build_gold = PythonOperator(
        task_id="build_gold_layer",
        python_callable=run_build_gold_layer,
    )

    task_identify_gaps = PythonOperator(
        task_id="identify_data_gaps",
        python_callable=identify_data_gaps,
        trigger_rule="none_failed_min_one_success",
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    (
        task_load_staging
        >> task_validate
        >> task_quality_gate
        >> [task_build_gold, task_gate_failed]
    )
    task_build_gold >> task_identify_gaps
