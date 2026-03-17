import sqlite3

import requests

from datetime import datetime, timedelta, timezone

from ..core.settings import (
    BACKFILL_DAYS,
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


def backfill_carbon_intensity_data(days_back=None):
    """Fetches missing historical carbon intensity data from the UK API."""
    if days_back is None:
        days_back = BACKFILL_DAYS

    end_time = datetime.now(timezone.utc)

    with get_carbon_database_connection() as db_connection:
        for region_id in UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING:
            # Find the latest reading for this region
            latest_reading = db_connection.execute(
                'SELECT MAX(interval_start_timestamp) FROM carbon_readings WHERE api_region_id = ?',
                (region_id,),
            ).fetchone()

            if latest_reading and latest_reading[0]:
                start_time = datetime.fromisoformat(
                    latest_reading[0].replace('Z', '+00:00')
                )
            else:
                start_time = end_time - timedelta(days=days_back)

            # If the gap is less than 30 minutes, skip
            if (end_time - start_time).total_seconds() < 1800:
                continue

            application_logger.info(
                f'Backfilling carbon data for region {region_id} from {start_time.isoformat()}...'
            )

            current_ptr = start_time
            total_readings_backfilled = 0
            while current_ptr < end_time:
                chunk_end = min(current_ptr + timedelta(days=1), end_time)
                from_str = current_ptr.strftime('%Y-%m-%dT%H:%MZ')
                to_str = chunk_end.strftime('%Y-%m-%dT%H:%MZ')

                try:
                    url = f'https://api.carbonintensity.org.uk/regional/intensity/{from_str}/{to_str}'
                    api_response = requests.get(url, timeout=30)
                    api_response.raise_for_status()
                    data = api_response.json()

                    readings_to_insert = []
                    for interval in data.get('data', []):
                        interval_start = interval.get('from')
                        for region in interval.get('regions', []):
                            if region.get('regionid') == region_id:
                                intensity_info = region.get('intensity', {})
                                intensity = intensity_info.get(
                                    'actual'
                                ) or intensity_info.get('forecast')
                                if intensity is not None:
                                    readings_to_insert.append(
                                        (region_id, interval_start, intensity)
                                    )

                    if readings_to_insert:
                        db_connection.executemany(
                            'INSERT OR REPLACE INTO carbon_readings VALUES (?, ?, ?)',
                            readings_to_insert,
                        )
                        db_connection.commit()
                        total_readings_backfilled += len(readings_to_insert)

                except Exception as e:
                    application_logger.error(
                        f'Failed to backfill chunk {from_str} -> {to_str} for region {region_id}: {e}'
                    )
                    break

                current_ptr = chunk_end

            application_logger.info(
                f'Backfill for region {region_id} complete. Added {total_readings_backfilled} readings.'
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
