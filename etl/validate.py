"""
etl/validate.py
────────────────
Data quality checks for the AQI pipeline:
  1. Pollutant range validation (EPA-based bounds)
  2. Duplicate record removal
  3. Missing-period identification (gaps > 2 hours)
  4. Rejected record logging

All rejected records are logged to data/logs/error_log.csv and
optionally to cleaned.rejected_records in PostgreSQL.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import pandas as pd
import numpy as np

from ingestion.ingestion_log import IngestionLogger

logger = logging.getLogger(__name__)

# ── Pollutant valid ranges (µg/m³) ──────────────────────────────────────────
# Based on WHO/EPA guidelines — extreme outliers beyond these are flagged
POLLUTANT_RANGES: dict[str, tuple[float, float]] = {
    "pm25": (0.0, 1000.0),    # µg/m³ — 500 is "Beyond AQI" but allow margin
    "pm10": (0.0, 2000.0),
    "no2":  (0.0, 3000.0),    # high industrial areas can exceed 1000
    "o3":   (0.0, 1000.0),
    "co":   (0.0, 100000.0),  # CO in µg/m³ (note: 50 ppm ≈ 57,250 µg/m³)
    "so2":  (0.0, 2000.0),
}

# Gap threshold for missing-period detection (hours)
MISSING_PERIOD_THRESHOLD_HOURS = 2


class ValidationResult:
    """Container for validation output."""

    def __init__(self, valid_df: pd.DataFrame, rejected_df: pd.DataFrame):
        self.valid = valid_df
        self.rejected = rejected_df

    @property
    def rejection_rate(self) -> float:
        total = len(self.valid) + len(self.rejected)
        return (len(self.rejected) / total * 100) if total > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"ValidationResult(valid={len(self.valid)}, "
            f"rejected={len(self.rejected)}, "
            f"rejection_rate={self.rejection_rate:.1f}%)"
        )


# ── Measurement validation ────────────────────────────────────────────────────

def validate_measurements(
    df: pd.DataFrame,
    run_id: str | None = None,
) -> ValidationResult:
    """
    Validate normalized measurement DataFrame.

    Checks performed:
    1. Drop rows with null critical fields
    2. Range check per pollutant
    3. Deduplicate by (location_id, parameter, measured_at_utc)

    Parameters
    ----------
    df     : normalized measurements DataFrame
    run_id : UUID string for logging (auto-generated if None)

    Returns
    -------
    ValidationResult with .valid and .rejected DataFrames
    """
    if df.empty:
        return ValidationResult(pd.DataFrame(), pd.DataFrame())

    run_id = run_id or str(uuid.uuid4())
    error_logger = IngestionLogger()
    rejected_rows: list[dict] = []
    mask_valid = pd.Series(True, index=df.index)

    # 1. Null critical fields
    null_mask = df["value_ugm3"].isna() | df["parameter"].isna() | df["measured_at_utc"].isna()
    for idx in df[null_mask].index:
        rejected_rows.append({
            "source_idx": idx,
            "rejection_reason": "null_critical_field",
            "original_value": str(df.loc[idx, "value_ugm3"]),
        })
        error_logger.log_error(
            run_id=run_id,
            source="validate_measurements",
            record_index=idx,
            rejection_reason="null_critical_field",
        )
    mask_valid &= ~null_mask

    # 2. Pollutant range check
    for param, (lo, hi) in POLLUTANT_RANGES.items():
        param_mask = df["parameter"] == param
        out_of_range = param_mask & (
            (df["value_ugm3"] < lo) | (df["value_ugm3"] > hi)
        )
        for idx in df[out_of_range].index:
            val = df.loc[idx, "value_ugm3"]
            reason = f"out_of_range:{param} value={val:.2f} bounds=[{lo},{hi}]"
            rejected_rows.append({
                "source_idx": idx,
                "rejection_reason": reason,
                "original_value": str(val),
            })
            error_logger.log_error(
                run_id=run_id,
                source="validate_measurements",
                record_index=idx,
                rejection_reason=reason,
                original_value=str(val),
            )
        mask_valid &= ~out_of_range

    # 3. Deduplicate on (location_id, parameter, measured_at_utc) — keep first
    df_valid_pre_dedup = df[mask_valid].copy()
    dedup_cols = ["location_id", "parameter", "measured_at_utc"]
    dup_mask = df_valid_pre_dedup.duplicated(subset=dedup_cols, keep="first")
    duplicate_count = dup_mask.sum()
    if duplicate_count > 0:
        logger.info("Removed %d duplicate measurement records", duplicate_count)

    df_valid = df_valid_pre_dedup[~dup_mask].copy()
    df_rejected = df[~mask_valid].copy()

    result = ValidationResult(df_valid, df_rejected)
    logger.info(
        "Measurement validation: %d valid, %d rejected (%.1f%%)",
        len(df_valid), len(df_rejected), result.rejection_rate,
    )
    return result


# ── Weather validation ────────────────────────────────────────────────────────

WEATHER_RANGES: dict[str, tuple[float, float]] = {
    "temperature_2m":       (-50.0, 60.0),    # °C
    "relative_humidity_2m": (0.0, 100.0),     # %
    "wind_speed_10m":       (0.0, 300.0),     # km/h
    "precipitation":        (0.0, 500.0),     # mm/hour
    "surface_pressure":     (800.0, 1100.0),  # hPa
    "cloud_cover":          (0.0, 100.0),     # %
}


def validate_weather(
    df: pd.DataFrame,
    run_id: str | None = None,
) -> ValidationResult:
    """
    Validate normalized weather DataFrame.

    Checks:
    1. Null timestamp or city
    2. Physical range bounds per variable
    3. Deduplication on (city, measured_at_utc)
    """
    if df.empty:
        return ValidationResult(pd.DataFrame(), pd.DataFrame())

    run_id = run_id or str(uuid.uuid4())
    error_logger = IngestionLogger()
    mask_valid = pd.Series(True, index=df.index)

    # 1. Null checks
    null_mask = df["measured_at_utc"].isna() | df["city"].isna()
    mask_valid &= ~null_mask

    # 2. Range checks
    for col, (lo, hi) in WEATHER_RANGES.items():
        if col not in df.columns:
            continue
        out_of_range = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        for idx in df[out_of_range].index:
            val = df.loc[idx, col]
            error_logger.log_error(
                run_id=run_id,
                source="validate_weather",
                record_index=idx,
                rejection_reason=f"out_of_range:{col} value={val}",
                original_value=str(val),
            )
        # For weather, out-of-range values become NaN rather than dropping the row
        df.loc[out_of_range, col] = np.nan

    # 3. Deduplicate
    df_valid_pre_dedup = df[mask_valid].copy()
    dup_mask = df_valid_pre_dedup.duplicated(subset=["city", "measured_at_utc"], keep="first")
    df_valid = df_valid_pre_dedup[~dup_mask].copy()
    df_rejected = df[~mask_valid].copy()

    result = ValidationResult(df_valid, df_rejected)
    logger.info(
        "Weather validation: %d valid, %d rejected", len(df_valid), len(df_rejected)
    )
    return result


# ── Missing period detection ──────────────────────────────────────────────────

def identify_missing_periods(
    df: pd.DataFrame,
    location_id_col: str = "location_id",
    time_col: str = "measured_at_utc",
    threshold_hours: int = MISSING_PERIOD_THRESHOLD_HOURS,
) -> pd.DataFrame:
    """
    Identify time gaps greater than threshold_hours for each station/pollutant.

    Returns
    -------
    pd.DataFrame with columns:
        location_id, parameter, gap_start, gap_end, gap_hours
    """
    if df.empty:
        return pd.DataFrame()

    gaps: list[dict] = []
    group_cols = [location_id_col, "parameter"] if "parameter" in df.columns else [location_id_col]

    for keys, group in df.groupby(group_cols):
        group_sorted = group.sort_values(time_col)
        times = group_sorted[time_col]
        diffs = times.diff()
        threshold = pd.Timedelta(hours=threshold_hours)

        for i, diff in enumerate(diffs):
            if pd.isna(diff) or diff <= threshold:
                continue
            gap_start = times.iloc[i - 1]
            gap_end = times.iloc[i]
            gap_hours = diff.total_seconds() / 3600

            gap_entry = {
                "gap_start": gap_start,
                "gap_end": gap_end,
                "gap_hours": round(gap_hours, 2),
            }
            if isinstance(keys, tuple):
                for col, val in zip(group_cols, keys):
                    gap_entry[col] = val
            else:
                gap_entry[group_cols[0]] = keys

            gaps.append(gap_entry)
            logger.warning(
                "Gap detected: %s — %.1fh gap from %s to %s",
                keys, gap_hours, gap_start, gap_end,
            )

    if not gaps:
        logger.info("No missing periods detected (threshold: %dh)", threshold_hours)
        return pd.DataFrame()

    result = pd.DataFrame(gaps)
    logger.info("Identified %d missing periods", len(result))
    return result
