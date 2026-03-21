"""API endpoint handlers."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BeforeValidator

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
    get_carbon_intensity_time_series,
    get_load_time_series,
)

logger = logging.getLogger('stats.routes')

router = APIRouter()


def _parse_flexible_datetime(v):
    if v == 'null':
        return None  # JavaScript shenanigans :(
    if isinstance(v, str) and not v.endswith('Z') and '+' not in v and '-' not in v[10:]:
        return v + 'Z'  # default to UTC if no timezone provided
    return v


FlexibleDatetime = Annotated[Optional[AwareDatetime], BeforeValidator(_parse_flexible_datetime)]


def get_time_window(
    start_time: Annotated[
        FlexibleDatetime,
        Query(
            description='Start of time window (ISO 8601)',
            openapi_examples={'default': {'value': '2026-03-18T00:00:00Z'}},
        ),
    ] = None,
    end_time: Annotated[
        FlexibleDatetime,
        Query(
            description='End of time window (ISO 8601)',
            openapi_examples={'default': {'value': '2026-03-25T00:00:00Z'}},
        ),
    ] = None,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)

    effective_start = start_time if start_time is not None else now
    effective_end = end_time if end_time is not None else now + timedelta(hours=PREDICTION_WINDOW_HOURS)

    max_end = now + timedelta(hours=PREDICTION_WINDOW_HOURS)
    if effective_end > max_end:
        raise HTTPException(
            status_code=422,
            detail=f'end_time cannot exceed the forecast window ({PREDICTION_WINDOW_HOURS}h from now)',
        )

    if effective_start >= effective_end:
        raise HTTPException(
            status_code=422,
            detail='start_time must be before end_time',
        )

    return effective_start, effective_end


@router.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=LoadForecastResponse,
    tags=['Forecasts'],
    summary='Load forecast for a location',
    description='Returns load data for the requested time window. Supports optional start_time and end_time query params (ISO 8601). Historical observations have is_forecast=false, predictions have is_forecast=true. Without params, returns a 7-day forecast from now.',
    responses={
        422: {
            'model': ErrorResponse,
            'description': 'Invalid time window (e.g. start after end, or exceeds forecast window)',
        },
        404: {
            'model': ErrorResponse,
            'description': 'No load data for this location',
        },
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_load_forecast(
    location: str,
    window: tuple[datetime, datetime] = Depends(get_time_window),
):
    effective_start, effective_end = window
    try:
        data = get_load_time_series(location, effective_start, effective_end)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error('Error generating load forecast for %s: %s', location, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return data


@router.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponse,
    tags=['Forecasts'],
    summary='Carbon intensity forecast for a location',
    description='Returns carbon intensity data for the requested time window. Supports optional start_time and end_time query params (ISO 8601). Historical observations have is_forecast=false, predictions have is_forecast=true. Without params, returns a 7-day forecast from now.',
    responses={
        422: {
            'model': ErrorResponse,
            'description': 'Invalid time window (e.g. start after end, or exceeds forecast window)',
        },
        404: {
            'model': ErrorResponse,
            'description': 'No carbon intensity data for this location',
        },
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_carbon_forecast(
    location: str,
    window: tuple[datetime, datetime] = Depends(get_time_window),
):
    effective_start, effective_end = window
    try:
        data = get_carbon_intensity_time_series(location, effective_start, effective_end)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error('Error generating CI forecast for %s: %s', location, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
        400: {'model': ErrorResponse, 'description': 'Malformed request body'},
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
