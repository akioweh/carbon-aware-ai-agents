from pydantic import BaseModel, Field


class DatacenterLocationResponseModel(BaseModel):
    id: str = Field(..., description='Datacenter location identifier')
    name: str = Field(..., description='Human-readable name of the datacenter')


class GenericForecastTimepointModel(BaseModel):
    timestamp: str = Field(
        ..., description='ISO 8601 format timestamp representing the prediction time'
    )
    value: float = Field(..., description='The forecasted numerical value')
    is_forecast: bool = Field(
        ...,
        description='Boolean flag indicating if this data point is a future forecast',
    )


class GenericForecastResponseMetadataModel(BaseModel):
    location_id: str = Field(..., description='Datacenter identifier')
    metric: str = Field(
        ...,
        description='The metric name (e.g. forecast_load, forecast_carbon_intensity)',
    )
    unit: str = Field(..., description='Unit of measurement for the forecasted values')


class DatacenterLoadForecastTimepointModel(GenericForecastTimepointModel):
    capacity: float = Field(
        ...,
        description='Total computational capacity available at this timestamp (in FLOs)',
    )


class DatacenterLoadForecastResponseModel(GenericForecastResponseMetadataModel):
    data: list[DatacenterLoadForecastTimepointModel] = Field(
        ..., description='Time series list of load predictions'
    )


class CarbonIntensityForecastResponseModel(GenericForecastResponseMetadataModel):
    data: list[GenericForecastTimepointModel] = Field(
        ..., description='Time series list of carbon intensity predictions'
    )


class ApiErrorResponseModel(BaseModel):
    error_message: str
