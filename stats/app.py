import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db_utils
from generate_history import generate_history
from predictor import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)
from carbon_collector import (
    init_database as init_carbon_db,
    backfill,
    collect_current,
    get_reading_count,
    DB_PATH as CARBON_DB_PATH,
    INTERVAL_MINUTES as CARBON_INTERVAL_MINUTES,
)

DB_FILE = 'cache.db'
LOG_FILE = os.environ.get('STATS_LOG_FILE', 'app.log')

# Logging setup — writes to both stdout and a persistent log file
_log_fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=_log_fmt,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger('stats.app')

# Threshold: log a CRITICAL alert after this many consecutive failures in a loop
_FAILURE_ALERT_THRESHOLD = int(os.environ.get('FAILURE_ALERT_THRESHOLD', 5))

# Configuration for Oracle/server deployment
HOST = os.environ.get('STATS_HOST', '127.0.0.1')
PORT = int(os.environ.get('STATS_PORT', 5000))
CARBON_SYNC_INTERVAL = int(os.environ.get('CARBON_SYNC_INTERVAL', 1800))  # 30 min
CARBON_COLLECTION_ENABLED = os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'


class Location(BaseModel):
    id: str = Field(..., description='Location identifier')
    name: str = Field(..., description='Human-readable name')


class Datacenter(BaseModel):
    id: str = Field(..., description='Location identifier')
    region_id: int = Field(..., description='UK Carbon Intensity API region ID')
    name: str = Field(..., description='Human-readable region/location name')
    active: bool = Field(..., description='Whether scheduler-visible location is enabled')
    latitude: float | None = Field(None, description='Latitude used for weather and map display')
    longitude: float | None = Field(None, description='Longitude used for weather and map display')


class DatacenterPatchRequest(BaseModel):
    active: bool = Field(..., description='New active state for this datacenter')


class Capacity(BaseModel):
    max_load: float = Field(..., description='Maximum load capacity')
    total_gpus: int = Field(..., description='Total number of GPUs')


class BaseForecastDataPoint(BaseModel):
    timestamp: str = Field(..., description='ISO format timestamp')
    value: float = Field(..., description='Forecasted value')
    is_forecast: bool = Field(..., description='Indicates if this is a forecast')


class BaseForecastResponse(BaseModel):
    location_id: str = Field(..., description='Datacenter identifier')
    metric: str = Field(
        ..., description='Metric name (e.g. forecast_load, forecast_carbon_intensity)'
    )
    unit: str = Field(..., description='Unit of measurement')


class LoadForecastDataPoint(BaseForecastDataPoint):
    capacity: float = Field(..., description='Capacity in FLOs')


class LoadForecastResponse(BaseForecastResponse):
    data: list[LoadForecastDataPoint] = Field(..., description='Time series data')


class CarbonIntensityForecastResponse(BaseForecastResponse):
    data: list[BaseForecastDataPoint] = Field(..., description='Time series data')


class ErrorResponse(BaseModel):
    error: str


class PredictionWindowModel(BaseModel):
    windowLengthHours: int


PREDICTION_WINDOW_HOURS = 7 * 24


def prediction_loop():
    """Background loop to update predictions every 5 minutes."""
    consecutive_failures: dict[str, int] = {}
    while True:
        logger.info('Updating predictions cache...')

        active_datacenters = db_utils.get_active_datacenter_ids()
        if not active_datacenters:
            logger.warning('No active datacenters configured; skipping prediction refresh')
            time.sleep(300)
            continue

        for dc in list(consecutive_failures):
            if dc not in active_datacenters:
                del consecutive_failures[dc]

        for dc in active_datacenters:
            consecutive_failures.setdefault(dc, 0)
            try:
                # Update Load Predictions
                load_data = generate_next_week_load_prediction(dc)
                db_utils.save_prediction(f'load_forecast_{dc}', load_data)

                # Update Carbon Intensity Predictions
                try:
                    ci_data = generate_next_week_carbon_intensity_prediction(dc)
                    db_utils.save_prediction(f'carbon_intensity_forecast_{dc}', ci_data)
                except ValueError as e:
                    logger.warning(
                        'ValueError updating CI predictions for %s: %s', dc, e
                    )
                    logger.warning(
                        'No carbon intensity data for %s, skipping CI forecast', dc
                    )

                if consecutive_failures[dc]:
                    logger.info(
                        'Prediction loop recovered for %s after %d failure(s)',
                        dc,
                        consecutive_failures[dc],
                    )
                consecutive_failures[dc] = 0
            except Exception as e:
                consecutive_failures[dc] += 1
                logger.error(
                    'Error updating predictions for %s (consecutive failures: %d): %s',
                    dc,
                    consecutive_failures[dc],
                    e,
                    exc_info=True,
                )
                if consecutive_failures[dc] >= _FAILURE_ALERT_THRESHOLD:
                    logger.critical(
                        'ALERT: prediction loop for %s has failed %d times in a row — predictions may be stale',
                        dc,
                        consecutive_failures[dc],
                    )

        time.sleep(300)


def carbon_sync_loop():
    """Background loop to sync carbon intensity data periodically."""
    consecutive_failures = 0
    while True:
        try:
            if db_utils.has_carbon_data():
                count = db_utils.sync_carbon_to_historical(days_back=7)
                logger.info('Carbon sync: %d records updated', count)
            if consecutive_failures:
                logger.info(
                    'Carbon sync loop recovered after %d failure(s)',
                    consecutive_failures,
                )
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.error(
                'Error syncing carbon data (consecutive failures: %d)',
                consecutive_failures,
                exc_info=True,
            )
            if consecutive_failures >= _FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon sync loop has failed %d times in a row — carbon data in cache.db may be stale',
                    consecutive_failures,
                )
        time.sleep(CARBON_SYNC_INTERVAL)


def carbon_collector_loop():
    """Background loop to collect carbon intensity data from UK API."""
    logger.info('Carbon collector starting (interval: %d min)', CARBON_INTERVAL_MINUTES)
    logger.info('Database: %s', CARBON_DB_PATH)

    conn = init_carbon_db(CARBON_DB_PATH)

    consecutive_failures = 0
    while True:
        try:
            collect_current(conn)
            logger.info('Carbon readings total: %d', get_reading_count(conn))
            if consecutive_failures:
                logger.info(
                    'Carbon collector loop recovered after %d failure(s)',
                    consecutive_failures,
                )
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.error(
                'Error collecting carbon data (consecutive failures: %d)',
                consecutive_failures,
                exc_info=True,
            )
            if consecutive_failures >= _FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon collector has failed %d times in a row — no new carbon readings are being stored',
                    consecutive_failures,
                )
        time.sleep(CARBON_INTERVAL_MINUTES * 60)


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


@app.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=LoadForecastResponse,
    tags=['Forecasts'],
    summary='Get load forecast for next week',
    responses={
        500: {'model': ErrorResponse},
        404: {'model': ErrorResponse, 'description': 'Location not found'},
    },
)
def get_load_forecast(location: str):
    try:
        cache_key = f'load_forecast_{location}'
        cached_result = db_utils.get_cached_prediction(cache_key)
        if cached_result:
            return cached_result
        else:
            data = generate_next_week_load_prediction(location)
            db_utils.save_prediction(cache_key, data)
            return data

    except ValueError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    except Exception as e:
        print(f'Error processing request: {e}')
        return JSONResponse(status_code=500, content={'error': str(e)})


@app.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponse,
    tags=['Forecasts'],
    summary='Get carbon intensity forecast for next week',
    responses={
        500: {'model': ErrorResponse},
        404: {'model': ErrorResponse, 'description': 'Location not found'},
    },
)
def get_carbon_forecast(location: str):
    """
    Returns ML-generated carbon intensity predictions for the next week.
    Results are cached for 5 minutes.
    """
    try:
        cache_key = f'carbon_intensity_forecast_{location}'
        cached_result = db_utils.get_cached_prediction(cache_key)
        if cached_result:
            return cached_result
        else:
            data = generate_next_week_carbon_intensity_prediction(location)
            db_utils.save_prediction(cache_key, data)
            return data
    except ValueError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    except Exception as e:
        print(f'Error processing request: {e}')
        return JSONResponse(status_code=500, content={'error': str(e)})


@app.get(
    '/predictionWindow',
    response_model=PredictionWindowModel,
    tags=['PredictionWindowLength'],
    summary='Returns prediction window length in hours to the future.',
)
def handle_get_prediction_window() -> PredictionWindowModel:
    return PredictionWindowModel(windowLengthHours=PREDICTION_WINDOW_HOURS)


@app.get(
    '/locations',
    response_model=list[Location],
    tags=['Locations'],
    summary='Get available locations',
    responses={
        200: {
            'description': 'Successful Response',
            'links': {
                'GetLoadForecast': {
                    'operationId': 'get_load_forecast_locations__location__metrics_forecast_load_get',
                    'parameters': {'location': '$response.body#/0/id'},
                    'description': 'Get load forecast for a location from the list',
                },
                'GetCarbonIntensityForecast': {
                    'operationId': 'get_carbon_forecast_locations__location__metrics_forecast_carbon_intensity_get',
                    'parameters': {'location': '$response.body#/0/id'},
                    'description': 'Get carbon intensity forecast for a location from the list',
                },
            },
        }
    },
)
def get_locations() -> list[Location]:
    """Returns active locations for scheduler consumption."""
    datacenters = db_utils.get_datacenters(include_inactive=False)
    return [Location(id=dc['id'], name=dc['name']) for dc in datacenters]


@app.get(
    '/datacenters',
    response_model=list[Datacenter],
    tags=['Datacenters'],
    summary='Get all datacenters and active state',
)
def get_datacenters() -> list[Datacenter]:
    """Returns all known datacenters and active state for UI management."""
    datacenters = db_utils.get_datacenters(include_inactive=True)
    return [
        Datacenter(
            id=dc['id'],
            region_id=dc['region_id'],
            name=dc['name'],
            active=dc['active'],
            latitude=dc.get('latitude'),
            longitude=dc.get('longitude'),
        )
        for dc in datacenters
    ]


@app.patch(
    '/datacenters/{location_id}',
    response_model=Datacenter,
    tags=['Datacenters'],
    summary='Update datacenter active state',
    responses={
        404: {'model': ErrorResponse, 'description': 'Datacenter not found'},
    },
)
def patch_datacenter(location_id: str, payload: DatacenterPatchRequest):
    """Updates whether a datacenter is active for scheduler-visible locations."""
    updated = db_utils.set_datacenter_active(location_id, payload.active)
    if not updated:
        return JSONResponse(
            status_code=404,
            content={'error': f'Datacenter not found: {location_id}'},
        )

    datacenter = db_utils.get_datacenter(location_id)
    if not datacenter:
        return JSONResponse(
            status_code=500,
            content={'error': f'Failed to load updated datacenter: {location_id}'},
        )

    return Datacenter(
        id=datacenter['id'],
        region_id=datacenter['region_id'],
        name=datacenter['name'],
        active=datacenter['active'],
        latitude=datacenter.get('latitude'),
        longitude=datacenter.get('longitude'),
    )


if __name__ == '__main__':
    import uvicorn

    print(f'Starting Stats API on {HOST}:{PORT}')
    uvicorn.run(app, host=HOST, port=PORT)
