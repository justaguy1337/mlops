"""
dashboard/utils/db_queries.py
──────────────────────────────
Cached SQL query functions for the Streamlit dashboard.
Uses st.cache_data with TTL to avoid hammering the database on every rerender.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# ── Connection ────────────────────────────────────────────────────────────────

def _get_engine():
    """Build a SQLAlchemy engine using environment variables."""
    user = os.getenv("POSTGRES_USER", "aqi_user")
    password = os.getenv("POSTGRES_PASSWORD", "aqi_secret_password_change_me")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "aqi_db")
    dsn = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(dsn, pool_pre_ping=True)


def _read(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = _get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ── Available cities ──────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_cities() -> list[str]:
    """Return list of cities with data in the gold layer."""
    try:
        df = _read("SELECT DISTINCT city FROM gold.daily_city_aqi ORDER BY city")
        return df["city"].tolist()
    except Exception:
        return ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata"]


@st.cache_data(ttl=3600)
def get_date_range() -> tuple[date, date]:
    """Return the min/max date range available in the gold layer."""
    try:
        df = _read("SELECT MIN(date_ist) AS min_date, MAX(date_ist) AS max_date FROM gold.daily_city_aqi")
        return df["min_date"].iloc[0], df["max_date"].iloc[0]
    except Exception:
        today = date.today()
        return today - timedelta(days=30), today


# ── Page 1: AQI Trend ─────────────────────────────────────────────────────────

@st.cache_data(ttl=900)
def get_aqi_trend(
    cities: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Daily AQI trend for selected cities and date range."""
    sql = """
        SELECT city, date_ist, aqi, aqi_category, dominant_pollutant,
               pm25_avg, pm10_avg, no2_avg, o3_avg
        FROM gold.daily_city_aqi
        WHERE city = ANY(:cities)
          AND date_ist BETWEEN :start_date AND :end_date
        ORDER BY city, date_ist
    """
    return _read(sql, {"cities": cities, "start_date": start_date, "end_date": end_date})


@st.cache_data(ttl=900)
def get_rolling_aqi(cities: list[str], start_date: date, end_date: date) -> pd.DataFrame:
    """7-day rolling average AQI for selected cities."""
    sql = """
        SELECT city, date_ist, aqi, aqi_7day_avg, aqi_category
        FROM gold.v_rolling_7day_aqi
        WHERE city = ANY(:cities)
          AND date_ist BETWEEN :start_date AND :end_date
        ORDER BY city, date_ist
    """
    return _read(sql, {"cities": cities, "start_date": start_date, "end_date": end_date})


# ── Page 2: Pollutant Contribution ───────────────────────────────────────────

@st.cache_data(ttl=900)
def get_pollutant_contribution(
    city: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Pollutant contribution percentages for a city and date range."""
    sql = """
        SELECT date_ist, parameter, avg_value, aqi_sub_index, contribution_pct
        FROM gold.pollutant_summary
        WHERE city = :city
          AND date_ist BETWEEN :start_date AND :end_date
        ORDER BY date_ist, aqi_sub_index DESC
    """
    return _read(sql, {"city": city, "start_date": start_date, "end_date": end_date})


# ── Page 3: City Comparison ───────────────────────────────────────────────────

@st.cache_data(ttl=900)
def get_city_comparison(start_date: date, end_date: date) -> pd.DataFrame:
    """All-cities AQI data for comparison heatmap/bar chart."""
    sql = """
        SELECT city, date_ist, aqi, aqi_category
        FROM gold.daily_city_aqi
        WHERE date_ist BETWEEN :start_date AND :end_date
        ORDER BY city, date_ist
    """
    return _read(sql, {"start_date": start_date, "end_date": end_date})


@st.cache_data(ttl=3600)
def get_city_stats(start_date: date, end_date: date) -> pd.DataFrame:
    """Summary stats per city (mean, max, min AQI, most common category)."""
    sql = """
        SELECT
            city,
            ROUND(AVG(aqi)::numeric, 1) AS avg_aqi,
            MAX(aqi) AS max_aqi,
            MIN(aqi) AS min_aqi,
            COUNT(*) AS data_days,
            MODE() WITHIN GROUP (ORDER BY aqi_category) AS dominant_category
        FROM gold.daily_city_aqi
        WHERE date_ist BETWEEN :start_date AND :end_date
        GROUP BY city
        ORDER BY avg_aqi DESC
    """
    return _read(sql, {"start_date": start_date, "end_date": end_date})


# ── Page 4: Hourly & Monthly Patterns ────────────────────────────────────────

@st.cache_data(ttl=1800)
def get_hourly_pattern(city: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Average AQI by hour-of-day and day-of-week for heatmap."""
    sql = """
        SELECT
            EXTRACT(HOUR FROM hour_ist) AS hour_of_day,
            EXTRACT(DOW  FROM hour_ist) AS day_of_week,
            ROUND(AVG(aqi)::numeric, 1) AS avg_aqi
        FROM gold.hourly_station_aqi
        WHERE city = :city
          AND date(hour_ist) BETWEEN :start_date AND :end_date
        GROUP BY hour_of_day, day_of_week
        ORDER BY day_of_week, hour_of_day
    """
    return _read(sql, {"city": city, "start_date": start_date, "end_date": end_date})


@st.cache_data(ttl=1800)
def get_monthly_pattern(city: str) -> pd.DataFrame:
    """Monthly AQI distribution (for box plot)."""
    sql = """
        SELECT
            TO_CHAR(date_ist, 'Mon YYYY') AS month_label,
            DATE_TRUNC('month', date_ist)  AS month_start,
            aqi
        FROM gold.daily_city_aqi
        WHERE city = :city
          AND aqi IS NOT NULL
        ORDER BY month_start
    """
    return _read(sql, {"city": city})


# ── Page 5: Weather Impact ────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def get_weather_aqi(city: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Daily weather + AQI joined data for correlation plots."""
    sql = """
        SELECT
            date_ist, aqi, aqi_category,
            temp_avg, humidity_avg, wind_speed_avg, precipitation_sum
        FROM gold.weather_aqi_daily
        WHERE city = :city
          AND date_ist BETWEEN :start_date AND :end_date
          AND aqi IS NOT NULL
        ORDER BY date_ist
    """
    return _read(sql, {"city": city, "start_date": start_date, "end_date": end_date})


# ── KPI summary ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_latest_kpis() -> pd.DataFrame:
    """Latest AQI per city for the dashboard header KPIs."""
    sql = """
        SELECT city, date_ist, aqi, aqi_category, dominant_pollutant
        FROM gold.v_latest_city_aqi
        ORDER BY city
    """
    try:
        return _read(sql)
    except Exception:
        return pd.DataFrame()
