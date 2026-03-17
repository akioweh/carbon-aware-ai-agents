from fastapi import APIRouter, HTTPException

from .response_schemas import (
    ApiErrorResponseModel,
    CarbonIntensityForecastResponseModel,
    DatacenterLoadForecastResponseModel,
    DatacenterLocationResponseModel,
)
from ..core.settings import SUPPORTED_DATACENTER_NAMES
from ..database import repository
from ..services.forecasting_engine import (
    predict_carbon_intensity_for_next_seven_days,
    predict_datacenter_load_for_next_seven_days,
)

forecast_api_router = APIRouter()


@forecast_api_router.get(
    '/locations/{location}/metrics/forecast_load',
    response_model=DatacenterLoadForecastResponseModel,
    tags=['Forecasts'],
    summary='Get datacenter load forecast for next week',
    responses={
        500: {'model': ApiErrorResponseModel},
        404: {'model': ApiErrorResponseModel, 'description': 'Location not found'},
    },
)
def handle_get_datacenter_load_forecast_request(location: str):
    try:
        cache_lookup_key = f'load_forecast_{location}'
        cached_forecast_data = repository.retrieve_forecast_from_cache_database(
            cache_lookup_key
        )

        if cached_forecast_data:
            return cached_forecast_data

        generated_forecast_data = predict_datacenter_load_for_next_seven_days(location)
        repository.save_forecast_to_cache_database(
            cache_lookup_key, generated_forecast_data
        )
        return generated_forecast_data

    except ValueError as validation_error:
        raise HTTPException(status_code=404, detail=str(validation_error))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail='Internal server error while generating load forecast',
        )


@forecast_api_router.get(
    '/locations/{location}/metrics/forecast_carbon_intensity',
    response_model=CarbonIntensityForecastResponseModel,
    tags=['Forecasts'],
    summary='Get carbon intensity forecast for next week',
    responses={
        500: {'model': ApiErrorResponseModel},
        404: {'model': ApiErrorResponseModel, 'description': 'Location not found'},
    },
)
def handle_get_datacenter_carbon_forecast_request(location: str):
    try:
        cache_lookup_key = f'carbon_intensity_forecast_{location}'
        cached_forecast_data = repository.retrieve_forecast_from_cache_database(
            cache_lookup_key
        )

        if cached_forecast_data:
            return cached_forecast_data

        generated_forecast_data = predict_carbon_intensity_for_next_seven_days(location)
        repository.save_forecast_to_cache_database(
            cache_lookup_key, generated_forecast_data
        )
        return generated_forecast_data

    except ValueError as validation_error:
        raise HTTPException(status_code=404, detail=str(validation_error))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail='Internal server error while generating carbon forecast',
        )


@forecast_api_router.get(
    '/locations',
    response_model=list[DatacenterLocationResponseModel],
    tags=['Locations'],
    summary='Get list of supported datacenter locations',
)
def handle_get_supported_datacenters_request() -> list[DatacenterLocationResponseModel]:
    return [
        DatacenterLocationResponseModel(
            id=datacenter, name=datacenter.replace('-', ' ')
        )
        for datacenter in SUPPORTED_DATACENTER_NAMES
    ]
