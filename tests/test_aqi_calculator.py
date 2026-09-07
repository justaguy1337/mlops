"""
tests/test_aqi_calculator.py
──────────────────────────────
Unit tests for the EPA AQI calculator.
Tests breakpoint interpolation, category assignment, and edge cases.
"""

import pytest
import numpy as np
from etl.aqi_calculator import (
    sub_index,
    calculate_aqi,
    aqi_category,
    AQIResult,
    AQI_CATEGORIES,
    calculate_aqi_for_df,
)
import pandas as pd


# ── AQI category tests ────────────────────────────────────────────────────────

class TestAqiCategory:
    def test_good(self):
        assert aqi_category(0) == "Good"
        assert aqi_category(25) == "Good"
        assert aqi_category(50) == "Good"

    def test_moderate(self):
        assert aqi_category(51) == "Moderate"
        assert aqi_category(75) == "Moderate"
        assert aqi_category(100) == "Moderate"

    def test_usg(self):
        assert aqi_category(101) == "Unhealthy for Sensitive Groups"
        assert aqi_category(150) == "Unhealthy for Sensitive Groups"

    def test_unhealthy(self):
        assert aqi_category(151) == "Unhealthy"
        assert aqi_category(200) == "Unhealthy"

    def test_very_unhealthy(self):
        assert aqi_category(201) == "Very Unhealthy"
        assert aqi_category(300) == "Very Unhealthy"

    def test_hazardous(self):
        assert aqi_category(301) == "Hazardous"
        assert aqi_category(500) == "Hazardous"

    def test_above_500(self):
        # Anything above 500 should still return Hazardous
        assert aqi_category(600) == "Hazardous"

    def test_none(self):
        assert aqi_category(None) == "Unknown"

    def test_nan(self):
        assert aqi_category(float("nan")) == "Unknown"


# ── Sub-index calculation tests ───────────────────────────────────────────────

class TestSubIndex:
    def test_pm25_good(self):
        # PM2.5 = 5.0 µg/m³ should map to AQI ~42
        result = sub_index("pm25", 5.0)
        assert result is not None
        assert 0 <= result <= 50

    def test_pm25_moderate(self):
        # PM2.5 = 20.0 µg/m³ should be moderate
        result = sub_index("pm25", 20.0)
        assert result is not None
        assert 51 <= result <= 100

    def test_pm25_unhealthy(self):
        # PM2.5 = 100.0 µg/m³ should be unhealthy
        result = sub_index("pm25", 100.0)
        assert result is not None
        assert 151 <= result <= 200

    def test_pm25_extreme(self):
        # Above max breakpoint → 500
        result = sub_index("pm25", 600.0)
        assert result == 500.0

    def test_pm10_good(self):
        result = sub_index("pm10", 20)
        assert result is not None
        assert 0 <= result <= 50

    def test_no2(self):
        result = sub_index("no2", 50.0)
        assert result is not None
        assert result >= 0

    def test_o3(self):
        result = sub_index("o3", 80.0)
        assert result is not None
        assert result >= 0

    def test_co(self):
        result = sub_index("co", 1000.0)
        assert result is not None
        assert result >= 0

    def test_negative_value(self):
        result = sub_index("pm25", -1.0)
        assert result is None

    def test_zero(self):
        result = sub_index("pm25", 0.0)
        assert result is not None
        assert result == 0.0

    def test_none_concentration(self):
        result = sub_index("pm25", None)
        assert result is None

    def test_nan_concentration(self):
        result = sub_index("pm25", float("nan"))
        assert result is None

    def test_unknown_pollutant(self):
        result = sub_index("xyz", 50.0)
        assert result is None


# ── Overall AQI calculation tests ─────────────────────────────────────────────

class TestCalculateAqi:
    def test_single_pollutant(self):
        result = calculate_aqi({"pm25": 10.0})
        assert result.aqi is not None
        assert result.dominant_pollutant == "pm25"
        assert result.category == "Good"

    def test_multiple_pollutants_max_wins(self):
        # PM2.5=250 (hazardous), NO2=30 (good)
        result = calculate_aqi({"pm25": 250.0, "no2": 30.0})
        assert result.dominant_pollutant == "pm25"
        assert result.aqi >= 201  # Very Unhealthy or worse

    def test_all_none(self):
        result = calculate_aqi({"pm25": None, "pm10": None})
        assert result.aqi is None
        assert result.category == "Unknown"
        assert result.dominant_pollutant is None

    def test_mixed_none_valid(self):
        result = calculate_aqi({"pm25": None, "pm10": 80.0})
        assert result.aqi is not None
        assert result.dominant_pollutant == "pm10"

    def test_returns_aqi_result(self):
        result = calculate_aqi({"pm25": 35.0, "pm10": 60.0})
        assert isinstance(result, AQIResult)
        assert result.sub_indices is not None

    def test_empty_dict(self):
        result = calculate_aqi({})
        assert result.aqi is None


# ── DataFrame-level AQI calculation tests ────────────────────────────────────

class TestCalculateAqiForDf:
    def test_basic_calculation(self):
        df = pd.DataFrame([
            {"city": "Delhi", "pm25": 50.0, "pm10": 80.0, "no2": 40.0, "o3": 60.0},
            {"city": "Mumbai", "pm25": 10.0, "pm10": 20.0, "no2": 15.0, "o3": 20.0},
        ])
        result = calculate_aqi_for_df(df)
        assert "aqi" in result.columns
        assert "aqi_category" in result.columns
        assert "dominant_pollutant" in result.columns
        assert len(result) == 2

    def test_handles_nan(self):
        df = pd.DataFrame([{"pm25": float("nan"), "pm10": 50.0}])
        result = calculate_aqi_for_df(df)
        assert result.iloc[0]["dominant_pollutant"] == "pm10"

    def test_no_pollutant_columns(self):
        df = pd.DataFrame([{"city": "Delhi", "temperature": 25.0}])
        result = calculate_aqi_for_df(df)
        assert "aqi" in result.columns
        assert result.iloc[0]["aqi"] is None


# ── EPA linear interpolation test ─────────────────────────────────────────────

class TestInterpolation:
    def test_pm25_breakpoint_boundary(self):
        # At C_lo of each breakpoint, I should = I_lo
        # PM2.5: 0.0 → AQI 0, 12.1 → AQI 51
        result_lo = sub_index("pm25", 0.0)
        assert result_lo == pytest.approx(0.0, abs=1)

        result_moderate_lo = sub_index("pm25", 12.1)
        assert result_moderate_lo == pytest.approx(51.0, abs=2)

    def test_pm25_midpoint(self):
        # At midpoint of Good range (6.05), AQI ~= 25
        result = sub_index("pm25", 6.05)
        assert result == pytest.approx(25.0, abs=3)
