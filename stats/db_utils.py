"""Database utilities for managing historical time-series data."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from config import CARBON_DB_FILE, DB_FILE, PREDICTION_CACHE_TTL

# Canonical set of datacenters seeded into cache.db.
# Keep Data-Center-1..5 mappings stable for scheduler compatibility.
# Coordinates added for weather API integration (Open-Meteo).
DEFAULT_DATACENTERS = [
    {
        'region_id': 13,
        'location_id': 'Data-Center-1',
        'name': 'London',
        'latitude': 51.51,
        'longitude': -0.13,
        'default_active': True,
    },
    {
        'region_id': 1,
        'location_id': 'Data-Center-2',
        'name': 'North Scotland',
        'latitude': 57.47,
        'longitude': -4.04,
        'default_active': True,
    },
    {
        'region_id': 2,
        'location_id': 'Data-Center-3',
        'name': 'South Scotland',
        'latitude': 55.31,
        'longitude': -3.54,
        'default_active': True,
    },
    {
        'region_id': 3,
        'location_id': 'Data-Center-4',
        'name': 'North West England',
        'latitude': 54.05,
        'longitude': -2.80,
        'default_active': True,
    },
    {
        'region_id': 4,
        'location_id': 'Data-Center-5',
        'name': 'North East England',
        'latitude': 54.97,
        'longitude': -1.61,
        'default_active': True,
    },
    {
        'region_id': 5,
        'location_id': 'Data-Center-6',
        'name': 'South Yorkshire',
        'latitude': 53.79,
        'longitude': -1.54,
        'default_active': False,
    },
    {
        'region_id': 6,
        'location_id': 'Data-Center-7',
        'name': 'North Wales, Merseyside and Cheshire',
        'latitude': 52.95,
        'longitude': -3.61,
        'default_active': False,
    },
    {
        'region_id': 7,
        'location_id': 'Data-Center-8',
        'name': 'South Wales',
        'latitude': 51.82,
        'longitude': -3.59,
        'default_active': False,
    },
    {
        'region_id': 8,
        'location_id': 'Data-Center-9',
        'name': 'West Midlands',
        'latitude': 52.51,
        'longitude': -2.01,
        'default_active': False,
    },
    {
        'region_id': 9,
        'location_id': 'Data-Center-10',
        'name': 'East Midlands',
        'latitude': 52.95,
        'longitude': -1.13,
        'default_active': False,
    },
    {
        'region_id': 10,
        'location_id': 'Data-Center-11',
        'name': 'East England',
        'latitude': 52.61,
        'longitude': 1.28,
        'default_active': False,
    },
    {
        'region_id': 11,
        'location_id': 'Data-Center-12',
        'name': 'South West England',
        'latitude': 50.71,
        'longitude': -3.53,
        'default_active': False,
    },
    {
        'region_id': 12,
        'location_id': 'Data-Center-13',
        'name': 'South England',
        'latitude': 50.93,
        'longitude': -1.44,
        'default_active': False,
    },
    {
        'region_id': 14,
        'location_id': 'Data-Center-14',
        'name': 'South East England',
        'latitude': 51.27,
        'longitude': 0.52,
        'default_active': False,
    },
]

# Map UK regions to Data Center locations for carbon sync.
UK_REGION_TO_DC = {row['region_id']: row['location_id'] for row in DEFAULT_DATACENTERS}

DATACENTER_METADATA_BY_ID = {row['location_id']: row for row in DEFAULT_DATACENTERS}


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
                load REAL,
                carbon_intensity REAL NOT NULL,
                PRIMARY KEY (location, timestamp)
            )
        """)

        # Migrate: allow NULL load (carbon-only rows from carbon sync)
        cursor = conn.execute("PRAGMA table_info(historical_data)")
        for col in cursor.fetchall():
            if col[1] == 'load' and col[3] == 1:  # col[3]=notnull flag
                conn.execute("""
                    CREATE TABLE historical_data_new (
                        location TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        load REAL,
                        carbon_intensity REAL NOT NULL,
                        PRIMARY KEY (location, timestamp)
                    )
                """)
                conn.execute("""
                    INSERT INTO historical_data_new
                    SELECT * FROM historical_data
                """)
                conn.execute("DROP TABLE historical_data")
                conn.execute("ALTER TABLE historical_data_new RENAME TO historical_data")
                # Clean up legacy load=0 rows from old carbon syncs
                conn.execute("""
                    UPDATE historical_data SET load = NULL WHERE load = 0
                """)
                break

        # Create indexes for efficient querying
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_historical_timestamp
            ON historical_data(timestamp)
        """)

        # Pre-upsampled (5-min) historical cache table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historical_cache (
                location TEXT NOT NULL,
                timestamp REAL NOT NULL,
                load REAL,
                carbon_intensity REAL,
                PRIMARY KEY (location, timestamp)
            )
        """)

        # Migrate: allow NULL load in cache table too
        cursor = conn.execute("PRAGMA table_info(historical_cache)")
        for col in cursor.fetchall():
            if col[1] == 'load' and col[3] == 1:  # col[3]=notnull flag
                conn.execute("""
                    CREATE TABLE historical_cache_new (
                        location TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        load REAL,
                        carbon_intensity REAL,
                        PRIMARY KEY (location, timestamp)
                    )
                """)
                conn.execute("INSERT INTO historical_cache_new SELECT * FROM historical_cache")
                conn.execute("DROP TABLE historical_cache")
                conn.execute("ALTER TABLE historical_cache_new RENAME TO historical_cache")
                break

        conn.execute("""
            CREATE TABLE IF NOT EXISTS datacenters (
                location_id TEXT PRIMARY KEY,
                region_id INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        now = time.time()
        conn.executemany(
            """
            INSERT OR IGNORE INTO datacenters
                (location_id, region_id, name, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    dc['location_id'],
                    dc['region_id'],
                    dc['name'],
                    int(dc['default_active']),
                    now,
                    now,
                )
                for dc in DEFAULT_DATACENTERS
            ],
        )

        # Keep region/name metadata fresh while preserving active user choices.
        conn.executemany(
            """
            UPDATE datacenters
            SET region_id = ?, name = ?, updated_at = ?
            WHERE location_id = ?
            """,
            [
                (dc['region_id'], dc['name'], now, dc['location_id'])
                for dc in DEFAULT_DATACENTERS
            ],
        )


def _datacenter_row_to_dict(row: tuple) -> Dict:
    metadata = DATACENTER_METADATA_BY_ID.get(row[0], {})
    return {
        'id': row[0],
        'region_id': row[1],
        'name': row[2],
        'active': bool(row[3]),
        'latitude': metadata.get('latitude'),
        'longitude': metadata.get('longitude'),
    }


def get_datacenters(include_inactive: bool = True) -> List[Dict]:
    """Get datacenter configuration entries."""
    try:
        with get_connection() as conn:
            if include_inactive:
                cursor = conn.execute(
                    """
                    SELECT location_id, region_id, name, is_active
                    FROM datacenters
                    ORDER BY region_id ASC
                    """
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT location_id, region_id, name, is_active
                    FROM datacenters
                    WHERE is_active = 1
                    ORDER BY region_id ASC
                    """
                )
            return [_datacenter_row_to_dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f'Error retrieving datacenters: {e}')
        return []


def get_datacenter(location_id: str) -> Optional[Dict]:
    """Get one datacenter configuration entry by location ID."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT location_id, region_id, name, is_active
                FROM datacenters
                WHERE location_id = ?
                """,
                (location_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _datacenter_row_to_dict(row)
    except sqlite3.Error as e:
        print(f'Error retrieving datacenter {location_id}: {e}')
        return None


def set_datacenter_active(location_id: str, active: bool) -> bool:
    """Set active state for a datacenter. Returns False if location is missing."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE datacenters
                SET is_active = ?, updated_at = ?
                WHERE location_id = ?
                """,
                (int(active), time.time(), location_id),
            )
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f'Error updating datacenter active flag for {location_id}: {e}')
        return False


def get_all_datacenter_ids(include_inactive: bool = True) -> List[str]:
    """Get datacenter IDs ordered by region ID."""
    return [dc['id'] for dc in get_datacenters(include_inactive=include_inactive)]


def get_active_datacenter_ids() -> List[str]:
    """Get IDs for active datacenters only."""
    return get_all_datacenter_ids(include_inactive=False)


def get_cached_prediction(key: str) -> Optional[dict]:
    """Get cached prediction if it exists and is within the configured TTL."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                'SELECT data, timestamp FROM predictions WHERE key = ?', (key,)
            )
            row = cursor.fetchone()

            if row:
                data_json, timestamp = row
                if time.time() - timestamp < PREDICTION_CACHE_TTL:
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


def save_historical_cache(location: str, entries: List[Dict]):
    """Replace the upsampled historical cache for a location.

    Args:
        entries: List of dicts with keys: timestamp (datetime), load, carbon_intensity
    """
    try:
        with get_connection() as conn:
            conn.execute(
                'DELETE FROM historical_cache WHERE location = ?', (location,)
            )
            conn.executemany(
                """INSERT INTO historical_cache
                   (location, timestamp, load, carbon_intensity)
                   VALUES (?, ?, ?, ?)""",
                [
                    (
                        location,
                        e['timestamp'].timestamp(),
                        e['load'],
                        e.get('carbon_intensity'),
                    )
                    for e in entries
                ],
            )
    except sqlite3.Error as e:
        print(f'Historical cache write error: {e}')


def get_historical_cache(
    location: str,
    start_time: datetime,
    end_time: datetime,
) -> Optional[List[Dict]]:
    """Get pre-upsampled 5-min historical data from cache.

    Returns list of dicts on hit, None if the cache table is empty for this location.
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT timestamp, load, carbon_intensity
                   FROM historical_cache
                   WHERE location = ? AND timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp ASC""",
                (location, start_time.timestamp(), end_time.timestamp()),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            return [
                {
                    'timestamp': datetime.fromtimestamp(row[0], tz=timezone.utc),
                    'load': row[1],
                    'carbon_intensity': row[2],
                }
                for row in rows
            ]
    except sqlite3.Error as e:
        print(f'Historical cache read error: {e}')
        return None


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
                    'timestamp': datetime.fromtimestamp(row[0], tz=timezone.utc),
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
                return datetime.fromtimestamp(result[0], tz=timezone.utc)
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


def sync_carbon_to_historical(days_back: int = 365) -> int:
    """Sync carbon intensity data to historical_data table.

    Reads from carbon_intensity.db, maps UK regions to Data Center locations,
    and upserts into cache.db. Only updates the carbon_intensity column for
    existing rows, preserving any existing load data.

    Args:
        days_back: How many days of data to sync

    Returns:
        Number of records synced
    """
    since = datetime.now() - timedelta(days=days_back)
    readings = get_carbon_readings(since=since, limit=500000)

    if not readings:
        print('No carbon readings found to sync')
        return 0

    bulk_data = []
    for reading in readings:
        region_id = reading.get('region_id')
        if region_id not in UK_REGION_TO_DC:
            continue

        location = UK_REGION_TO_DC[region_id]
        carbon_intensity = reading.get('actual')

        if carbon_intensity is None:
            continue

        ts_str = reading.get('timestamp_from', '')
        try:
            ts_str = ts_str.replace('Z', '+00:00')
            timestamp = datetime.fromisoformat(ts_str)
        except ValueError:
            continue

        bulk_data.append(
            {
                'location': location,
                'timestamp': timestamp,
                'carbon_intensity': carbon_intensity,
            }
        )

    if bulk_data:
        _upsert_carbon_intensity_bulk(bulk_data)
        print(f'Synced {len(bulk_data)} carbon readings to historical data')

    return len(bulk_data)


def _upsert_carbon_intensity_bulk(data: List[Dict]):
    """Upsert carbon intensity into historical_data without overwriting load.

    For existing rows (matching location + timestamp), only carbon_intensity
    is updated. For new rows, load is set to NULL so that forward-fill in
    upsampling propagates the previous valid load value instead of injecting 0.
    """
    try:
        with get_connection() as conn:
            conn.executemany(
                """INSERT INTO historical_data
                   (location, timestamp, load, carbon_intensity)
                   VALUES (?, ?, NULL, ?)
                   ON CONFLICT(location, timestamp)
                   DO UPDATE SET carbon_intensity = excluded.carbon_intensity""",
                [
                    (
                        d['location'],
                        d['timestamp'].timestamp(),
                        d['carbon_intensity'],
                    )
                    for d in data
                ],
            )
    except sqlite3.Error as e:
        print(f'Error upserting carbon intensity data: {e}')
        raise


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
