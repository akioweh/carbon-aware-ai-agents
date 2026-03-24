"""Tests for the RidgeFull (v2) predictor — feature engineering and pipeline."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from predictors.ridge_enhanced import (
    DC_REGION_MAP,
    _predict_ci,
    build_temporal_features,
    get_next_week_carbon_intensity,
)


# ── build_temporal_features ─────────────────────────────────────────────


class TestTemporalFeatures:
    def test_output_shape(self):
        ts = pd.date_range('2026-03-18', periods=48, freq='30min')
        features = build_temporal_features(ts.values)
        # 22 Fourier features
        assert features.shape == (48, 22)

    def test_values_in_range(self):
        ts = pd.date_range('2026-01-01', periods=1000, freq='30min')
        features = build_temporal_features(ts.values)
        assert np.all(features >= -1.0)
        assert np.all(features <= 1.0)


# ── DC_REGION_MAP ───────────────────────────────────────────────────────


class TestDcRegionMap:
    def test_all_dcs_present(self):
        for i in range(1, 6):
            assert f'Data-Center-{i}' in DC_REGION_MAP

    def test_map_values_have_coords(self):
        for dc_name, (rid, name, lat, lon) in DC_REGION_MAP.items():
            assert isinstance(rid, int)
            assert isinstance(name, str)
            assert -90 <= lat <= 90
            assert -180 <= lon <= 180

    def test_known_dc_resolves(self):
        df = pd.DataFrame({'location': ['Data-Center-1'] * 5, 'carbon_intensity': range(5)})
        locs = df['location'].dropna().unique()
        assert len(locs) == 1 and locs[0] in DC_REGION_MAP

    def test_unknown_dc_not_in_map(self):
        assert 'Unknown-DC' not in DC_REGION_MAP

    def test_multiple_locations_not_resolved(self):
        df = pd.DataFrame(
            {
                'location': ['Data-Center-1', 'Data-Center-2'],
                'carbon_intensity': [100, 200],
            }
        )
        locs = df['location'].dropna().unique()
        # Multiple locations → should not resolve to a single DC
        assert len(locs) != 1


# ── _predict_ci ─────────────────────────────────────────────────────────


class TestPredictCi:
    def _make_historical(self, n_points=200):
        """Build a synthetic historical DataFrame with enough data for RidgeFull."""
        base = datetime(2026, 3, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=30 * i) for i in range(n_points)]
        values = [150 + 50 * np.sin(2 * np.pi * i / 48) + np.random.uniform(-5, 5) for i in range(n_points)]
        return pd.DataFrame({'timestamp': timestamps, 'carbon_intensity': values})

    def test_insufficient_data(self):
        df = pd.DataFrame(
            {
                'timestamp': [datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=30 * i) for i in range(50)],
                'carbon_intensity': range(50),
            }
        )
        with pytest.raises(ValueError, match='Need >= 96 observations'):
            _predict_ci(df)

    def test_output_shape(self):
        df = self._make_historical(200)
        result = _predict_ci(df, dc_name=None)
        assert 'ds' in result.columns
        assert 'yhat' in result.columns
        assert len(result) == 2016

    def test_output_clipped(self):
        df = self._make_historical(200)
        result = _predict_ci(df, dc_name=None)
        assert (result['yhat'] >= 0).all()
        assert (result['yhat'] <= 500).all()

    def test_timestamps_are_5min(self):
        df = self._make_historical(200)
        result = _predict_ci(df, dc_name=None)
        diffs = result['ds'].diff().dropna()
        assert (diffs == pd.Timedelta(minutes=5)).all()


# ── get_next_week_carbon_intensity (public API) ─────────────────────────


class TestGetNextWeekCarbonIntensity:
    def _make_historical(self, n_points=200):
        base = datetime(2026, 3, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=30 * i) for i in range(n_points)]
        values = [150 + 50 * np.sin(2 * np.pi * i / 48) + np.random.uniform(-5, 5) for i in range(n_points)]
        return pd.DataFrame({'timestamp': timestamps, 'carbon_intensity': values})

    def test_without_location(self):
        df = self._make_historical(200)
        result = get_next_week_carbon_intensity(df)
        assert len(result) == 2016

    def test_with_location_column(self):
        df = self._make_historical(200)
        df['location'] = 'Data-Center-1'
        result = get_next_week_carbon_intensity(df)
        assert len(result) == 2016

    def test_with_unknown_location(self):
        df = self._make_historical(200)
        df['location'] = 'Unknown-DC'
        result = get_next_week_carbon_intensity(df)
        assert len(result) == 2016
