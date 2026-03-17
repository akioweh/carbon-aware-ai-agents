import math
import random
from datetime import datetime, timedelta

from ..core.settings import SUPPORTED_DATACENTER_NAMES
from ..database import repository
from ..scripts.generate_mock_historical_data import (
    generate_and_store_mock_historical_data,
)
from ..services import carbon_api_client
from ..services.forecasting_engine import (
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
            generate_and_store_mock_historical_data(days=30)

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


if __name__ == '__main__':
    seed()
