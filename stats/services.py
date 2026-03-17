from datetime import datetime, timedelta

import carbon_collector
import db_utils
from config import UK_REGION_TO_DC


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
                    'carbon_intensity': r['actual'],
                }
            )

    if bulk:
        db_utils.upsert_carbon_data(bulk)  # Use the new targeted upsert
    return len(bulk)
