"""Shared fixtures for stats test suite."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure stats/ is on sys.path so bare imports (db_utils, config, etc.) work.
STATS_DIR = Path(__file__).resolve().parent.parent
if str(STATS_DIR) not in sys.path:
    sys.path.insert(0, str(STATS_DIR))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Temporary cache.db with schema and seeded datacenters."""
    db_file = tmp_path / 'cache.db'
    monkeypatch.setattr('db_utils.DB_FILE', db_file)
    import db_utils

    db_utils.initialize_db()
    return db_file


@pytest.fixture
def tmp_carbon_db(tmp_path, monkeypatch):
    """Temporary carbon_intensity.db with schema and regions."""
    db_file = tmp_path / 'carbon_intensity.db'
    monkeypatch.setattr('db_utils.CARBON_DB_FILE', db_file)
    from data.carbon_collector import init_database

    conn = init_database(db_file)
    conn.close()
    return db_file


@pytest.fixture
def sample_history():
    """48 hours of 30-min historical data for Data-Center-1."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=48)
    entries = []
    t = start
    i = 0
    while t <= now:
        entries.append(
            {
                'location': 'Data-Center-1',
                'timestamp': t,
                'load': 50.0 + 10.0 * (i % 10),
                'carbon_intensity': 200.0 + 5.0 * (i % 20),
            }
        )
        t += timedelta(minutes=30)
        i += 1
    return entries


@pytest.fixture
def seeded_db(tmp_db, sample_history):
    """tmp_db with sample historical data already inserted."""
    import db_utils

    db_utils.insert_historical_data_bulk(sample_history)
    return tmp_db


@pytest.fixture
def client(tmp_db):
    """FastAPI TestClient wired to a temp DB (no background threads)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import router

    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app)
