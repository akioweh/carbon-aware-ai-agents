"""Pydantic request/response models for the Stats API."""

from typing import Any

from pydantic import BaseModel, Field


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
    is_forecast: bool = Field(..., description='True for predicted data, False for historical observations')


class BaseForecastResponse(BaseModel):
    location_id: str = Field(..., description='Datacenter identifier', examples=['Data-Center-1'])
    metric: str = Field(..., description='Metric name', examples=['forecast_load', 'forecast_carbon_intensity'])
    unit: str = Field(..., description='Unit of measurement', examples=['FLOs', 'gCO2/kWh'])


class LoadForecastDataPoint(BaseForecastDataPoint):
    capacity: float = Field(..., description='Max computational capacity at this interval (FLOs)', examples=[9.84e17])


class LoadForecastResponse(BaseForecastResponse):
    data: list[LoadForecastDataPoint] = Field(..., description='Time series data points within the requested window')


class CarbonIntensityForecastResponse(BaseForecastResponse):
    data: list[BaseForecastDataPoint] = Field(..., description='Time series data points within the requested window')


class ErrorResponse(BaseModel):
    detail: str | list[Any] = Field(..., description='Error description (string for app errors, array for validation errors)')


class PredictionWindowModel(BaseModel):
    windowLengthHours: int = Field(..., description='Forecast window length in hours', examples=[168])
