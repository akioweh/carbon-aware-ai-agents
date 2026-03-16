from fastapi import APIRouter, HTTPException

import db_utils
from generate_history import DATA_CENTRES
from predictor import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)
from schemas import (
    CarbonIntensityForecastResponse,
    ErrorResponse,
    LoadForecastResponse,
    Location,
)

router = APIRouter()


@router.get(
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
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
    """Returns a list of available locations."""
    return [Location(id=dc, name=dc.replace('-', ' ')) for dc in DATA_CENTRES]
