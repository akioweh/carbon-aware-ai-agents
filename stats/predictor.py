from datetime import datetime, timedelta

import pandas as pd

import db_utils
from generate_history import DC_GPU_CONFIGS, dc_base_capacity
from predictor_load import get_next_week_load
from predictor_direct_ridge import get_next_week_carbon_intensity


def _dc_index_for_location(location: str) -> int:
    """Return the DC_GPU_CONFIGS index for a named datacenter (default: 0)."""
    for idx, (name, _, _) in enumerate(DC_GPU_CONFIGS):
        if name == location:
            return idx
    return 0


def _capacity_for_location(location: str) -> float:
    """Return the base FLO capacity per 5-min block for a named datacenter.

    Falls back to the first datacenter's capacity if the location is not found
    in DC_GPU_CONFIGS.
    """
    for idx, (name, _, _) in enumerate(DC_GPU_CONFIGS):
        if name == location:
            return dc_base_capacity(idx)
    return dc_base_capacity(0)


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
    next_week_load_df = get_next_week_load(historical_load, now=now, dc_index=_dc_index_for_location(location))

    # Format as unified metric time-series
    capacity = _capacity_for_location(location)
    return {
        'location_id': location,
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': [
            {
                'timestamp': next_week_load_df.iloc[i]['ds'].isoformat(),
                'value': max(0.0, float(next_week_load_df.iloc[i]['yhat'])),
                'is_forecast': True,
                'capacity': capacity,
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
