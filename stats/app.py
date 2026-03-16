import threading
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

import db_utils
from carbon_collector import (
    DB_PATH as CARBON_DB_PATH,
)
from carbon_collector import (
    backfill,
)
from carbon_collector import init_database as init_carbon_db
from config import (
    CARBON_COLLECTION_ENABLED,
    HOST,
    PORT,
    logger,
)
from generate_history import generate_history
from routes import router
from tasks import carbon_collector_loop, carbon_sync_loop, prediction_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_utils.initialize_db()

    # Step 1: Backfill carbon data from API BEFORE anything else.
    if CARBON_COLLECTION_ENABLED:
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
            count = db_utils.sync_carbon_to_historical(days_back=30)
            logger.info('Synced %d carbon readings to historical data', count)
        except Exception:
            logger.error('Failed to sync carbon data on startup', exc_info=True)

    # Step 3: Fall back to synthetic data only if no historical data at all
    if db_utils.count_historical_data() == 0:
        print('No historical data found, generating initial data...')
        generate_history()

    # Step 4: Start background threads
    prediction_thread = threading.Thread(target=prediction_loop, daemon=True)
    prediction_thread.start()

    if CARBON_COLLECTION_ENABLED:
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
    title='Stats API',
    description='Statistics provider for carbon-aware scheduling predictions.',
    version='1.0.0',
    lifespan=lifespan,
)
app.include_router(router)


if __name__ == '__main__':
    import uvicorn

    print(f'Starting Stats API on {HOST}:{PORT}')
    uvicorn.run(app, host=HOST, port=PORT)
