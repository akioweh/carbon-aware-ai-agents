"""Tests for background prediction and sync loops."""

import logging
from unittest.mock import MagicMock

import pytest


class _BreakLoop(Exception):
    """Raised by mock sleep to exit infinite loops."""


# ── prediction_loop ──────────────────────────────────────────────────────


class TestPredictionLoop:
    def test_single_successful_iteration(self, seeded_db, monkeypatch):
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr(
            "background.generate_next_week_load_prediction",
            lambda dc: {"data": []},
        )
        monkeypatch.setattr(
            "background.generate_next_week_carbon_intensity_prediction",
            lambda dc: {"data": []},
        )
        monkeypatch.setattr("background.refresh_historical_cache", lambda dc: None)

        with pytest.raises(_BreakLoop):
            background.prediction_loop()

    def test_handles_load_error_gracefully(self, tmp_db, monkeypatch):
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr(
            "background.generate_next_week_load_prediction",
            MagicMock(side_effect=RuntimeError("load failed")),
        )

        # Should not raise RuntimeError — it catches all exceptions
        with pytest.raises(_BreakLoop):
            background.prediction_loop()

    def test_handles_ci_valueerror(self, tmp_db, monkeypatch):
        """ValueError from CI prediction is caught separately (warning, not error)."""
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr(
            "background.generate_next_week_load_prediction",
            lambda dc: {"data": []},
        )
        monkeypatch.setattr(
            "background.generate_next_week_carbon_intensity_prediction",
            MagicMock(side_effect=ValueError("no CI data")),
        )
        monkeypatch.setattr("background.refresh_historical_cache", lambda dc: None)

        with pytest.raises(_BreakLoop):
            background.prediction_loop()

    def test_alerts_after_threshold(self, tmp_db, monkeypatch, caplog):
        import background

        threshold = 2
        monkeypatch.setattr("background.FAILURE_ALERT_THRESHOLD", threshold)
        monkeypatch.setattr(
            "background.generate_next_week_load_prediction",
            MagicMock(side_effect=RuntimeError("fail")),
        )

        iteration = [0]

        def counting_sleep(seconds):
            iteration[0] += 1
            if iteration[0] >= threshold + 1:
                raise _BreakLoop

        monkeypatch.setattr("background.time.sleep", counting_sleep)

        with pytest.raises(_BreakLoop), caplog.at_level(
            logging.CRITICAL, logger="stats.background"
        ):
            background.prediction_loop()

        critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert len(critical) > 0
        assert any("ALERT" in r.message for r in critical)

    def test_skips_when_no_datacenters(self, tmp_db, monkeypatch):
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr(
            "background.db_utils.get_all_datacenter_ids", lambda: []
        )

        with pytest.raises(_BreakLoop):
            background.prediction_loop()


# ── carbon_sync_loop ─────────────────────────────────────────────────────


class TestCarbonSyncLoop:
    def test_single_iteration_no_data(self, tmp_db, monkeypatch):
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr("background.db_utils.has_carbon_data", lambda: False)

        with pytest.raises(_BreakLoop):
            background.carbon_sync_loop()

    def test_handles_sync_error(self, tmp_db, monkeypatch):
        import background

        monkeypatch.setattr("background.time.sleep", MagicMock(side_effect=_BreakLoop))
        monkeypatch.setattr("background.db_utils.has_carbon_data", lambda: True)
        monkeypatch.setattr(
            "background.db_utils.sync_carbon_to_historical",
            MagicMock(side_effect=RuntimeError("sync fail")),
        )

        with pytest.raises(_BreakLoop):
            background.carbon_sync_loop()

    def test_alerts_after_threshold(self, tmp_db, monkeypatch, caplog):
        import background

        threshold = 2
        monkeypatch.setattr("background.FAILURE_ALERT_THRESHOLD", threshold)
        monkeypatch.setattr("background.db_utils.has_carbon_data", lambda: True)
        monkeypatch.setattr(
            "background.db_utils.sync_carbon_to_historical",
            MagicMock(side_effect=RuntimeError("fail")),
        )

        iteration = [0]

        def counting_sleep(seconds):
            iteration[0] += 1
            if iteration[0] >= threshold + 1:
                raise _BreakLoop

        monkeypatch.setattr("background.time.sleep", counting_sleep)

        with pytest.raises(_BreakLoop), caplog.at_level(
            logging.CRITICAL, logger="stats.background"
        ):
            background.carbon_sync_loop()

        critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert len(critical) > 0
