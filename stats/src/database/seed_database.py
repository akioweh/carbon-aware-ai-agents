import math
import random
from datetime import datetime, timedelta

from src.core.settings import SUPPORTED_DATACENTER_NAMES
from src.database import repository
from src.scripts.generate_mock_historical_data import (
    calculate_simulated_datacenter_load,
)
from src.services import carbon_api_client
from src.services.forecasting_engine import (
    predict_carbon_intensity_for_next_seven_days,
    predict_datacenter_load_for_next_seven_days,
)


def seed():
    print('🚀 Initializing databases...')
    repository.initialize_main_cache_database_tables()
    carbon_api_client.initialize_carbon_database_tables()

    # Check if data already exists to avoid double-seeding
    with repository.get_main_cache_database_connection() as conn:
        count = conn.execute('SELECT COUNT(*) FROM historical_data').fetchone()[0]
        if count > 0:
            print(
                f'⚠️ Database already contains {count} records. Skipping history generation.'
            )
        else:
            print('📊 Generating 30 days of historical data...')
            generate_history()

    print('🔮 Pre-generating forecasts for the cache...')
    for dc in SUPPORTED_DATACENTER_NAMES:
        try:
            # Seed Load Forecast
            load_forecast = predict_datacenter_load_for_next_seven_days(dc)
            repository.save_forecast_to_cache_database(
                f'load_forecast_{dc}', load_forecast
            )

            # Seed Carbon Forecast
            carbon_forecast = predict_carbon_intensity_for_next_seven_days(dc)
            repository.save_forecast_to_cache_database(
                f'carbon_intensity_forecast_{dc}', carbon_forecast
            )

            print(f'✅ Cached forecasts for {dc}')
        except Exception as e:
            print(f'❌ Failed to forecast {dc}: {e}')

    print('\n✨ Database is now ready.')


def generate_history():
    current_time = datetime.now()
    iterating_time = current_time - timedelta(days=30)

    load_payload = []
    carbon_payload = []

    while iterating_time <= current_time:
        for index, dc_name in enumerate(SUPPORTED_DATACENTER_NAMES):
            # 1. Varying Load (using your existing logic)
            sim_load = calculate_simulated_datacenter_load(iterating_time, index)
            load_payload.append(
                {'location': dc_name, 'timestamp': iterating_time, 'load': sim_load}
            )

            # 2. Varying Carbon Intensity (Sine wave + noise to make "Greenness" move)
            # Base of 200, swings +/- 150 based on time of day, + random noise
            day_progress = (iterating_time.hour + iterating_time.minute / 60) / 24
            variation = 150 * math.sin(2 * math.pi * day_progress)
            noise = random.uniform(-20, 20)
            sim_carbon = max(50, min(500, 250 + variation + noise))

            carbon_payload.append(
                {
                    'location': dc_name,
                    'timestamp': iterating_time,
                    'carbon_intensity': sim_carbon,
                }
            )

        # Process in batches to keep memory low
        if len(load_payload) > 5000:
            repository.insert_or_update_historical_load_metrics(load_payload)
            repository.insert_or_update_historical_carbon_metrics(carbon_payload)
            load_payload, carbon_payload = [], []
            print(f'   ...processed history up to {iterating_time.date()}')

        iterating_time += timedelta(minutes=15)

    # Final batch
    repository.insert_or_update_historical_load_metrics(load_payload)
    repository.insert_or_update_historical_carbon_metrics(carbon_payload)


if __name__ == '__main__':
    seed()
