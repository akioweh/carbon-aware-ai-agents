import json

import pandas as pd

import db_utils
from .ridge import get_next_week_carbon_intensity
from .load import get_next_week_load

# Number of GPUs per data center (uniform across all locations)
GPUS_PER_DATACENTER = 200
# FLOs per GPU per 5-minute interval (derived from hardware specs)
FLOS_PER_GPU = 4.92e15
# Maximum computational capacity per data center per interval (in FLOs)
DEFAULT_CAPACITY = GPUS_PER_DATACENTER * FLOS_PER_GPU


def generate_next_week_load_prediction(location):
    """Generate load predictions for the next week at a specific location."""
    now = pd.Timestamp.now().ceil('5min')
    location_history = db_utils.get_historical_data(location)

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
    location_history = db_utils.get_historical_data(location)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_df = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'carbon_intensity': entry.get('carbon_intensity'),
                'location': location,
            }
            for entry in location_history
        ]
    )

    if historical_df['carbon_intensity'].isna().all():
        raise ValueError(f'No carbon intensity data available for location: {location}')

    next_week_ci_df = get_next_week_carbon_intensity(historical_df, now=now)

    return {
        'location_id': location,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2/kWh',
        'data': [
            {
                'timestamp': next_week_ci_df.iloc[i]['ds'].isoformat(),
                'value': float(next_week_ci_df.iloc[i]['yhat']),
                'is_forecast': True,
            }
            for i in range(len(next_week_ci_df))
        ],
    }


if __name__ == '__main__':
    all_predictions = {}

    db_utils.initialize_db()
    data_centres = db_utils.get_all_datacenter_ids(include_inactive=True)

    for dc in data_centres:
        load_pred = generate_next_week_load_prediction(dc)
        print(f'Generated {len(load_pred["data"])} load predictions for {dc}')

        try:
            ci_pred = generate_next_week_carbon_intensity_prediction(dc)
            print(
                f'Generated {len(ci_pred["data"])} carbon intensity predictions for {dc}'
            )
        except ValueError as exc:
            ci_pred = {'error': str(exc)}
            print(f'Skipping carbon intensity for {dc}: {exc}')

        all_predictions[dc] = {
            'load_prediction': load_pred,
            'carbon_intensity_prediction': ci_pred,
        }

    with open('predictions.json', 'w') as f:
        json.dump(all_predictions, f, indent=2)

    print('Predictions saved to predictions.json')
