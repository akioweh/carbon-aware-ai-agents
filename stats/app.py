import logging
import threading
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

import config  # triggers logging setup
import db_utils
from background import carbon_sync_loop, prediction_loop
from data.carbon_collector import (
    backfill,
    carbon_collector_loop,
    init_database as init_carbon_db,
    DB_PATH as CARBON_DB_PATH,
)
from routes import router

logger = logging.getLogger('stats.app')


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_utils.initialize_db()

    # Step 1: Backfill carbon data from API BEFORE anything else.
    if config.CARBON_COLLECTION_ENABLED:
        logger.info('Running carbon collector backfill from API...')
        try:
            conn = init_carbon_db(CARBON_DB_PATH)
            backfill(conn)
            conn.close()
            logger.info('Carbon backfill complete')
        except Exception:
            logger.error('Carbon backfill failed on startup', exc_info=True)

    # Step 2: Sync carbon data into historical_data table
    if db_utils.has_carbon_data():
        logger.info('Syncing carbon data to historical_data...')
        try:
            count = db_utils.sync_carbon_to_historical()
            logger.info('Synced %d carbon readings to historical data', count)
        except Exception:
            logger.error('Failed to sync carbon data on startup', exc_info=True)

    # Step 3: Start background threads
    prediction_thread = threading.Thread(target=prediction_loop, daemon=True)
    prediction_thread.start()

    if config.CARBON_COLLECTION_ENABLED:
        collector_thread = threading.Thread(target=carbon_collector_loop, daemon=True)
        collector_thread.start()
        print('Carbon collector background thread started')

        sync_thread = threading.Thread(target=carbon_sync_loop, daemon=True)
        sync_thread.start()
        print('Carbon sync background thread started')
    elif db_utils.has_carbon_data():
        sync_thread = threading.Thread(target=carbon_sync_loop, daemon=True)
        sync_thread.start()
        print('Carbon sync background thread started')

    openapi_data = app.openapi()
    with open('openapi.yaml', 'w') as f:
        yaml.dump(openapi_data, f, sort_keys=False)
    print('openapi.yaml updated')

    yield


app = FastAPI(
    title='Carbon-Aware Forecasting Service',
    description=(
        'Provides load and carbon intensity forecasts for data center locations. '
        'Forecasts are generated using Ridge regression models trained on historical '
        'UK Carbon Intensity API data and weather features from Open-Meteo. '
        'All forecasts cover a 7-day window at 5-minute resolution (2016 data points).'
    ),
    version='1.0.0',
    lifespan=lifespan,
)
app.include_router(router)


if __name__ == '__main__':
    import uvicorn

    print(f'Starting Stats API on {config.HOST}:{config.PORT}')
    uvicorn.run(app, host=config.HOST, port=config.PORT)
