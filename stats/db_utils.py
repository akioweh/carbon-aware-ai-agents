import json
import sqlite3
import time
from datetime import datetime

from config import DB_FILE


def get_connection():
    return sqlite3.connect(DB_FILE)


def initialize_db():
    with get_connection() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(
            'CREATE TABLE IF NOT EXISTS predictions (key TEXT PRIMARY KEY, data TEXT, timestamp REAL)'
        )
        conn.execute(
            'CREATE TABLE IF NOT EXISTS historical_data (location TEXT, timestamp REAL, load REAL, carbon_intensity REAL, PRIMARY KEY (location, timestamp))'
        )


def save_prediction(key: str, data: dict):
    with get_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO predictions VALUES (?, ?, ?)',
            (key, json.dumps(data), time.time()),
        )


def get_cached_prediction(key: str):
    with get_connection() as conn:
        res = conn.execute(
            'SELECT data, timestamp FROM predictions WHERE key = ?', (key,)
        ).fetchone()
        return json.loads(res[0]) if res and (time.time() - res[1] < 300) else None


def get_historical_data(location: str, start_time=None):
    query = 'SELECT timestamp, load, carbon_intensity FROM historical_data WHERE location = ?'
    params = [location]
    if start_time:
        query += ' AND timestamp >= ?'
        params.append(start_time.timestamp())
    with get_connection() as conn:
        rows = conn.execute(query + ' ORDER BY timestamp ASC', tuple(params)).fetchall()
        return [
            {
                'timestamp': datetime.fromtimestamp(r[0]),
                'load': r[1],
                'carbon_intensity': r[2],
            }
            for r in rows
        ]


def insert_historical_data_bulk(data_list):
    with get_connection() as conn:
        conn.executemany(
            'INSERT OR REPLACE INTO historical_data VALUES (?, ?, ?, ?)',
            [
                (
                    d['location'],
                    d['timestamp'].timestamp(),
                    d['load'],
                    d['carbon_intensity'],
                )
                for d in data_list
            ],
        )
