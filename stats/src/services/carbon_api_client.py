import sqlite3

import requests

from src.core.settings import (
    CARBON_INTENSITY_SQLITE_DB_PATH,
    UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING,
    application_logger,
)


def get_carbon_database_connection():
    return sqlite3.connect(CARBON_INTENSITY_SQLITE_DB_PATH)


def initialize_carbon_database_tables():
    with get_carbon_database_connection() as db_connection:
        db_connection.execute('PRAGMA journal_mode=WAL')
        db_connection.execute(
            'CREATE TABLE IF NOT EXISTS carbon_readings (api_region_id INTEGER, interval_start_timestamp TEXT, actual_carbon_intensity INTEGER, PRIMARY KEY (api_region_id, interval_start_timestamp))'
        )


def fetch_latest_carbon_intensity_and_store_in_db(db_connection):
    """Fetches latest data from the UK API and stores it only if an 'actual' value is present."""
    for region_id in UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING:
        try:
            api_response = requests.get(
                f'https://api.carbonintensity.org.uk/regional/regionid/{region_id}',
                timeout=10,
            )
            api_response.raise_for_status()
            parsed_json_data = api_response.json()

            latest_data_entry = parsed_json_data['data'][0]['data'][0]
            actual_intensity_value = latest_data_entry['intensity'].get('actual')

            if actual_intensity_value is not None:
                db_connection.execute(
                    'INSERT OR REPLACE INTO carbon_readings VALUES (?, ?, ?)',
                    (region_id, latest_data_entry['from'], actual_intensity_value),
                )
            else:
                application_logger.debug(
                    f"Region {region_id}: No 'actual' intensity yet (likely still in forecast)."
                )

        except (requests.RequestException, KeyError, IndexError) as error:
            application_logger.warning(
                f'Could not update region {region_id} due to error: {error}'
            )


def retrieve_carbon_readings_since_timestamp(since_iso_timestamp):
    with get_carbon_database_connection() as db_connection:
        db_connection.row_factory = sqlite3.Row
        return db_connection.execute(
            'SELECT * FROM carbon_readings WHERE interval_start_timestamp >= ?',
            (since_iso_timestamp,),
        ).fetchall()
