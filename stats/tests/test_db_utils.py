"""Tests for db_utils — database CRUD, caching, and sync."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import db_utils


# ── Schema & Initialization ─────────────────────────────────────────────


class TestInitializeDb:
    def test_creates_all_tables(self, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "predictions" in tables
        assert "historical_data" in tables
        assert "historical_cache" in tables
        assert "datacenters" in tables

    def test_seeds_all_datacenters(self, tmp_db):
        dcs = db_utils.get_datacenters(include_inactive=True)
        assert len(dcs) == len(db_utils.DEFAULT_DATACENTERS)
        ids = {dc["id"] for dc in dcs}
        assert "Data-Center-1" in ids

    def test_idempotent(self, tmp_db):
        db_utils.initialize_db()
        dcs = db_utils.get_datacenters(include_inactive=True)
        assert len(dcs) == len(db_utils.DEFAULT_DATACENTERS)

    def test_wal_mode_enabled(self, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# ── Datacenter CRUD ──────────────────────────────────────────────────────


class TestDatacenterCrud:
    def test_get_all(self, tmp_db):
        dcs = db_utils.get_datacenters(include_inactive=True)
        assert any(dc["active"] for dc in dcs)
        assert any(not dc["active"] for dc in dcs)

    def test_get_active_only(self, tmp_db):
        dcs = db_utils.get_datacenters(include_inactive=False)
        assert len(dcs) > 0
        assert all(dc["active"] for dc in dcs)

    def test_get_by_id(self, tmp_db):
        dc = db_utils.get_datacenter("Data-Center-1")
        assert dc is not None
        assert dc["id"] == "Data-Center-1"
        assert dc["name"] == "London"
        assert dc["region_id"] == 13
        assert dc["latitude"] == 51.51

    def test_get_by_id_not_found(self, tmp_db):
        assert db_utils.get_datacenter("nonexistent") is None

    def test_set_active(self, tmp_db):
        dc = db_utils.get_datacenter("Data-Center-6")
        assert not dc["active"]

        assert db_utils.set_datacenter_active("Data-Center-6", True) is True
        assert db_utils.get_datacenter("Data-Center-6")["active"] is True

    def test_set_active_missing_returns_false(self, tmp_db):
        assert db_utils.set_datacenter_active("nonexistent", True) is False

    def test_get_all_ids(self, tmp_db):
        ids = db_utils.get_all_datacenter_ids(include_inactive=True)
        assert isinstance(ids, list)
        assert len(ids) == len(db_utils.DEFAULT_DATACENTERS)
        assert "Data-Center-1" in ids

    def test_get_active_ids_subset(self, tmp_db):
        active = db_utils.get_active_datacenter_ids()
        all_ids = db_utils.get_all_datacenter_ids()
        assert len(active) <= len(all_ids)
        assert all(dc_id in all_ids for dc_id in active)

    def test_ordered_by_region(self, tmp_db):
        dcs = db_utils.get_datacenters(include_inactive=True)
        region_ids = [dc["region_id"] for dc in dcs]
        assert region_ids == sorted(region_ids)


# ── Prediction Cache ─────────────────────────────────────────────────────


class TestPredictionCache:
    def test_save_and_get(self, tmp_db):
        data = {"metric": "load", "values": [1, 2, 3]}
        db_utils.save_prediction("test_key", data)
        assert db_utils.get_cached_prediction("test_key") == data

    def test_expired_returns_none(self, tmp_db, monkeypatch):
        db_utils.save_prediction("expired", {"x": 1})
        monkeypatch.setattr("db_utils.PREDICTION_CACHE_TTL", 0)
        assert db_utils.get_cached_prediction("expired") is None

    def test_missing_returns_none(self, tmp_db):
        assert db_utils.get_cached_prediction("no_such_key") is None

    def test_overwrite(self, tmp_db):
        db_utils.save_prediction("key", {"v": 1})
        db_utils.save_prediction("key", {"v": 2})
        assert db_utils.get_cached_prediction("key") == {"v": 2}


# ── Historical Data ──────────────────────────────────────────────────────


class TestHistoricalData:
    def test_insert_and_get(self, tmp_db):
        ts = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        db_utils.insert_historical_data("Data-Center-1", ts, 100.0, 250.0)

        rows = db_utils.get_historical_data("Data-Center-1")
        assert len(rows) == 1
        assert rows[0]["load"] == 100.0
        assert rows[0]["carbon_intensity"] == 250.0

    def test_bulk_insert(self, tmp_db):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        data = [
            {
                "location": "Data-Center-1",
                "timestamp": base + timedelta(minutes=30 * i),
                "load": float(i),
                "carbon_intensity": 200.0 + i,
            }
            for i in range(10)
        ]
        db_utils.insert_historical_data_bulk(data)
        rows = db_utils.get_historical_data("Data-Center-1")
        assert len(rows) == 10

    def test_filter_start_and_end(self, tmp_db):
        base = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        data = [
            {
                "location": "Data-Center-1",
                "timestamp": base + timedelta(hours=i),
                "load": float(i),
                "carbon_intensity": 200.0,
            }
            for i in range(24)
        ]
        db_utils.insert_historical_data_bulk(data)

        start = base + timedelta(hours=6)
        end = base + timedelta(hours=12)

        rows = db_utils.get_historical_data("Data-Center-1", start, end)
        assert len(rows) == 7  # hours 6..12 inclusive
        assert all(start <= r["timestamp"] <= end for r in rows)

    def test_filter_start_only(self, tmp_db):
        base = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        data = [
            {
                "location": "Data-Center-1",
                "timestamp": base + timedelta(hours=i),
                "load": float(i),
                "carbon_intensity": 200.0,
            }
            for i in range(24)
        ]
        db_utils.insert_historical_data_bulk(data)
        rows = db_utils.get_historical_data(
            "Data-Center-1", start_time=base + timedelta(hours=20)
        )
        assert len(rows) == 4  # hours 20..23

    def test_filter_end_only(self, tmp_db):
        base = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
        data = [
            {
                "location": "Data-Center-1",
                "timestamp": base + timedelta(hours=i),
                "load": float(i),
                "carbon_intensity": 200.0,
            }
            for i in range(24)
        ]
        db_utils.insert_historical_data_bulk(data)
        rows = db_utils.get_historical_data(
            "Data-Center-1", end_time=base + timedelta(hours=3)
        )
        assert len(rows) == 4  # hours 0..3

    def test_empty_location(self, tmp_db):
        rows = db_utils.get_historical_data("empty-location")
        assert rows == []

    def test_latest_timestamp(self, tmp_db):
        base = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        later = base + timedelta(hours=2)
        db_utils.insert_historical_data("Data-Center-1", base, 100.0, 200.0)
        db_utils.insert_historical_data("Data-Center-1", later, 110.0, 210.0)
        assert db_utils.get_latest_timestamp("Data-Center-1") == later

    def test_latest_timestamp_empty(self, tmp_db):
        assert db_utils.get_latest_timestamp("Data-Center-1") is None

    def test_count(self, tmp_db):
        assert db_utils.count_historical_data() == 0
        ts = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        db_utils.insert_historical_data("Data-Center-1", ts, 100.0, 200.0)
        assert db_utils.count_historical_data() == 1

    def test_delete_old(self, tmp_db):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        db_utils.insert_historical_data("Data-Center-1", old, 1.0, 1.0)
        db_utils.insert_historical_data("Data-Center-1", recent, 2.0, 2.0)
        db_utils.delete_old_data(days=30)
        assert db_utils.count_historical_data() == 1

    def test_upsert_preserves_load(self, tmp_db):
        ts = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        db_utils.insert_historical_data("Data-Center-1", ts, 100.0, 200.0)

        db_utils._upsert_carbon_intensity_bulk(
            [{"location": "Data-Center-1", "timestamp": ts, "carbon_intensity": 999.0}]
        )

        rows = db_utils.get_historical_data("Data-Center-1")
        assert rows[0]["load"] == 100.0
        assert rows[0]["carbon_intensity"] == 999.0


# ── Historical Cache ─────────────────────────────────────────────────────


class TestHistoricalCache:
    def test_save_and_get(self, tmp_db):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        entries = [
            {
                "timestamp": now - timedelta(minutes=5 * i),
                "load": float(i),
                "carbon_intensity": 200.0,
            }
            for i in range(10)
        ]
        db_utils.save_historical_cache("Data-Center-1", entries)

        cached = db_utils.get_historical_cache(
            "Data-Center-1", now - timedelta(hours=1), now
        )
        assert cached is not None
        assert len(cached) == 10

    def test_empty_returns_none(self, tmp_db):
        now = datetime.now(timezone.utc)
        cached = db_utils.get_historical_cache(
            "Data-Center-1", now - timedelta(hours=1), now
        )
        assert cached is None

    def test_replaces_on_save(self, tmp_db):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        entries1 = [
            {"timestamp": now, "load": 1.0, "carbon_intensity": 100.0}
        ]
        entries2 = [
            {"timestamp": now, "load": 2.0, "carbon_intensity": 200.0}
        ]
        db_utils.save_historical_cache("Data-Center-1", entries1)
        db_utils.save_historical_cache("Data-Center-1", entries2)

        cached = db_utils.get_historical_cache(
            "Data-Center-1", now - timedelta(hours=1), now + timedelta(hours=1)
        )
        assert len(cached) == 1
        assert cached[0]["load"] == 2.0


# ── Carbon Sync ──────────────────────────────────────────────────────────


class TestCarbonSync:
    def test_has_carbon_data_false_when_missing(self, tmp_db, monkeypatch):
        from pathlib import Path

        monkeypatch.setattr(
            "db_utils.CARBON_DB_FILE", Path("/nonexistent/carbon.db")
        )
        assert db_utils.has_carbon_data() is False

    def test_has_carbon_data_true(self, tmp_db, tmp_carbon_db):
        import sqlite3

        # Insert a reading so has_carbon_data returns True
        with sqlite3.connect(tmp_carbon_db) as conn:
            conn.execute(
                """INSERT INTO carbon_readings
                   (region_id, timestamp_from, timestamp_to, actual, index_value, collected_at)
                   VALUES (13, '2026-03-15T12:00Z', '2026-03-15T12:30Z', 200, 'moderate', '2026-03-15T12:00Z')"""
            )
        assert db_utils.has_carbon_data() is True

    def test_sync_maps_regions_to_datacenters(self, tmp_db, tmp_carbon_db):
        import sqlite3

        ts_from = "2026-03-15T12:00Z"
        ts_to = "2026-03-15T12:30Z"

        # Insert readings for region 13 (London → Data-Center-1)
        with sqlite3.connect(tmp_carbon_db) as conn:
            conn.execute(
                """INSERT INTO carbon_readings
                   (region_id, timestamp_from, timestamp_to, actual, index_value, collected_at)
                   VALUES (13, ?, ?, 185, 'moderate', '2026-03-15T12:00Z')""",
                (ts_from, ts_to),
            )

        count = db_utils.sync_carbon_to_historical()
        assert count == 1

        rows = db_utils.get_historical_data("Data-Center-1")
        assert len(rows) == 1
        assert rows[0]["carbon_intensity"] == 185
