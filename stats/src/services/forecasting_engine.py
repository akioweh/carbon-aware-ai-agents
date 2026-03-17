from datetime import datetime, timedelta

import pandas as pd

from different_prediction_models.predictor_direct_ridge import (
    get_next_week_carbon_intensity,
)
from different_prediction_models.predictor_load import get_next_week_load
from src.core.settings import TOTAL_SCALED_DATACENTER_CAPACITY
from src.database import repository


def predict_datacenter_load_for_next_seven_days(datacenter_location_id):
    """Generates load predictions for the next week at a specific datacenter."""
    current_time_rounded = pd.Timestamp.now().ceil('5min')
    history_start_time = datetime.now() - timedelta(days=60)

    historical_data_records = repository.fetch_historical_metrics_for_datacenter(
        datacenter_location_id, start_datetime=history_start_time
    )

    if not historical_data_records:
        raise ValueError(
            f'No history found for datacenter location: {datacenter_location_id}'
        )

    historical_load_dataframe = pd.DataFrame(
        [
            {'timestamp': record['timestamp'], 'load': record['load']}
            for record in historical_data_records
        ]
    )

    forecast_dataframe = get_next_week_load(
        historical_load_dataframe, now=current_time_rounded
    )

    return {
        'location_id': datacenter_location_id,
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': [
            {
                'timestamp': forecast_dataframe.iloc[i]['ds'].isoformat(),
                'value': max(0.0, float(forecast_dataframe.iloc[i]['yhat'])),
                'is_forecast': True,
                'capacity': TOTAL_SCALED_DATACENTER_CAPACITY,
            }
            for i in range(len(forecast_dataframe))
        ],
    }


def predict_carbon_intensity_for_next_seven_days(datacenter_location_id):
    """Generates carbon intensity predictions for the next week at a specific datacenter."""
    current_time_rounded = pd.Timestamp.now().ceil('5min')
    history_start_time = datetime.now() - timedelta(days=60)

    historical_data_records = repository.fetch_historical_metrics_for_datacenter(
        datacenter_location_id, start_datetime=history_start_time
    )

    if not historical_data_records:
        raise ValueError(
            f'No history found for datacenter location: {datacenter_location_id}'
        )

    historical_carbon_dataframe = pd.DataFrame(
        [
            {
                'timestamp': record['timestamp'],
                'carbon_intensity': record['carbon_intensity'],
                'location': datacenter_location_id,
            }
            for record in historical_data_records
        ]
    )

    forecast_dataframe = get_next_week_carbon_intensity(
        historical_carbon_dataframe, now=current_time_rounded
    )

    forecast_timeseries_data = []
    for i in range(len(forecast_dataframe)):
        dataframe_row = forecast_dataframe.iloc[i]
        forecast_timeseries_data.append(
            {
                'timestamp': dataframe_row['ds'].isoformat(),
                'value': max(0.0, float(dataframe_row['yhat'])),
                'is_forecast': True,
            }
        )

    return {
        'location_id': datacenter_location_id,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2eq/kWh',
        'data': forecast_timeseries_data,
    }
