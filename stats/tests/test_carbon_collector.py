"""Tests for carbon intensity collector — DB operations and data storage."""

import pytest

from data.carbon_collector import (
    REGIONS,
    _get_regions_with_data,
    get_latest_reading_timestamp,
    get_reading_count,
    init_database,
    store_regional_slot,
)


@pytest.fixture
def carbon_conn(tmp_path):
    """Fresh carbon_intensity.db connection with schema."""
    db = tmp_path / 'carbon.db'
    conn = init_database(db)
    yield conn
    conn.close()


# ── init_database ────────────────────────────────────────────────────────


class TestInitDatabase:
    def test_creates_tables(self, carbon_conn):
        tables = {row[0] for row in carbon_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'regions' in tables
        assert 'carbon_readings' in tables
        assert 'generation_mix' in tables

    def test_seeds_regions(self, carbon_conn):
        rows = carbon_conn.execute('SELECT COUNT(*) FROM regions').fetchone()
        assert rows[0] == len(REGIONS)

    def test_idempotent(self, tmp_path):
        db = tmp_path / 'carbon.db'
        conn1 = init_database(db)
        conn1.close()
        conn2 = init_database(db)
        rows = conn2.execute('SELECT COUNT(*) FROM regions').fetchone()
        assert rows[0] == len(REGIONS)
        conn2.close()


# ── store_regional_slot ──────────────────────────────────────────────────


def _make_slot(ts_from='2026-03-18T12:00Z', ts_to='2026-03-18T12:30Z'):
    """Build a minimal slot dict with one region."""
    return {
        'from': ts_from,
        'to': ts_to,
        'regions': [
            {
                'regionid': 13,
                'intensity': {'forecast': 185, 'index': 'moderate'},
                'generationmix': [
                    {'fuel': 'gas', 'perc': 40.0},
                    {'fuel': 'wind', 'perc': 30.0},
                ],
            }
        ],
    }


class TestStoreRegionalSlot:
    def test_stores_reading(self, carbon_conn):
        stored = store_regional_slot(carbon_conn, _make_slot())
        carbon_conn.commit()
        assert stored == 1
        assert get_reading_count(carbon_conn) == 1

    def test_stores_generation_mix(self, carbon_conn):
        store_regional_slot(carbon_conn, _make_slot())
        carbon_conn.commit()
        mix = carbon_conn.execute('SELECT COUNT(*) FROM generation_mix').fetchone()
        assert mix[0] == 2

    def test_skips_duplicate(self, carbon_conn):
        slot = _make_slot()
        store_regional_slot(carbon_conn, slot)
        carbon_conn.commit()
        # Same slot again should be skipped
        stored = store_regional_slot(carbon_conn, slot)
        assert stored == 0

    def test_skips_unknown_region(self, carbon_conn):
        slot = {
            'from': '2026-03-18T12:00Z',
            'to': '2026-03-18T12:30Z',
            'regions': [{'regionid': 999, 'intensity': {'forecast': 100, 'index': 'low'}}],
        }
        stored = store_regional_slot(carbon_conn, slot)
        assert stored == 0

    def test_multiple_regions(self, carbon_conn):
        slot = {
            'from': '2026-03-18T12:00Z',
            'to': '2026-03-18T12:30Z',
            'regions': [
                {
                    'regionid': rid,
                    'intensity': {'forecast': 100 + rid, 'index': 'moderate'},
                    'generationmix': [],
                }
                for rid in [1, 2, 3, 13]
            ],
        }
        stored = store_regional_slot(carbon_conn, slot)
        carbon_conn.commit()
        assert stored == 4


# ── get_latest_reading_timestamp ─────────────────────────────────────────


class TestLatestTimestamp:
    def test_empty_db(self, carbon_conn):
        assert get_latest_reading_timestamp(carbon_conn) is None

    def test_returns_most_recent(self, carbon_conn):
        store_regional_slot(carbon_conn, _make_slot('2026-03-18T12:00Z', '2026-03-18T12:30Z'))
        store_regional_slot(carbon_conn, _make_slot('2026-03-18T13:00Z', '2026-03-18T13:30Z'))
        carbon_conn.commit()

        latest = get_latest_reading_timestamp(carbon_conn)
        assert latest is not None
        assert latest.hour == 13


# ── _get_regions_with_data ───────────────────────────────────────────────


class TestRegionsWithData:
    def test_empty(self, carbon_conn):
        assert _get_regions_with_data(carbon_conn) == set()

    def test_returns_region_ids(self, carbon_conn):
        store_regional_slot(carbon_conn, _make_slot())
        carbon_conn.commit()
        regions = _get_regions_with_data(carbon_conn)
        assert 13 in regions


# ── get_reading_count ────────────────────────────────────────────────────


class TestReadingCount:
    def test_empty(self, carbon_conn):
        assert get_reading_count(carbon_conn) == 0

    def test_after_insert(self, carbon_conn):
        store_regional_slot(carbon_conn, _make_slot())
        carbon_conn.commit()
        assert get_reading_count(carbon_conn) == 1
