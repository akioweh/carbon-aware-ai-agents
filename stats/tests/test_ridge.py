"""Tests for the Direct Ridge predictor — feature engineering and pipeline."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from predictors.ridge import (
    _infer_dc_name,
    _predict_carbon_intensity,
    build_cyclical_features,
)


# ── build_cyclical_features ──────────────────────────────────────────────


class TestCyclicalFeatures:
    def test_output_shape(self):
        ts = pd.date_range("2026-03-18", periods=48, freq="30min")
        features = build_cyclical_features(ts)
        assert features.shape == (48, 6)

    def test_columns(self):
        ts = pd.date_range("2026-03-18", periods=10, freq="h")
        features = build_cyclical_features(ts)
        expected = {"hour_sin", "hour_cos", "dow_sin", "dow_cos", "min_sin", "min_cos"}
        assert set(features.columns) == expected

    def test_values_in_range(self):
        ts = pd.date_range("2026-01-01", periods=1000, freq="30min")
        features = build_cyclical_features(ts)
        assert (features >= -1.0).all().all()
        assert (features <= 1.0).all().all()

    def test_midnight_sin_near_zero(self):
        ts = pd.to_datetime(["2026-03-18 00:00:00"])
        features = build_cyclical_features(ts)
        assert abs(features["hour_sin"].iloc[0]) < 1e-10

    def test_noon_sin_near_zero(self):
        ts = pd.to_datetime(["2026-03-18 12:00:00"])
        features = build_cyclical_features(ts)
        # sin(2*pi*12/24) = sin(pi) ≈ 0
        assert abs(features["hour_sin"].iloc[0]) < 1e-10

    def test_6am_sin_near_one(self):
        ts = pd.to_datetime(["2026-03-18 06:00:00"])
        features = build_cyclical_features(ts)
        # sin(2*pi*6/24) = sin(pi/2) = 1
        assert abs(features["hour_sin"].iloc[0] - 1.0) < 1e-10


# ── _infer_dc_name ───────────────────────────────────────────────────────


class TestInferDcName:
    def test_with_location_column(self):
        df = pd.DataFrame(
            {"location": ["Data-Center-1"] * 5, "carbon_intensity": range(5)}
        )
        assert _infer_dc_name(df) == "Data-Center-1"

    def test_without_location_column(self):
        df = pd.DataFrame({"carbon_intensity": range(5)})
        assert _infer_dc_name(df) is None

    def test_unknown_location(self):
        df = pd.DataFrame(
            {"location": ["Unknown-DC"] * 5, "carbon_intensity": range(5)}
        )
        assert _infer_dc_name(df) is None

    def test_multiple_locations_returns_none(self):
        df = pd.DataFrame(
            {
                "location": ["Data-Center-1", "Data-Center-2"],
                "carbon_intensity": [100, 200],
            }
        )
        assert _infer_dc_name(df) is None


# ── _predict_carbon_intensity ────────────────────────────────────────────


class TestPredictCarbonIntensity:
    def _make_historical(self, n_points=200):
        """Build a synthetic historical DataFrame with enough data for Ridge."""
        base = datetime(2026, 3, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=30 * i) for i in range(n_points)]
        # Sine wave + noise to give Ridge something to learn
        values = [
            150 + 50 * np.sin(2 * np.pi * i / 48) + np.random.uniform(-5, 5)
            for i in range(n_points)
        ]
        return pd.DataFrame({"timestamp": timestamps, "carbon_intensity": values})

    def test_insufficient_data(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=30 * i)
                    for i in range(50)
                ],
                "carbon_intensity": range(50),
            }
        )
        with pytest.raises(ValueError, match="Not enough carbon intensity data"):
            _predict_carbon_intensity(df)

    def test_output_shape(self):
        df = self._make_historical(200)
        result = _predict_carbon_intensity(df, dc_name=None)
        assert "ds" in result.columns
        assert "yhat" in result.columns
        assert len(result) == 2016

    def test_output_clipped(self):
        df = self._make_historical(200)
        result = _predict_carbon_intensity(df, dc_name=None)
        assert (result["yhat"] >= 0).all()
        assert (result["yhat"] <= 500).all()

    def test_timestamps_are_5min(self):
        df = self._make_historical(200)
        result = _predict_carbon_intensity(df, dc_name=None)
        diffs = result["ds"].diff().dropna()
        assert (diffs == pd.Timedelta(minutes=5)).all()
