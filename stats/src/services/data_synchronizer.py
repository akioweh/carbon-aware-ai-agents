from datetime import datetime, timedelta

from src.core.settings import UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING
from src.database import repository
from src.services import carbon_api_client


def synchronize_carbon_readings_to_main_historical_database(days_to_look_back=7):
    """Bridge function: Moves data from the carbon collection database into the main historical database."""
    cutoff_datetime_iso = (
        datetime.now() - timedelta(days=days_to_look_back)
    ).isoformat()
    raw_carbon_readings = carbon_api_client.retrieve_carbon_readings_since_timestamp(
        cutoff_datetime_iso
    )

    bulk_insert_payload = []
    for reading in raw_carbon_readings:
        datacenter_location = UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING.get(
            reading['api_region_id']
        )

        if datacenter_location and reading['actual_carbon_intensity'] is not None:
            bulk_insert_payload.append(
                {
                    'location': datacenter_location,
                    'timestamp': datetime.fromisoformat(
                        reading['interval_start_timestamp'].replace('Z', '+00:00')
                    ),
                    'carbon_intensity': reading['actual_carbon_intensity'],
                }
            )

    if bulk_insert_payload:
        repository.insert_or_update_historical_carbon_metrics(bulk_insert_payload)

    return len(bulk_insert_payload)
