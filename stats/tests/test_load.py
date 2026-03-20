"""Tests for the load predictor."""

import pandas as pd
import pytest

from predictors.load import get_next_week_load


class TestGetNextWeekLoad:
    def _call(self, now=None):
        dummy_history = pd.DataFrame({"timestamp": [], "load": []})
        return get_next_week_load(dummy_history, now=now)

    def test_returns_2016_points(self):
        result = self._call()
        assert len(result) == 2016

    def test_columns(self):
        result = self._call()
        assert list(result.columns) == ["ds", "yhat"]

    def test_values_non_negative(self):
        result = self._call()
        assert (result["yhat"] >= 0).all()

    def test_5min_frequency(self):
        result = self._call()
        diffs = result["ds"].diff().dropna()
        assert (diffs == pd.Timedelta(minutes=5)).all()

    def test_custom_start(self):
        now = pd.Timestamp("2026-03-18 10:00:00")
        result = self._call(now=now)
        assert result["ds"].iloc[0] >= now
