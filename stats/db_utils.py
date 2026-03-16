"""Database utilities for managing historical time-series data."""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

DB_FILE = Path(__file__).parent / 'cache.db'
CARBON_DB_FILE = Path(
    os.environ.get('CARBON_DB_PATH', Path(__file__).parent / 'carbon_intensity.db')
)

# Map UK regions to Data Center locations
UK_REGION_TO_DC = {
    13: 'Data-Center-1',  # London
    14: 'Data-Center-2',  # South East England
    5: 'Data-Center-3',  # South Yorkshire
    3: 'Data-Center-4',  # North West England
    4: 'Data-Center-5',  # North East England
}


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_FILE)
    return conn


def initialize_db():
    """Initialize the SQLite database for caching and historical data."""
    with sqlite3.connect(DB_FILE) as conn:
        # Enable WAL mode for better concurrent access
        conn.execute('PRAGMA journal_mode=WAL')

        # Check if historical_data table exists and has greenness column
        cursor = conn.execute('PRAGMA table_info(historical_data)')
        columns = [col[1] for col in cursor.fetchall()]
        if 'greenness' in columns and 'carbon_intensity' not in columns:
            # Migrate old schema
            conn.execute(
                'ALTER TABLE historical_data RENAME COLUMN greenness TO carbon_intensity'
            )

        # Predictions cache table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                key TEXT PRIMARY KEY,
                data TEXT,
                timestamp REAL
            )
        """)

        # Historical time-series data table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historical_data (
                location TEXT NOT NULL,
                timestamp REAL NOT NULL,
                load REAL NOT NULL,
                carbon_intensity REAL NOT NULL,
                PRIMARY KEY (location, timestamp)
            )
        """)

        # Create indexes for efficient querying
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_historical_timestamp 
            ON historical_data(timestamp)
        """)


def get_cached_prediction(key: str) -> Optional[dict]:
    """Get cached prediction if it exists and is less than 5 minutes old."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                'SELECT data, timestamp FROM predictions WHERE key = ?', (key,)
            )
            row = cursor.fetchone()

            if row:
                data_json, timestamp = row
                # Check if cache is fresh (less than 5 minutes old)
                if time.time() - timestamp < 300:  # 300 seconds = 5 minutes
                    return json.loads(data_json)
    except sqlite3.Error as e:
        print(f'Cache read error: {e}')
    return None


def save_prediction(key: str, data: dict):
    """Save prediction to cache with current timestamp."""
    try:
        with get_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO predictions (key, data, timestamp) VALUES (?, ?, ?)',
                (key, json.dumps(data), time.time()),
            )
    except sqlite3.Error as e:
        print(f'Cache write error: {e}')


def insert_historical_data(
    location: str, timestamp: datetime, load: float, carbon_intensity: float
):
    """Insert a single historical data point. Replaces if timestamp already exists."""
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO historical_data 
                   (location, timestamp, load, carbon_intensity) 
                   VALUES (?, ?, ?, ?)""",
                (location, timestamp.timestamp(), load, carbon_intensity),
            )
    except sqlite3.Error as e:
        print(f'Error inserting historical data: {e}')
        raise


def insert_historical_data_bulk(data: List[Dict]):
    """Insert multiple historical data points efficiently.

    Args:
        data: List of dicts with keys: location, timestamp, load, and carbon_intensity
    """
    try:
        with get_connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO historical_data
                   (location, timestamp, load, carbon_intensity)
                   VALUES (?, ?, ?, ?)""",
                [
                    (
                        d['location'],
                        d['timestamp'].timestamp(),
                        d['load'],
                        d['carbon_intensity'],
                    )
                    for d in data
                ],
            )
    except sqlite3.Error as e:
        print(f'Error inserting bulk historical data: {e}')
        raise


def get_historical_data(
    location: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[Dict]:
    """Get historical data for a location within optional time range.

    Args:
        location: Datacenter location identifier
        start_time: Optional start time filter
        end_time: Optional end time filter

    Returns:
        List of dicts with keys: timestamp (datetime), load, and optionally carbon_intensity
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute('PRAGMA table_info(historical_data)')
            select_cols = 'timestamp, load, carbon_intensity'

            if start_time and end_time:
                cursor = conn.execute(
                    f"""SELECT {select_cols}
                       FROM historical_data
                       WHERE location = ? AND timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp ASC""",
                    (location, start_time.timestamp(), end_time.timestamp()),
                )
            elif start_time:
                cursor = conn.execute(
                    f"""SELECT {select_cols}
                       FROM historical_data
                       WHERE location = ? AND timestamp >= ?
                       ORDER BY timestamp ASC""",
                    (location, start_time.timestamp()),
                )

                cursor = conn.execute(
                    f"""SELECT {select_cols}
                       FROM historical_data
                       WHERE location = ? AND timestamp >= ?
                       ORDER BY timestamp ASC""",
                    (location, start_time.timestamp()),
                )
            elif end_time:
                cursor = conn.execute(
                    f"""SELECT {select_cols}
                       FROM historical_data
                       WHERE location = ? AND timestamp <= ?
                       ORDER BY timestamp ASC""",
                    (location, end_time.timestamp()),
                )
            else:
                cursor = conn.execute(
                    f"""SELECT {select_cols}
                       FROM historical_data
                       WHERE location = ?
                       ORDER BY timestamp ASC""",
                    (location,),
                )

            rows = cursor.fetchall()
            return [
                {
                    'timestamp': datetime.fromtimestamp(row[0]),
                    'load': row[1],
                    'carbon_intensity': row[2],
                }
                for row in rows
            ]
    except sqlite3.Error as e:
        print(f'Error retrieving historical data: {e}')
        return []


def delete_old_data(days: int = 30):
    """Delete historical data older than specified number of days."""
    cutoff = datetime.now() - timedelta(days=days)
    with get_connection() as conn:
        cursor = conn.execute(
            'DELETE FROM historical_data WHERE timestamp < ?', (cutoff.timestamp(),)
        )
        deleted_count = cursor.rowcount
        print(f'Deleted {deleted_count} old historical data points')


def get_latest_timestamp(location: str) -> Optional[datetime]:
    """Get the timestamp of the most recent data point for a location."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT MAX(timestamp) FROM historical_data WHERE location = ?""",
                (location,),
            )
            result = cursor.fetchone()
            if result and result[0]:
                return datetime.fromtimestamp(result[0])
            return None
    except sqlite3.Error as e:
        print(f'Error getting latest timestamp: {e}')
        return None


def count_historical_data() -> int:
    """Get the total count of historical data points in the database."""
    try:
        with get_connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM historical_data')
            return cursor.fetchone()[0]
    except sqlite3.Error as e:
        print(f'Error counting historical data: {e}')
        return 0


# --- Carbon Intensity Database Functions ---


def get_carbon_db_connection():
    """Get a connection to the carbon intensity database."""
    if not CARBON_DB_FILE.exists():
        raise FileNotFoundError(
            f'Carbon intensity database not found: {CARBON_DB_FILE}'
        )
    conn = sqlite3.connect(CARBON_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_carbon_readings(
    region_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 10000,
) -> List[Dict]:
    """Get carbon intensity readings from the collector database.

    Args:
        region_id: Optional filter by UK region ID
        since: Optional filter for readings after this time
        limit: Maximum number of readings to return

    Returns:
        List of reading dicts with region_id, timestamp_from, actual, index_value
    """
    try:
        with get_carbon_db_connection() as conn:
            query = 'SELECT * FROM carbon_readings'
            params = []
            conditions = []

            if region_id is not None:
                conditions.append('region_id = ?')
                params.append(region_id)

            if since:
                conditions.append('timestamp_from >= ?')
                params.append(since.isoformat())

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            query += ' ORDER BY timestamp_from DESC LIMIT ?'
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except (sqlite3.Error, FileNotFoundError) as e:
        print(f'Error reading carbon database: {e}')
        return []


def sync_carbon_to_historical(days_back: int = 30) -> int:
    """Sync carbon intensity data to historical_data table.

    Reads from carbon_intensity.db, converts intensity to carbon_intensity,
    maps UK regions to Data Center locations, and inserts into cache.db.

    Args:
        days_back: How many days of data to sync

    Returns:
        Number of records synced
    """
    since = datetime.now() - timedelta(days=days_back)
    readings = get_carbon_readings(since=since, limit=50000)

    if not readings:
        print('No carbon readings found to sync')
        return 0

    # Convert readings to historical data format
    bulk_data = []
    for reading in readings:
        region_id = reading.get('region_id')
        if region_id not in UK_REGION_TO_DC:
            continue

        location = UK_REGION_TO_DC[region_id]
        carbon_intensity = reading.get('actual')

        if carbon_intensity is None:
            continue

        # Parse timestamp
        ts_str = reading.get('timestamp_from', '')
        try:
            # Handle ISO format with or without Z suffix
            ts_str = ts_str.replace('Z', '+00:00')
            timestamp = datetime.fromisoformat(ts_str)
        except ValueError:
            continue

        bulk_data.append(
            {
                'location': location,
                'timestamp': timestamp,
                'load': 50 * 1e12,  # TODO: stop hardcode dumb value
                'carbon_intensity': carbon_intensity,
            }
        )

    if bulk_data:
        insert_historical_data_bulk(bulk_data)
        print(f'Synced {len(bulk_data)} carbon readings to historical data')

    return len(bulk_data)


def get_carbon_reading_count() -> int:
    """Get total count of carbon intensity readings collected."""
    try:
        with get_carbon_db_connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM carbon_readings')
            return cursor.fetchone()[0]
    except (sqlite3.Error, FileNotFoundError) as e:
        print(f'Error counting carbon readings: {e}')
        return 0


def has_carbon_data() -> bool:
    """Check if carbon intensity database exists and has data."""
    if not CARBON_DB_FILE.exists():
        return False
    try:
        return get_carbon_reading_count() > 0
    except Exception:
        return False
