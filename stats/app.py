import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import db_utils
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
    id: str = Field(..., description='Location identifier', examples=['Data-Center-1'])
    name: str = Field(..., description='Human-readable region name', examples=['London'])


class Datacenter(BaseModel):
    id: str = Field(..., description='Location identifier', examples=['Data-Center-1'])
    region_id: int = Field(..., description='UK Carbon Intensity API region ID', examples=[13])
    name: str = Field(..., description='Human-readable region name', examples=['London'])
    active: bool = Field(..., description='Whether this datacenter is visible to the scheduler')
    latitude: float | None = Field(None, description='Latitude for weather lookups and map display', examples=[51.51])
    longitude: float | None = Field(None, description='Longitude for weather lookups and map display', examples=[-0.13])


class DatacenterPatchRequest(BaseModel):
    active: bool = Field(..., description='New active state for this datacenter')


class BaseForecastDataPoint(BaseModel):
    timestamp: str = Field(..., description='ISO 8601 timestamp', examples=['2026-03-18T12:00:00'])
    value: float = Field(..., description='Forecasted value')
    is_forecast: bool = Field(..., description='Always true for forecast endpoints')


class BaseForecastResponse(BaseModel):
    location_id: str = Field(..., description='Datacenter identifier', examples=['Data-Center-1'])
    metric: str = Field(..., description='Metric name', examples=['forecast_load', 'forecast_carbon_intensity'])
    unit: str = Field(..., description='Unit of measurement', examples=['FLOs', 'gCO2/kWh'])


class LoadForecastDataPoint(BaseForecastDataPoint):
    capacity: float = Field(..., description='Max computational capacity at this interval (FLOs)', examples=[9.84e17])


class LoadForecastResponse(BaseForecastResponse):
    data: list[LoadForecastDataPoint] = Field(..., description='2016-point time series (7 days at 5-min intervals)')


class CarbonIntensityForecastResponse(BaseForecastResponse):
    data: list[BaseForecastDataPoint] = Field(..., description='2016-point time series (7 days at 5-min intervals)')


class ErrorResponse(BaseModel):
    detail: str = Field(..., description='Error description')


class PredictionWindowModel(BaseModel):
    windowLengthHours: int = Field(..., description='Forecast window length in hours', examples=[168])


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
                count = db_utils.sync_carbon_to_historical()
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
            count = db_utils.sync_carbon_to_historical()
            logger.info('Synced %d carbon readings to historical data', count)
        except Exception:
            logger.error('Failed to sync carbon data on startup', exc_info=True)

    # Step 3: Start background threads
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


@app.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=LoadForecastResponse,
    tags=['Forecasts'],
    summary='Load forecast for a location',
    description='Returns a 7-day load forecast at 5-minute resolution (2016 data points). Each point includes the predicted load and the datacenter capacity in FLOs. Results are cached for 5 minutes.',
    responses={
        404: {'model': ErrorResponse, 'description': 'No historical data for this location'},
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_load_forecast(location: str):
    cache_key = f'load_forecast_{location}'
    cached_result = db_utils.get_cached_prediction(cache_key)
    if cached_result:
        return cached_result

    try:
        data = generate_next_week_load_prediction(location)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error('Error generating load forecast for %s: %s', location, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    db_utils.save_prediction(cache_key, data)
    return data


@app.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponse,
    tags=['Forecasts'],
    summary='Carbon intensity forecast for a location',
    description='Returns a 7-day carbon intensity forecast at 5-minute resolution (2016 data points) in gCO2/kWh. Uses Ridge regression trained on UK Carbon Intensity API data with weather exogenous features. Results are cached for 5 minutes.',
    responses={
        404: {'model': ErrorResponse, 'description': 'No carbon intensity data for this location'},
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_carbon_forecast(location: str):
    cache_key = f'carbon_intensity_forecast_{location}'
    cached_result = db_utils.get_cached_prediction(cache_key)
    if cached_result:
        return cached_result

    try:
        data = generate_next_week_carbon_intensity_prediction(location)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error('Error generating CI forecast for %s: %s', location, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    db_utils.save_prediction(cache_key, data)
    return data


@app.get(
    '/predictionWindow',
    response_model=PredictionWindowModel,
    tags=['Configuration'],
    summary='Prediction window length',
    description='Returns the forecast window length in hours. Currently fixed at 168 hours (7 days).',
)
def handle_get_prediction_window() -> PredictionWindowModel:
    return PredictionWindowModel(windowLengthHours=PREDICTION_WINDOW_HOURS)


@app.get(
    '/locations',
    response_model=list[Location],
    tags=['Locations'],
    summary='Active locations',
    description='Returns locations that are currently active and visible to the scheduler. Use a location ID from this list to query forecast endpoints.',
    responses={
        200: {
            'description': 'List of active locations',
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
    summary='All datacenters',
    description='Returns all known datacenters (active and inactive) with their region metadata and coordinates. Used by the UI for datacenter management.',
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
    summary='Toggle datacenter active state',
    description='Activates or deactivates a datacenter. Active datacenters appear in /locations and receive scheduled forecasts.',
    responses={
        404: {'model': ErrorResponse, 'description': 'Datacenter not found'},
        500: {'model': ErrorResponse, 'description': 'Failed to reload datacenter after update'},
    },
)
def patch_datacenter(location_id: str, payload: DatacenterPatchRequest):
    """Updates whether a datacenter is active for scheduler-visible locations."""
    updated = db_utils.set_datacenter_active(location_id, payload.active)
    if not updated:
        raise HTTPException(status_code=404, detail=f'Datacenter not found: {location_id}')

    datacenter = db_utils.get_datacenter(location_id)
    if not datacenter:
        raise HTTPException(status_code=500, detail=f'Failed to load updated datacenter: {location_id}')

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
