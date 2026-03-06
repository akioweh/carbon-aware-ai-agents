import json
from datetime import datetime, timedelta

import pandas as pd

import db_utils
from predictor_load import get_next_week_load
from predictor_sarimax import get_next_week_greenness, get_next_week_carbon_intensity


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


def generate_next_week_greenness_and_ci_prediction(location):
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
                'carbon_intensity': entry.get('carbon_intensity'),
            }
            for entry in location_history
        ]
    )

    next_week_greenness_df = get_next_week_greenness(historical_greenness)

    has_ci = 'ci' in next_week_greenness_df.columns

    # Format as unified metric time-series
    # Note: greenness is inverse of carbon intensity for this prototype
    data = []
    for i in range(len(next_week_greenness_df)):
        row = next_week_greenness_df.iloc[i]
        point = {
            'timestamp': row['ds'].isoformat(),
            'value': max(0.0, min(100.0, float(row['yhat']))),
            'is_forecast': True,
        }
        if has_ci:
            point['carbon_intensity'] = max(0.0, min(500.0, float(row['ci'])))
        data.append(point)

    return {
        'location_id': location,
        'metric': 'forecast_greenness',
        'unit': 'greenness_score',
        'data': data,
    }



def generate_next_week_carbon_intensity_prediction(location):
    """Generate carbon intensity predictions for the next week at a specific location."""
    start_time = datetime.now() - timedelta(days=60)
    location_history = db_utils.get_historical_data(location, start_time=start_time)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_df = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'carbon_intensity': entry.get('carbon_intensity'),
            }
            for entry in location_history
        ]
    )

    if historical_df['carbon_intensity'].isna().all():
        raise ValueError(f'No carbon intensity data available for location: {location}')

    next_week_ci_df = get_next_week_carbon_intensity(historical_df)

    return {
        'location_id': location,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2/kWh',
        'data': [
            {
                'timestamp': next_week_ci_df.iloc[i]['ds'].isoformat(),
                'value': max(0.0, min(500.0, float(next_week_ci_df.iloc[i]['yhat']))),
                'is_forecast': True,
            }
            for i in range(len(next_week_ci_df))
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
