from datetime import datetime

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)


def transformLatitudeToLocation(latitude: str) -> str:
    return "Data-Center-" + latitude


def transformFromGramToPounds(obj):
    conversionRateGramsToPounds = 2.20462262
    return {
        k: (v * conversionRateGramsToPounds if k == "value" else v)
        for k, v in obj.items()
    }


def getForecastDataForLocation(location: str):
    statsAPICIEndpoint = f"http://140.238.79.139:5000//locations/{location}/metrics/forecast_carbon_intensity"

    try:
        response = requests.get(statsAPICIEndpoint, timeout=10)
        response.raise_for_status()
        external_data = response.json()
        data = [
            {"point_time": point["timestamp"], "value": point["value"]}
            for point in external_data.get("data", [])
        ]
    except Exception:
        print("ERROR fetching from python API")
        data = []
    return [transformFromGramToPounds(item) for item in data]


@app.route("/login", methods=["GET"])
def login():
    return jsonify({"token": "mock_token"})


@app.route("/region-from-loc", methods=["GET"])
def region_from_loc():
    lat = request.args.get("latitude")
    cleaned_lat = str(lat)

    location = transformLatitudeToLocation(cleaned_lat)

    jsonResp = jsonify(
        {"region": location, "region_full_name": location, "signal_type": "co2_moer"}
    )

    return jsonResp


@app.route("/forecast", methods=["GET"])
def forecast():
    location = request.args.get("region")

    if not location:
        Exception("not correct region provided")

    curr_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    jsonResp = jsonify(
        {
            "generated_at": curr_time_str,
            "data": getForecastDataForLocation(location),
            "meta": {"region": location, "units": "lbs/MWh"},
        }
    )

    return jsonResp


if __name__ == "__main__":
    app.run(port=5000)
