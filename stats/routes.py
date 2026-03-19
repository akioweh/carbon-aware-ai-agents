"""API endpoint handlers."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
    get_load_time_series,
    get_carbon_intensity_time_series,
)

logger = logging.getLogger('stats.routes')

router = APIRouter()


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 string to a UTC-aware datetime.

    Returns None for absent, empty, or unparseable values so that
    invalid query params are silently treated as "no filter".
    """
    if not value or value.lower() == 'null':
        return None
    try:
        value = value.replace('Z', '+00:00')
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


@router.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=LoadForecastResponse,
    tags=['Forecasts'],
    summary='Load forecast for a location',
    description='Returns load data for the requested time window. Supports optional start_time and end_time query params (ISO 8601). Historical observations have is_forecast=false, predictions have is_forecast=true. Without params, returns all available history plus a 7-day forecast.',
    responses={
        404: {
            'model': ErrorResponse,
            'description': 'No historical data for this location',
        },
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_load_forecast(
    location: str,
    start_time: Optional[str] = Query(None, description='Start of time window (ISO 8601, e.g. 2026-03-18T00:00:00Z)'),
    end_time: Optional[str] = Query(None, description='End of time window (ISO 8601, e.g. 2026-03-25T00:00:00Z)'),
):
    parsed_start = _parse_iso_timestamp(start_time)
    parsed_end = _parse_iso_timestamp(end_time)

    if parsed_start and parsed_end and parsed_start >= parsed_end:
        raise HTTPException(
            status_code=422,
            detail='start_time must be before end_time',
        )

    try:
        data = get_load_time_series(location, parsed_start, parsed_end)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            'Error generating load forecast for %s: %s', location, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))

    return data


@router.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponse,
    tags=['Forecasts'],
    summary='Carbon intensity forecast for a location',
    description='Returns carbon intensity data for the requested time window. Supports optional start_time and end_time query params (ISO 8601). Historical observations have is_forecast=false, predictions have is_forecast=true. Without params, returns all available history plus a 7-day forecast.',
    responses={
        404: {
            'model': ErrorResponse,
            'description': 'No carbon intensity data for this location',
        },
        500: {'model': ErrorResponse, 'description': 'Prediction generation failed'},
    },
)
def get_carbon_forecast(
    location: str,
    start_time: Optional[str] = Query(None, description='Start of time window (ISO 8601, e.g. 2026-03-18T00:00:00Z)'),
    end_time: Optional[str] = Query(None, description='End of time window (ISO 8601, e.g. 2026-03-25T00:00:00Z)'),
):
    parsed_start = _parse_iso_timestamp(start_time)
    parsed_end = _parse_iso_timestamp(end_time)

    if parsed_start and parsed_end and parsed_start >= parsed_end:
        raise HTTPException(
            status_code=422,
            detail='start_time must be before end_time',
        )

    try:
        data = get_carbon_intensity_time_series(location, parsed_start, parsed_end)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            'Error generating CI forecast for %s: %s', location, e, exc_info=True
        )
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
