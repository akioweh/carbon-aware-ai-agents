from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3
import json
import time
import threading
import yaml
import os
from contextlib import asynccontextmanager

from generate_history import DATA_CENTRES, generate_history
from predictor import (
    generate_next_week_load_prediction,
    generate_next_week_greenness_prediction,
)

DB_FILE = 'cache.db'
HISTORY_FILE = 'history.json'


class Location(BaseModel):
    id: str = Field(..., description='Location identifier')
    name: str = Field(..., description='Human-readable name')


class Capacity(BaseModel):
    max_load: float = Field(..., description='Maximum load capacity')
    total_gpus: int = Field(..., description='Total number of GPUs')


class BaseForecastDataPoint(BaseModel):
    timestamp: str = Field(..., description='ISO format timestamp')
    value: float = Field(..., description='Forecasted value')
    is_forecast: bool = Field(..., description='Indicates if this is a forecast')


class LoadForecastDataPoint(BaseForecastDataPoint):
    available_gpus: int = Field(..., description='Number of available GPUs')


class GreennessForecastDataPoint(BaseForecastDataPoint):
    pass


class BaseForecastResponse(BaseModel):
    location_id: str = Field(..., description='Datacenter identifier')
    metric: str = Field(
        ..., description='Metric name (e.g. forecast_load, forecast_greenness)'
    )
    unit: str = Field(..., description='Unit of measurement')


class LoadForecastResponse(BaseForecastResponse):
    capacity: Capacity = Field(..., description='Capacity information')
    data: list[LoadForecastDataPoint] = Field(..., description='Time series data')


class GreennessForecastResponse(BaseForecastResponse):
    data: list[GreennessForecastDataPoint] = Field(..., description='Time series data')


class ErrorResponse(BaseModel):
    error: str


def init_db():
    """Initialize the SQLite database for caching."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                key TEXT PRIMARY KEY,
                data TEXT,
                timestamp REAL
            )
        """)


def get_cached_prediction(key: str) -> Optional[dict]:
    """Get cached prediction if it exists and is less than 5 minutes old."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                'SELECT data, timestamp FROM predictions WHERE key = ?', (key,)
            )
            row = cursor.fetchone()

            if row:
                data_json, timestamp = row
                # Check if cache is fresh (less than 5 minutes old)
                if time.time() - timestamp < 300:  # 300 seconds = 5 minutes
                    return json.loads(data_json)
    except sqlite3.Error as e:
        print(f'Cache read error: {e}')
    return None


def save_prediction(key: str, data: dict):
    """Save prediction to cache with current timestamp."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO predictions (key, data, timestamp) VALUES (?, ?, ?)',
                (key, json.dumps(data), time.time()),
            )
    except sqlite3.Error as e:
        print(f'Cache write error: {e}')


def prediction_loop():
    """Background loop to update predictions every 5 minutes."""
    while True:
        print('Updating predictions cache...')
        for dc in DATA_CENTRES:
            try:
                load_data = generate_next_week_load_prediction(dc)
                save_prediction(f'load_forecast_{dc}', load_data)

                greenness_data = generate_next_week_greenness_prediction(dc)
                save_prediction(f'greenness_forecast_{dc}', greenness_data)
            except Exception as e:
                print(f'Error updating predictions for {dc}: {e}')

        time.sleep(300)


# does some housekeeping stuff including
# generating history and auto-updating the api schema file
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    if not os.path.exists(HISTORY_FILE):
        print('Generating history data...')
        generate_history()

    thread = threading.Thread(target=prediction_loop, daemon=True)
    thread.start()

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
        cached_result = get_cached_prediction(cache_key)
        if cached_result:
            return cached_result
        else:
            # when not in cache, we can either:
            # 1. generate immediately (slower response path), or
            # 2. return 404/503.
            # for now, we generate on-demand so the endpint is always "reliable"
            data = generate_next_week_load_prediction(location)
            save_prediction(cache_key, data)
            return data

    except ValueError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    except Exception as e:
        print(f'Error processing request: {e}')
        return JSONResponse(status_code=500, content={'error': str(e)})


@app.get(
    '/locations/{location}/metrics/forecast_greenness',
    response_model=GreennessForecastResponse,
    tags=['Forecasts'],
    summary='Get greenness forecast for next week',
    responses={
        500: {'model': ErrorResponse},
        404: {'model': ErrorResponse, 'description': 'Location not found'},
    },
)
def get_carbon_forecast(location: str):
    """
    Returns ML-generated greenness predictions for the next week.
    Results are cached for 5 minutes.
    """
    try:
        cache_key = f'greenness_forecast_{location}'
        cached_result = get_cached_prediction(cache_key)
        if cached_result:
            return cached_result
        else:
            data = generate_next_week_greenness_prediction(location)
            save_prediction(cache_key, data)
            return data
    except ValueError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    except Exception as e:
        print(f'Error processing request: {e}')
        return JSONResponse(status_code=500, content={'error': str(e)})


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
                'GetGreennessForecast': {
                    'operationId': 'get_carbon_forecast_locations__location__metrics_forecast_greenness_get',
                    'parameters': {'location': '$response.body#/0/id'},
                    'description': 'Get greenness forecast for a location from the list',
                },
            },
        }
    },
)
def get_locations() -> list[Location]:
    """Returns a list of available locations."""
    return [Location(id=dc, name=dc.replace('-', ' ')) for dc in DATA_CENTRES]


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, port=5000)
