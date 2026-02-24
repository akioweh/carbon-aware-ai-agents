import json
from datetime import datetime, timedelta

import pandas as pd

import db_utils
from predictor_linreg import get_next_week_load, get_next_week_greenness


def generate_next_week_load_prediction(location):
    """Generate load predictions for the next week at a specific location."""
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
    next_week_load_df = get_next_week_load(historical_load)

    # Format as unified metric time-series
    return {
        'location_id': location,
        'metric': 'forecast_load',
        'unit': 'utilization_units',
        'capacity': {'max_load': 50.0, 'total_gpus': 32},
        'data': [
            {
                'timestamp': next_week_load_df.iloc[i]['ds'].isoformat(),
                'value': max(0.0, float(next_week_load_df.iloc[i]['yhat'])),
                'is_forecast': True,
                'available_gpus': max(
                    0, int(32 - (next_week_load_df.iloc[i]['yhat'] / 50.0 * 32))
                ),
            }
            for i in range(len(next_week_load_df))
        ],
    }


def generate_next_week_greenness_prediction(location):
    """Generate greenness/carbon predictions for the next week at a specific location."""
    # Get history for specific location from database
    # optimization: limit to 60 days of data
    start_time = datetime.now() - timedelta(days=60)
    location_history = db_utils.get_historical_data(location, start_time=start_time)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_greenness = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'greenness': entry['greenness'],
            }
            for entry in location_history
        ]
    )

    next_week_greenness_df = get_next_week_greenness(historical_greenness)

    # Format as unified metric time-series
    # Note: greenness is inverse of carbon intensity for this prototype
    return {
        'location_id': location,
        'metric': 'forecast_greenness',
        'unit': 'greenness_score',
        'data': [
            {
                'timestamp': next_week_greenness_df.iloc[i]['ds'].isoformat(),
                'value': max(
                    0.0, min(100.0, float(next_week_greenness_df.iloc[i]['yhat']))
                ),
                'is_forecast': True,
            }
            for i in range(len(next_week_greenness_df))
        ],
    }


from generate_history import DATA_CENTRES

if __name__ == '__main__':
    all_predictions = {}

    for dc in DATA_CENTRES:
        # Test the prediction functions
        load_pred = generate_next_week_load_prediction(dc)
        print(f'Generated {len(load_pred["data"])} load predictions for {dc}')

        greenness_pred = generate_next_week_greenness_prediction(dc)
        print(f'Generated {len(greenness_pred["data"])} greenness predictions for {dc}')

        # Store predictions for this data centre
        all_predictions[dc] = {
            'load_prediction': load_pred,
            'greenness_prediction': greenness_pred,
        }

    # Save all predictions to JSON file
    with open('predictions.json', 'w') as f:
        json.dump(all_predictions, f, indent=2)

    print('Predictions saved to predictions.json')
