"""Tests for synthetic load generation."""

from datetime import datetime

from data.generate_history import MAX_CAPACITY, generate_load


class TestGenerateLoad:
    def test_output_non_negative(self):
        ts = datetime(2026, 3, 18, 10, 0)
        assert generate_load(ts, 0) >= 0

    def test_output_within_capacity(self):
        ts = datetime(2026, 3, 18, 10, 0)
        max_flos = MAX_CAPACITY * 4.92e15
        for dc_idx in range(5):
            val = generate_load(ts, dc_idx)
            assert 0 <= val <= max_flos

    def test_returns_flos(self):
        ts = datetime(2026, 3, 18, 10, 0)
        val = generate_load(ts, 0)
        # Should be in the FLOs scale (> 1e15)
        assert val > 1e14

    def test_weekday_peak_higher_than_night(self):
        """Weekday 10am should produce significantly higher load than 3am."""
        peak = datetime(2026, 3, 18, 10, 0)  # Wednesday 10am
        night = datetime(2026, 3, 18, 3, 0)  # Wednesday 3am

        peak_avg = sum(generate_load(peak, 0) for _ in range(50)) / 50
        night_avg = sum(generate_load(night, 0) for _ in range(50)) / 50
        assert peak_avg > night_avg

    def test_dc_index_varies_output(self):
        """Different DC indices should produce different outputs."""
        ts = datetime(2026, 3, 18, 10, 0)
        vals = {generate_load(ts, i) for i in range(3)}
        # With noise, exact equality is unlikely; at minimum offsets differ
        assert len(vals) >= 2
