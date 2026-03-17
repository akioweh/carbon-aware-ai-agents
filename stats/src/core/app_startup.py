import threading

from ..database import repository
from ..scripts.generate_mock_historical_data import (
    generate_and_store_mock_historical_data,
)
from ..services import carbon_api_client, data_synchronizer
from ..workers.background_jobs import (
    start_continuous_carbon_data_collection_worker_loop,
    start_continuous_forecast_generation_worker_loop,
)


def initialize_app_and_start_background_workers():
    # 1. Initialize DB structures
    repository.initialize_main_cache_database_tables()
    carbon_api_client.initialize_carbon_database_tables()

    # 2. Backfill carbon data from API
    try:
        carbon_api_client.backfill_carbon_intensity_data(days_back=None)
    except Exception as e:
        from .settings import application_logger

        application_logger.error(f'Carbon backfill failed on startup: {e}')

    # 3. Conditional Seeding: Only run if the database is empty
    if repository.get_historical_data_count() == 0:
        generate_and_store_mock_historical_data(days=30)

    # 4. Sync historical data to baseline cache
    data_synchronizer.synchronize_carbon_readings_to_main_historical_database(
        days_to_look_back=30
    )

    # 5. Start background threads
    active_worker_threads = [
        threading.Thread(
            target=start_continuous_forecast_generation_worker_loop, daemon=True
        ),
        threading.Thread(
            target=start_continuous_carbon_data_collection_worker_loop, daemon=True
        ),
    ]

    for worker_thread in active_worker_threads:
        worker_thread.start()

    return active_worker_threads
