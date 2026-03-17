from datetime import datetime, timedelta

import carbon_collector
import db_utils
from config import TOTAL_CAPACITY, UK_REGION_TO_DC


def sync_carbon_to_historical(days_back=7):
    """Bridge: Moves data from carbon_collector domain to db_utils domain."""
    since = (datetime.now() - timedelta(days=days_back)).isoformat()
    readings = carbon_collector.get_all_readings(since)

    bulk = []
    for r in readings:
        loc = UK_REGION_TO_DC.get(r['region_id'])
        if loc and r['actual'] is not None:
            bulk.append(
                {
                    'location': loc,
                    'timestamp': datetime.fromisoformat(
                        r['timestamp_from'].replace('Z', '+00:00')
                    ),
                    'load': TOTAL_CAPACITY,
                    'carbon_intensity': r['actual'],
                }
            )

    if bulk:
        db_utils.insert_historical_data_bulk(bulk)
    return len(bulk)
