"""API endpoint handlers."""

import logging

from fastapi import APIRouter, HTTPException

import db_utils
from config import PREDICTION_WINDOW_HOURS
from models import (
    CarbonIntensityForecastResponse,
    Datacenter,
    DatacenterPatchRequest,
    ErrorResponse,
    LoadForecastResponse,
    Location,
    PredictionWindowModel,
)
from predictors import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)

logger = logging.getLogger('stats.routes')

router = APIRouter()


@router.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=LoadForecastResponse,
    tags=['Forecasts'],
    summary='Load forecast for a location',
    description='Returns a 7-day load forecast at 5-minute resolution (2016 data points). Each point includes the predicted load and the datacenter capacity in FLOs. Results are cached for 5 minutes.',
    responses={
        404: {
            'model': ErrorResponse,
            'description': 'No historical data for this location',
        },
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_load_forecast(location: str):
    print(f'load_forecast_{location}')
    cache_key = f'load_forecast_{location}'
    cached_result = db_utils.get_cached_prediction(cache_key)
    if cached_result:
        return cached_result

    try:
        data = generate_next_week_load_prediction(location)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            'Error generating load forecast for %s: %s', location, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))

    db_utils.save_prediction(cache_key, data)
    return data


@router.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponse,
    tags=['Forecasts'],
    summary='Carbon intensity forecast for a location',
    description='Returns a 7-day carbon intensity forecast at 5-minute resolution (2016 data points) in gCO2/kWh. Uses Ridge regression trained on UK Carbon Intensity API data with weather exogenous features. Results are cached for 5 minutes.',
    responses={
        404: {
            'model': ErrorResponse,
            'description': 'No carbon intensity data for this location',
        },
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
        logger.error(
            'Error generating CI forecast for %s: %s', location, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))

    db_utils.save_prediction(cache_key, data)
    return data


@router.get(
    '/predictionWindow',
    response_model=PredictionWindowModel,
    tags=['Configuration'],
    summary='Prediction window length',
    description='Returns the forecast window length in hours. Currently fixed at 168 hours (7 days).',
)
def handle_get_prediction_window() -> PredictionWindowModel:
    return PredictionWindowModel(windowLengthHours=PREDICTION_WINDOW_HOURS)


@router.get(
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


@router.get(
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


@router.patch(
    '/datacenters/{location_id}',
    response_model=Datacenter,
    tags=['Datacenters'],
    summary='Toggle datacenter active state',
    description='Activates or deactivates a datacenter. Active datacenters appear in /locations and receive scheduled forecasts.',
    responses={
        404: {'model': ErrorResponse, 'description': 'Datacenter not found'},
        500: {
            'model': ErrorResponse,
            'description': 'Failed to reload datacenter after update',
        },
    },
)
def patch_datacenter(location_id: str, payload: DatacenterPatchRequest):
    """Updates whether a datacenter is active for scheduler-visible locations."""
    updated = db_utils.set_datacenter_active(location_id, payload.active)
    if not updated:
        raise HTTPException(
            status_code=404, detail=f'Datacenter not found: {location_id}'
        )

    datacenter = db_utils.get_datacenter(location_id)
    if not datacenter:
        raise HTTPException(
            status_code=500, detail=f'Failed to load updated datacenter: {location_id}'
        )

    return Datacenter(
        id=datacenter['id'],
        region_id=datacenter['region_id'],
        name=datacenter['name'],
        active=datacenter['active'],
        latitude=datacenter.get('latitude'),
        longitude=datacenter.get('longitude'),
    )
