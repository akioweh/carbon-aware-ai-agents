"""Database utilities for managing historical time-series data."""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

DB_FILE = 'cache.db'


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_FILE)
    return conn


def initialize_db():
    """Initialize the SQLite database for caching and historical data."""
    with sqlite3.connect(DB_FILE) as conn:
        # Enable WAL mode for better concurrent access
        conn.execute('PRAGMA journal_mode=WAL')
        
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
                greenness REAL NOT NULL,
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



def insert_historical_data(location: str, timestamp: datetime, load: float, greenness: float):
    """Insert a single historical data point. Replaces if timestamp already exists."""
    try:
        with get_connection() as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO historical_data 
                   (location, timestamp, load, greenness) 
                   VALUES (?, ?, ?, ?)''',
                (location, timestamp.timestamp(), load, greenness)
            )
    except sqlite3.Error as e:
        print(f'Error inserting historical data: {e}')
        raise


def insert_historical_data_bulk(data: List[Dict]):
    """Insert multiple historical data points efficiently.
    
    Args:
        data: List of dicts with keys: location, timestamp, load, greenness
    """
    try:
        with get_connection() as conn:
            conn.executemany(
                '''INSERT OR REPLACE INTO historical_data 
                   (location, timestamp, load, greenness) 
                   VALUES (?, ?, ?, ?)''',
                [(d['location'], d['timestamp'].timestamp(), d['load'], d['greenness']) 
                 for d in data]
            )
    except sqlite3.Error as e:
        print(f'Error inserting bulk historical data: {e}')
        raise


def get_historical_data(
    location: str, 
    start_time: Optional[datetime] = None, 
    end_time: Optional[datetime] = None
) -> List[Dict]:
    """Get historical data for a location within optional time range.
    
    Args:
        location: Datacenter location identifier
        start_time: Optional start time filter
        end_time: Optional end time filter
        
    Returns:
        List of dicts with keys: timestamp (datetime), load, greenness
    """
    try:
        with get_connection() as conn:
            if start_time and end_time:
                cursor = conn.execute(
                    '''SELECT timestamp, load, greenness 
                       FROM historical_data 
                       WHERE location = ? AND timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp ASC''',
                    (location, start_time.timestamp(), end_time.timestamp())
                )
            elif start_time:
                cursor = conn.execute(
                    '''SELECT timestamp, load, greenness 
                       FROM historical_data 
                       WHERE location = ? AND timestamp >= ?
                       ORDER BY timestamp ASC''',
                    (location, start_time.timestamp())
                )
            elif end_time:
                cursor = conn.execute(
                    '''SELECT timestamp, load, greenness 
                       FROM historical_data 
                       WHERE location = ? AND timestamp <= ?
                       ORDER BY timestamp ASC''',
                    (location, end_time.timestamp())
                )
            else:
                cursor = conn.execute(
                    '''SELECT timestamp, load, greenness 
                       FROM historical_data 
                       WHERE location = ?
                       ORDER BY timestamp ASC''',
                    (location,)
                )
            
            rows = cursor.fetchall()
            return [
                {
                    'timestamp': datetime.fromtimestamp(row[0]),
                    'load': row[1],
                    'greenness': row[2]
                }
                for row in rows
            ]
    except sqlite3.Error as e:
        print(f'Error retrieving historical data: {e}')
        return []


def delete_old_data(days: int = 30):
    """Delete historical data older than specified number of days."""
    try:
        cutoff = datetime.now() - timedelta(days=days)
        with get_connection() as conn:
            cursor = conn.execute(
                'DELETE FROM historical_data WHERE timestamp < ?',
                (cutoff.timestamp(),)
            )
            deleted_count = cursor.rowcount
            print(f'Deleted {deleted_count} old historical data points')
    except sqlite3.Error as e:
        print(f'Error deleting old data: {e}')
        raise


def get_latest_timestamp(location: str) -> Optional[datetime]:
    """Get the timestamp of the most recent data point for a location."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                '''SELECT MAX(timestamp) FROM historical_data WHERE location = ?''',
                (location,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                return datetime.fromtimestamp(result[0])
            return None
    except sqlite3.Error as e:
        print(f'Error getting latest timestamp: {e}')
        return None


def migrate_json_to_db(json_file: str = 'history.json'):
    """Migrate data from history.json to the database.
    
    Args:
        json_file: Path to the JSON file to migrate
    """
    if not os.path.exists(json_file):
        print(f'{json_file} not found, skipping migration')
        return
    
    print(f'Migrating data from {json_file} to database...')
    
    try:
        with open(json_file, 'r') as f:
            history_json = json.load(f)
        
        # Prepare bulk insert data
        bulk_data = []
        for location, entries in history_json.items():
            for entry in entries:
                bulk_data.append({
                    'location': location,
                    'timestamp': datetime.fromisoformat(entry['timestamp']),
                    'load': entry['load'],
                    'greenness': entry['greenness']
                })
        
        # Insert all data
        if bulk_data:
            insert_historical_data_bulk(bulk_data)
            print(f'Successfully migrated {len(bulk_data)} data points from {json_file}')
            
            # Rename the old file as backup
            backup_file = f'{json_file}.backup'
            os.rename(json_file, backup_file)
            print(f'Backed up {json_file} to {backup_file}')
        else:
            print('No data found in JSON file')
            
    except Exception as e:
        print(f'Error during migration: {e}')
        raise


def count_historical_data() -> int:
    """Get the total count of historical data points in the database."""
    try:
        with get_connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM historical_data')
            return cursor.fetchone()[0]
    except sqlite3.Error as e:
        print(f'Error counting historical data: {e}')
        return 0
