#!/usr/bin/env python3
"""
Carbon Intensity Data Collector

Collects carbon intensity data from the UK Carbon Intensity API
every 5 minutes, storing results in SQLite database.

Designed to run indefinitely on a server (e.g., Oracle Cloud VM).
"""

import sqlite3
import requests
import time
import shutil
import schedule
import signal
import os
from datetime import datetime
from pathlib import Path

# Configuration
API_BASE_URL = "https://api.carbonintensity.org.uk/regional/regionid"
REGIONS = {
    1: "North Scotland",
    2: "South Scotland",
    3: "North West England",
    4: "North East England",
    13: "London",
}
DB_PATH = Path(os.environ.get("CARBON_DB_PATH", Path(__file__).parent / "carbon_intensity.db"))
INTERVAL_MINUTES = int(os.environ.get("CARBON_INTERVAL_MINUTES", 5))

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

    # Insert regions
    for region_id, name in REGIONS.items():
        conn.execute(
            "INSERT OR IGNORE INTO regions (region_id, name) VALUES (?, ?)",
            (region_id, name)
        )

    conn.commit()
    return conn


def fetch_region_data(region_id: int) -> dict | None:
    """Fetch carbon intensity data for a specific region."""
    url = f"{API_BASE_URL}/{region_id}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"  Error fetching region {region_id}: {e}")
        return None


def store_reading(conn: sqlite3.Connection, region_id: int, data: dict) -> None:
    """Store a carbon intensity reading in the database."""
    collected_at = datetime.utcnow().isoformat()

    try:
        region_data = data.get("data", [{}])[0]
        intensity = region_data.get("data", [{}])[0].get("intensity", {})
        generationmix = region_data.get("data", [{}])[0].get("generationmix", [])

        cursor = conn.execute(
            """
            INSERT INTO carbon_readings
            (region_id, timestamp_from, timestamp_to, actual, index_value, collected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                region_id,
                region_data.get("data", [{}])[0].get("from", ""),
                region_data.get("data", [{}])[0].get("to", ""),
                intensity.get("actual"),
                intensity.get("index"),
                collected_at,
            )
        )

        reading_id = cursor.lastrowid

        for mix in generationmix:
            conn.execute(
                """
                INSERT INTO generation_mix (reading_id, fuel, percentage)
                VALUES (?, ?, ?)
                """,
                (reading_id, mix.get("fuel", ""), mix.get("perc", 0))
            )

        conn.commit()
    except (KeyError, IndexError) as e:
        print(f"  Error parsing data for region {region_id}: {e}")


def collect_all_regions(conn: sqlite3.Connection) -> None:
    """Fetch and store data for all regions."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collecting data...")

    for region_id, region_name in REGIONS.items():
        data = fetch_region_data(region_id)
        if data:
            store_reading(conn, region_id, data)
            print(f"  Stored: {region_name}")
        time.sleep(0.5)  # Small delay between API calls


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
    print("Send SIGTERM or press Ctrl+C to stop.\n")

    def job():
        collect_all_regions(conn)
        print(f"  Total readings: {get_reading_count(conn)}")

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
            # Just dump existing database
            if DB_PATH.exists():
                dump_database(DB_PATH)
            else:
                print(f"Database not found: {DB_PATH}")
        elif sys.argv[1] == "stats":
            # Show reading count
            if DB_PATH.exists():
                conn = sqlite3.connect(DB_PATH)
                print(f"Total readings: {get_reading_count(conn)}")
                conn.close()
            else:
                print(f"Database not found: {DB_PATH}")
    else:
        run_collector()
