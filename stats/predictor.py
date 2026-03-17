import json
from datetime import datetime, timedelta

import pandas as pd

import db_utils
from predictor_load import get_next_week_load
from predictor_direct_ridge import get_next_week_carbon_intensity


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
                'location': location,
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


if __name__ == '__main__':
    all_predictions = {}

    db_utils.initialize_db()
    data_centres = db_utils.get_all_datacenter_ids(include_inactive=True)

    for dc in data_centres:
        # Test the prediction functions
        load_pred = generate_next_week_load_prediction(dc)
        print(f'Generated {len(load_pred["data"])} load predictions for {dc}')

        greenness_pred = generate_next_week_greenness_and_ci_prediction(dc)
        print(f'Generated {len(greenness_pred["data"])} greenness predictions for {dc}')

        try:
            ci_pred = generate_next_week_carbon_intensity_prediction(dc)
            print(f'Generated {len(ci_pred["data"])} carbon intensity predictions for {dc}')
        except ValueError as exc:
            ci_pred = {'error': str(exc)}
            print(f'Skipping carbon intensity for {dc}: {exc}')

        # Store predictions for this data centre
        all_predictions[dc] = {
            'load_prediction': load_pred,
            'greenness_prediction': greenness_pred,
            'carbon_intensity_prediction': ci_pred,
        }

    # Save all predictions to JSON file
    with open('predictions.json', 'w') as f:
        json.dump(all_predictions, f, indent=2)

    print('Predictions saved to predictions.json')
