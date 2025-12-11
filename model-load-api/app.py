from flask import Flask, jsonify
import json
from predictor import generate_next_week_load_prediction, generate_next_week_greenness_prediction

app = Flask(__name__)

def get_history():
    with open("history.json", "r") as f:
        return json.load(f)

@app.get("/history")
def full_history():
    return jsonify(get_history())

@app.get("/load/history")
def load_history():
    data = get_history()
    load_only = [{"timestamp": d["timestamp"], "load": d["load"]} for d in data]
    return jsonify(load_only)

@app.get("/greenness/history")
def greenness_history():
    data = get_history()
    green_only = [{"timestamp": d["timestamp"], "greenness": d["greenness"]} for d in data]
    return jsonify(green_only)

@app.get("/latest")
def latest():
    data = get_history()
    return jsonify(data[-1])

@app.get("/load/latest")
def latest_load():
    data = get_history()
    return jsonify({"timestamp": data[-1]["timestamp"], "load": data[-1]["load"]})

@app.get("/greenness/latest")
def latest_green():
    data = get_history()
    return jsonify({"timestamp": data[-1]["timestamp"], "greenness": data[-1]["greenness"]})

@app.get("/locations/<location>/metrics/load")
def get_load_forecast(location):
    """Get load predictions for next week following unified API schema."""
    try:
        result = generate_next_week_load_prediction(location)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/locations/<location>/metrics/greenness")
def get_carbon_forecast(location):
    """Get carbon/greenness predictions for next week following unified API schema."""
    try:
        result = generate_next_week_greenness_prediction(location)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)