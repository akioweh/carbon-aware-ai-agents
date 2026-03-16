from datetime import datetime, timedelta

import pandas as pd

import db_utils
from different_prediction_models.predictor_direct_ridge import (
    get_next_week_carbon_intensity,
)
from different_prediction_models.predictor_load import get_next_week_load

DEFAULT_CAPACITY = 50.0 * 1e12


def generate_next_week_load_prediction(location):
    """Generate load predictions for the next week at a specific location."""
    now = pd.Timestamp.now().ceil('5min')
    # Get history for specific location from database
    # optimization: limit to 60 days of data
    start_time = datetime.now() - timedelta(days=60)
    location_history = db_utils.get_historical_data(location, start_time=start_time)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_load = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'load': entry['load'],
            }
            for entry in location_history
        ]
    )
    next_week_load_df = get_next_week_load(historical_load, now=now)

    # Format as unified metric time-series
    return {
        'location_id': location,
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': [
            {
                'timestamp': next_week_load_df.iloc[i]['ds'].isoformat(),
                'value': max(0.0, float(next_week_load_df.iloc[i]['yhat'])),
                'is_forecast': True,
                'capacity': DEFAULT_CAPACITY,
            }
            for i in range(len(next_week_load_df))
        ],
    }


def generate_next_week_carbon_intensity_prediction(location):
    """Generate carbon intensity predictions for the next week at a specific location."""
    now = pd.Timestamp.now().ceil('5min')
    # Get history for specific location from database
    # optimization: limit to 60 days of data
    start_time = datetime.now() - timedelta(days=60)
    location_history = db_utils.get_historical_data(location, start_time=start_time)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_carbon_intensity = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'carbon_intensity': entry['carbon_intensity'],
                'location': location,
            }
            for entry in location_history
        ]
    )

    next_week_carbon_intensity_df = get_next_week_carbon_intensity(
        historical_carbon_intensity, now=now
    )

    # Format as unified metric time-series
    data = []
    for i in range(len(next_week_carbon_intensity_df)):
        row = next_week_carbon_intensity_df.iloc[i]
        point = {
            'timestamp': row['ds'].isoformat(),
            'value': max(0.0, float(row['yhat'])),
            'is_forecast': True,
        }
        data.append(point)

    return {
        'location_id': location,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2eq/kWh',
        'data': data,
    }
