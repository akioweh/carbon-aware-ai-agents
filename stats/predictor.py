import json
from datetime import datetime
from prophet import Prophet as p
import pandas as pd

def generate_next_week_load_prediction(location):
    """Generate load predictions for the next week at a specific location."""
    with open("history.json", "r") as f:
        history_json = json.load(f)

    # Get history for specific location
    location_history = history_json.get(location, [])
    
    historical_load = pd.DataFrame([
        {
            "timestamp": datetime.fromisoformat(entry["timestamp"]),
            "load": entry["load"]
        }
        for entry in location_history
    ])
    next_week_load_df = get_next_week_load(historical_load)
    
    # Format as unified metric time-series
    return {
        "location_id": location,
        "metric": "load",
        "unit": "utilization_units",
        "capacity": {
            "max_load": 50.0,
            "total_gpus": 32
        },
        "data": [
            {
                "timestamp": next_week_load_df.iloc[i]['ds'].isoformat(),
                "value": max(0.0, float(next_week_load_df.iloc[i]['yhat'])),
                "is_forecast": True,
                "available_gpus": max(0, int(32 - (next_week_load_df.iloc[i]['yhat'] / 50.0 * 32)))
            }
            for i in range(len(next_week_load_df))
        ]
    }

def generate_next_week_greenness_prediction(location):
    """Generate greenness/carbon predictions for the next week at a specific location."""
    with open("history.json", "r") as f:
        history_json = json.load(f)

    # Get history for specific location
    location_history = history_json.get(location, [])
    
    historical_greenness = pd.DataFrame([
        {
            "timestamp": datetime.fromisoformat(entry["timestamp"]),
            "greenness": entry["greenness"]
        }
        for entry in location_history
    ])
    
    next_week_greenness_df = get_next_week_greenness(historical_greenness)
    
    # Format as unified metric time-series
    # Note: greenness is inverse of carbon intensity for this prototype
    return {
        "location_id": location,
        "metric": "carbon_intensity",
        "unit": "greenness_score",
        "data": [
            {
                "timestamp": next_week_greenness_df.iloc[i]['ds'].isoformat(),
                "value": max(0.0, min(100.0, float(next_week_greenness_df.iloc[i]['yhat']))),
                "is_forecast": True
            }
            for i in range(len(next_week_greenness_df))
        ]
    }

def get_next_week_load(historical_load):
    historical_load = historical_load.rename(columns={'timestamp': 'ds', 'load': 'y'})
    model = p(daily_seasonality=True, weekly_seasonality=True)
    model.fit(historical_load)
    future = model.make_future_dataframe(periods=288*7, freq="5min")
    prediction = model.predict(future)
    prediction['yhat'] = prediction['yhat'].clip(0, 100)
    prediction['yhat_lower'] = prediction['yhat_lower'].clip(0, 100)
    prediction['yhat_upper'] = prediction['yhat_upper'].clip(0, 100)
    return prediction

def get_next_week_greenness(historical_greenness):
    historical_greenness = historical_greenness.rename(columns={'timestamp': 'ds', 'greenness': 'y'})
    model = p(daily_seasonality=True, weekly_seasonality=True)
    model.fit(historical_greenness)
    future = model.make_future_dataframe(periods=288*7, freq="5min")
    prediction = model.predict(future)
    prediction['yhat'] = prediction['yhat'].clip(0, 100)
    prediction['yhat_lower'] = prediction['yhat_lower'].clip(0, 100)
    prediction['yhat_upper'] = prediction['yhat_upper'].clip(0, 100)
    return prediction

    
if __name__ == "__main__":
    all_predictions = {}
    
    for dc in [f"Data Centre {i}" for i in range(1,6)]:
        # Test the prediction functions
        load_pred = generate_next_week_load_prediction(dc)
        print(f"Generated {len(load_pred['data'])} load predictions for {dc}")
        
        greenness_pred = generate_next_week_greenness_prediction(dc)
        print(f"Generated {len(greenness_pred['data'])} greenness predictions for {dc}")

        # Store predictions for this data centre
        all_predictions[dc] = {
            "load_prediction": load_pred,
            "greenness_prediction": greenness_pred
        }

    # Save all predictions to JSON file
    with open("predictions.json", "w") as f:
        json.dump(all_predictions, f, indent=2)

    print("Predictions saved to predictions.json")
    