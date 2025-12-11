import json
from datetime import datetime
from prophet import Prophet as p
import pandas as pd

def generate_next_week():
    with open("history.json", "r") as f:
        history_json = json.load(f)
    
    historical_load = pd.DataFrame([
        {
            "timestamp": datetime.fromisoformat(entry["timestamp"]),
            "load": entry["load"]
        }
        for entry in history_json
    ])
    next_week_load_df = get_next_week_load(historical_load)
    
    historical_greenness = pd.DataFrame([
        {
            "timestamp": datetime.fromisoformat(entry["timestamp"]),
            "greenness": entry["greenness"]
        }
        for entry in history_json
    ])

    next_week_greenness_df = get_next_week_greenness(historical_greenness)

    predictions = []
    for i in range(len(next_week_load_df)):
        predictions.append({
            "timestamp": next_week_load_df.iloc[i]['ds'].isoformat(),
            "predicted_load": float(next_week_load_df.iloc[i]['yhat']),
            "predicted_greenness": float(next_week_greenness_df.iloc[i]['yhat'])
        })
    
    
    with open("prediction.json", "w") as f:
        json.dump(predictions, f, indent=2)
    
    print("prediction.json generated.")

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
    generate_next_week()
    