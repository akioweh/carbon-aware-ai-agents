#!/usr/bin/env python3
"""
Carbon Intensity Data Collector

Collects carbon intensity data from the UK Carbon Intensity API
every 5 minutes, storing results in SQLite database.

On startup, backfills the last 7 days of data at 30-minute granularity
before entering the regular collection loop.

Designed to run indefinitely on a server (e.g., Oracle Cloud VM).
"""

import sqlite3
import requests
import time
import shutil
import schedule
import signal
import os
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
API_BASE_URL = "https://api.carbonintensity.org.uk"
REGIONS = {
    3: "North West England",
    4: "North East England",
    5: "South Yorkshire",
    13: "London",
    14: "South East England",
}
DB_PATH = Path(os.environ.get("CARBON_DB_PATH", Path(__file__).parent / "carbon_intensity.db"))
INTERVAL_MINUTES = int(os.environ.get("CARBON_INTERVAL_MINUTES", 30))
BACKFILL_DAYS = int(os.environ.get("BACKFILL_DAYS", 7))

# Graceful shutdown flag
_shutdown_requested = False


def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS regions (
            region_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS carbon_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER NOT NULL,
            timestamp_from TEXT NOT NULL,
            timestamp_to TEXT NOT NULL,
            actual INTEGER,
            index_value TEXT,
            collected_at TEXT NOT NULL,
            FOREIGN KEY (region_id) REFERENCES regions(region_id)
        );

        CREATE TABLE IF NOT EXISTS generation_mix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id INTEGER NOT NULL,
            fuel TEXT NOT NULL,
            percentage REAL NOT NULL,
            FOREIGN KEY (reading_id) REFERENCES carbon_readings(id)
        );

        CREATE INDEX IF NOT EXISTS idx_readings_region
            ON carbon_readings(region_id);
        CREATE INDEX IF NOT EXISTS idx_readings_timestamp
            ON carbon_readings(timestamp_from);
    """)

    for region_id, name in REGIONS.items():
        conn.execute(
            "INSERT OR IGNORE INTO regions (region_id, name) VALUES (?, ?)",
            (region_id, name)
        )

    conn.commit()
    return conn


def fetch_regional_intensity(from_str: str, to_str: str) -> dict | None:
    """Fetch carbon intensity for all regions in a time range."""
    url = f"{API_BASE_URL}/regional/intensity/{from_str}/{to_str}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  Error fetching {from_str} -> {to_str}: {e}")
        return None


def fetch_current_regional() -> dict | None:
    """Fetch current carbon intensity for all regions."""
    url = f"{API_BASE_URL}/regional"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  Error fetching current regional data: {e}")
        return None


def store_regional_slot(conn: sqlite3.Connection, slot: dict) -> int:
    """Store one time slot's data for all tracked regions. Returns count of rows stored."""
    collected_at = datetime.utcnow().isoformat()
    ts_from = slot.get("from", "")
    ts_to = slot.get("to", "")
    stored = 0

    for region in slot.get("regions", []):
        rid = region.get("regionid")
        if rid not in REGIONS:
            continue

        intensity = region.get("intensity", {})
        forecast = intensity.get("forecast")
        index_val = intensity.get("index")
        generationmix = region.get("generationmix", [])

        # Skip if we already have this exact reading
        existing = conn.execute(
            "SELECT id FROM carbon_readings WHERE region_id = ? AND timestamp_from = ? AND actual IS NOT NULL",
            (rid, ts_from)
        ).fetchone()
        if existing:
            continue

        # Update existing row (from old collector with NULL actual) or insert new
        updated = conn.execute(
            "UPDATE carbon_readings SET actual = ?, index_value = ? WHERE region_id = ? AND timestamp_from = ? AND actual IS NULL",
            (forecast, index_val, rid, ts_from)
        )

        if updated.rowcount == 0:
            cursor = conn.execute(
                """INSERT INTO carbon_readings
                   (region_id, timestamp_from, timestamp_to, actual, index_value, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (rid, ts_from, ts_to, forecast, index_val, collected_at)
            )
            reading_id = cursor.lastrowid

            for mix in generationmix:
                conn.execute(
                    "INSERT INTO generation_mix (reading_id, fuel, percentage) VALUES (?, ?, ?)",
                    (reading_id, mix.get("fuel", ""), mix.get("perc", 0))
                )

        stored += 1

    return stored


def backfill(conn: sqlite3.Connection, days: int = BACKFILL_DAYS) -> None:
    """Backfill the last N days of data at 30-minute granularity."""
    print(f"Backfilling last {days} days of data...")

    end = datetime.utcnow()
    start = end - timedelta(days=days)
    current = start
    total_stored = 0

    while current < end:
        next_day = min(current + timedelta(days=1), end)
        from_str = current.strftime('%Y-%m-%dT%H:%MZ')
        to_str = next_day.strftime('%Y-%m-%dT%H:%MZ')

        data = fetch_regional_intensity(from_str, to_str)
        if data:
            day_stored = 0
            for slot in data.get("data", []):
                day_stored += store_regional_slot(conn, slot)
            conn.commit()
            total_stored += day_stored
            print(f"  {current.strftime('%b %d')}: {day_stored} readings stored")
        else:
            print(f"  {current.strftime('%b %d')}: FAILED")

        current = next_day
        time.sleep(0.5)

    print(f"Backfill complete: {total_stored} readings stored")


def collect_current(conn: sqlite3.Connection) -> None:
    """Fetch and store current data for all regions."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collecting current data...")

    data = fetch_current_regional()
    if not data:
        print("  Failed to fetch current data")
        return

    # The /regional endpoint returns data nested differently
    regions_data = data.get("data", [{}])[0].get("regions", [])
    if not regions_data:
        print("  No region data in response")
        return

    # Build a slot-like structure to reuse store_regional_slot
    slot = {
        "from": data.get("data", [{}])[0].get("from", ""),
        "to": data.get("data", [{}])[0].get("to", ""),
        "regions": regions_data,
    }
    stored = store_regional_slot(conn, slot)
    conn.commit()
    print(f"  Stored {stored} readings. Total: {get_reading_count(conn)}")


def dump_database(db_path: Path, output_path: Path = None) -> Path:
    """Create a copy of the database file."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = db_path.parent / f"carbon_intensity_dump_{timestamp}.db"

    shutil.copy2(db_path, output_path)
    print(f"Database dumped to: {output_path}")
    return output_path


def get_reading_count(conn: sqlite3.Connection) -> int:
    """Get total number of readings."""
    cursor = conn.execute("SELECT COUNT(*) FROM carbon_readings")
    return cursor.fetchone()[0]


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    print(f"\n\nReceived {sig_name}, shutting down gracefully...")
    _shutdown_requested = True


def run_collector():
    """Main collection loop - runs indefinitely until stopped."""
    global _shutdown_requested

    print("Carbon Intensity Data Collector")
    print(f"Database: {DB_PATH}")
    print(f"Interval: {INTERVAL_MINUTES} minutes")
    print(f"Mode: Continuous (runs indefinitely)")
    print(f"Regions: {', '.join(REGIONS.values())}")

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    conn = init_database(DB_PATH)
    start_time = datetime.now()
    print(f"\nStarted at: {start_time}")
    
    # Backfill last 7 days on startup
    backfill(conn)
    print("Send SIGTERM or press Ctrl+C to stop.\n")

    def job():
        collect_current(conn)

    # Run immediately, then schedule at interval
    job()
    schedule.every(INTERVAL_MINUTES).minutes.do(job)

    # Main loop - runs until shutdown requested
    while not _shutdown_requested:
        schedule.run_pending()
        time.sleep(1)

    # Cleanup
    print(f"\nTotal readings collected: {get_reading_count(conn)}")
    conn.close()
    print("Database connection closed. Goodbye!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "dump":
            if DB_PATH.exists():
                dump_database(DB_PATH)
            else:
                print(f"Database not found: {DB_PATH}")
        elif sys.argv[1] == "stats":
            if DB_PATH.exists():
                conn = sqlite3.connect(DB_PATH)
                print(f"Total readings: {get_reading_count(conn)}")
                conn.close()
            else:
                print(f"Database not found: {DB_PATH}")
        elif sys.argv[1] == "backfill":
            if DB_PATH.exists():
                conn = init_database(DB_PATH)
                days = int(sys.argv[2]) if len(sys.argv) > 2 else BACKFILL_DAYS
                backfill(conn, days)
                conn.close()
            else:
                print(f"Database not found: {DB_PATH}")
    else:
        run_collector()
