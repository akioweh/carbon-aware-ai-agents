import sqlite3

import requests

from config import CARBON_DB_FILE, UK_REGION_TO_DC, logger


def get_db():
    return sqlite3.connect(CARBON_DB_FILE)


def init_database():
    with get_db() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(
            'CREATE TABLE IF NOT EXISTS carbon_readings (region_id INTEGER, timestamp_from TEXT, actual INTEGER, PRIMARY KEY (region_id, timestamp_from))'
        )


def fetch_and_store(conn):
    """Fetches latest data and stores only if an 'actual' value is present."""
    for rid in UK_REGION_TO_DC:
        try:
            r = requests.get(
                f'https://api.carbonintensity.org.uk/regional/regionid/{rid}',
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            entry = data['data'][0]['data'][0]
            actual = entry['intensity'].get('actual')

            if actual is not None:
                conn.execute(
                    'INSERT OR REPLACE INTO carbon_readings VALUES (?, ?, ?)',
                    (rid, entry['from'], actual),
                )
            else:
                logger.debug(
                    f"Region {rid}: No 'actual' intensity yet (likely still in forecast)."
                )

        except (requests.RequestException, KeyError, IndexError) as e:
            logger.warning(f'Could not update region {rid}: {e}')


def get_all_readings(since_iso):
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            'SELECT * FROM carbon_readings WHERE timestamp_from >= ?', (since_iso,)
        ).fetchall()
