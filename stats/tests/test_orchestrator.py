"""Tests for the prediction orchestrator — upsampling, time windows, stitching."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from predictors.orchestrator import (
    _slice_cached_data,
    _upsample_historical,
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)

# ── _upsample_historical ────────────────────────────────────────────────


class TestUpsampleHistorical:
    def test_empty_input(self):
        assert _upsample_historical([]) == []

    def test_two_30min_points(self):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        entries = [
            {'timestamp': base, 'load': 100.0, 'carbon_intensity': 200.0},
            {
                'timestamp': base + timedelta(minutes=30),
                'load': 110.0,
                'carbon_intensity': 210.0,
            },
        ]
        result = _upsample_historical(entries)
        # 0, 5, 10, 15, 20, 25, 30 → 7 points
        assert len(result) == 7
        assert result[0]['load'] == 100.0
        assert result[-1]['load'] == 110.0
        # Intermediate points forward-filled from first obs
        assert result[1]['load'] == 100.0

    def test_fill_until_extends(self):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        entries = [{'timestamp': base, 'load': 50.0, 'carbon_intensity': 100.0}]
        fill = base + timedelta(minutes=15)
        result = _upsample_historical(entries, fill_until=fill)
        # base, +5, +10, +15 → 4 points
        assert len(result) == 4
        assert all(r['load'] == 50.0 for r in result)

    def test_preserves_carbon_intensity(self):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        entries = [
            {'timestamp': base, 'load': 10.0, 'carbon_intensity': 300.0},
            {
                'timestamp': base + timedelta(minutes=10),
                'load': 20.0,
                'carbon_intensity': 310.0,
            },
        ]
        result = _upsample_historical(entries)
        assert result[0]['carbon_intensity'] == 300.0

    def test_none_ci_stays_none(self):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        entries = [{'timestamp': base, 'load': 10.0, 'carbon_intensity': None}]
        result = _upsample_historical(entries)
        assert result[0]['carbon_intensity'] is None


# ── _slice_cached_data ───────────────────────────────────────────────────


class TestSliceCachedData:
    def _make_points(self, base, n):
        return [
            {
                'timestamp': (base + timedelta(hours=i)).isoformat(),
                'value': float(i),
            }
            for i in range(n)
        ]

    def test_within_bounds(self):
        base = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
        points = self._make_points(base, 10)
        start = base + timedelta(hours=3)
        end = base + timedelta(hours=7)
        result = _slice_cached_data(points, start, end)
        assert len(result) == 5

    def test_no_bounds(self):
        base = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
        points = self._make_points(base, 5)
        assert len(_slice_cached_data(points, None, None)) == 5

    def test_start_only(self):
        base = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
        points = self._make_points(base, 10)
        result = _slice_cached_data(points, base + timedelta(hours=8), None)
        assert len(result) == 2  # hours 8, 9


# ── generate_next_week_load_prediction ───────────────────────────────────


def test_load_prediction_no_history(tmp_db):
    with pytest.raises(ValueError, match='No history found'):
        generate_next_week_load_prediction('Data-Center-1')


def test_load_prediction_shape(seeded_db):
    result = generate_next_week_load_prediction('Data-Center-1')
    assert result['location_id'] == 'Data-Center-1'
    assert result['metric'] == 'forecast_load'
    assert result['unit'] == 'FLOs'
    assert len(result['data']) == 2016
    assert all(p['is_forecast'] for p in result['data'])
    assert all(p['value'] >= 0 for p in result['data'])
    assert all('capacity' in p for p in result['data'])


# ── generate_next_week_carbon_intensity_prediction ───────────────────────


def test_ci_prediction_no_history(tmp_db):
    with pytest.raises(ValueError, match='No history found'):
        generate_next_week_carbon_intensity_prediction('empty-location')
