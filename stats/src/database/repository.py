import json
import sqlite3
import time
from datetime import datetime

from src.core.settings import MAIN_CACHE_SQLITE_DB_PATH


def get_historical_data_count() -> int:
    """Returns total records in historical_data. Safe for existing servers."""
    with get_main_cache_database_connection() as db_connection:
        result = db_connection.execute(
            'SELECT COUNT(*) FROM historical_data'
        ).fetchone()
        return result[0] if result else 0


def get_main_cache_database_connection():
    return sqlite3.connect(MAIN_CACHE_SQLITE_DB_PATH)


def initialize_main_cache_database_tables():
    with get_main_cache_database_connection() as db_connection:
        db_connection.execute('PRAGMA journal_mode=WAL')
        db_connection.execute(
            'CREATE TABLE IF NOT EXISTS predictions (cache_key TEXT PRIMARY KEY, json_data TEXT, cache_timestamp REAL)'
        )
        db_connection.execute(
            'CREATE TABLE IF NOT EXISTS historical_data (datacenter_location TEXT, metric_timestamp REAL, load_value REAL, carbon_intensity_value REAL, PRIMARY KEY (datacenter_location, metric_timestamp))'
        )


def save_forecast_to_cache_database(cache_key: str, forecast_data_dict: dict):
    with get_main_cache_database_connection() as db_connection:
        db_connection.execute(
            'INSERT OR REPLACE INTO predictions VALUES (?, ?, ?)',
            (cache_key, json.dumps(forecast_data_dict), time.time()),
        )


def retrieve_forecast_from_cache_database(cache_key: str):
    with get_main_cache_database_connection() as db_connection:
        query_result = db_connection.execute(
            'SELECT json_data, cache_timestamp FROM predictions WHERE cache_key = ?',
            (cache_key,),
        ).fetchone()

        # Cache expires after 300 seconds (5 minutes)
        is_cache_valid = query_result and (time.time() - query_result[1] < 300)
        return json.loads(query_result[0]) if is_cache_valid else None


def fetch_historical_metrics_for_datacenter(
    datacenter_location: str, start_datetime=None
):
    sql_query = 'SELECT metric_timestamp, load_value, carbon_intensity_value FROM historical_data WHERE datacenter_location = ?'
    query_parameters = [datacenter_location]

    if start_datetime:
        sql_query += ' AND metric_timestamp >= ?'
        query_parameters.append(start_datetime.timestamp())

    with get_main_cache_database_connection() as db_connection:
        database_rows = db_connection.execute(
            sql_query + ' ORDER BY metric_timestamp ASC', tuple(query_parameters)
        ).fetchall()
        return [
            {
                'timestamp': datetime.fromtimestamp(row[0]),
                'load': row[1],
                'carbon_intensity': row[2],
            }
            for row in database_rows
        ]


def insert_or_update_historical_load_metrics(load_metrics_list):
    """Inserts load data. If row exists, updates ONLY the load_value."""
    with get_main_cache_database_connection() as db_connection:
        db_connection.executemany(
            """INSERT INTO historical_data (datacenter_location, metric_timestamp, load_value, carbon_intensity_value) 
               VALUES (?, ?, ?, 250.0)
               ON CONFLICT(datacenter_location, metric_timestamp) DO UPDATE SET load_value=excluded.load_value""",
            [
                (
                    data_point['location'],
                    data_point['timestamp'].timestamp(),
                    data_point['load'],
                )
                for data_point in load_metrics_list
            ],
        )


def insert_or_update_historical_carbon_metrics(carbon_metrics_list):
    """Inserts carbon data. If row exists, updates ONLY the carbon_intensity_value."""
    with get_main_cache_database_connection() as db_connection:
        db_connection.executemany(
            """INSERT INTO historical_data (datacenter_location, metric_timestamp, load_value, carbon_intensity_value) 
               VALUES (?, ?, 0.0, ?)
               ON CONFLICT(datacenter_location, metric_timestamp) DO UPDATE SET carbon_intensity_value=excluded.carbon_intensity_value""",
            [
                (
                    data_point['location'],
                    data_point['timestamp'].timestamp(),
                    data_point['carbon_intensity'],
                )
                for data_point in carbon_metrics_list
            ],
        )
