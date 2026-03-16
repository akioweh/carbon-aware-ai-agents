from pydantic import BaseModel, Field


class Location(BaseModel):
    id: str = Field(..., description='Location identifier')
    name: str = Field(..., description='Human-readable name')


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
