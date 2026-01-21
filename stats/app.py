from flask import Flask, jsonify
import json
import sqlite3
import time
from predictor import generate_next_week_load_prediction, generate_next_week_greenness_prediction

app = Flask(__name__)

DB_FILE = "cache.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                key TEXT PRIMARY KEY,
                data TEXT,
                timestamp REAL
            )
        """)

def get_cached_prediction(key):
    """Get cached prediction if it exists and is less than 5 minutes old."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.execute(
                "SELECT data, timestamp FROM predictions WHERE key = ?", 
                (key,)
            )
            row = cursor.fetchone()
            
            if row:
                data_json, timestamp = row
                # Check if cache is fresh (less than 5 minutes old)
                if time.time() - timestamp < 300:  # 300 seconds = 5 minutes
                    return json.loads(data_json)
    except sqlite3.Error as e:
        print(f"Cache read error: {e}")
    return None

def save_prediction(key, data):
    """Save prediction to cache with current timestamp."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO predictions (key, data, timestamp) VALUES (?, ?, ?)",
                (key, json.dumps(data), time.time())
            )
    except sqlite3.Error as e:
        print(f"Cache write error: {e}")

# Initialize database on module load
init_db()

def get_history():
    with open("history.json", "r") as f:
        return json.load(f)

def full_history():
    return jsonify(get_history())

def load_history():
    data = get_history()
    result = {
        dc: [{"timestamp": d["timestamp"], "load": d["load"]} for d in entries]
        for dc, entries in data.items()
    }
    return jsonify(result)

def greenness_history():
    data = get_history()
    result = {
        dc: [{"timestamp": d["timestamp"], "greenness": d["greenness"]} for d in entries]
        for dc, entries in data.items()
    }
    return jsonify(result)

def latest():
    data = get_history()
    result = {dc: entries[-1] for dc, entries in data.items()}
    return jsonify(result)

def latest_load():
    data = get_history()
    result = {dc: {"timestamp": entries[-1]["timestamp"], "load": entries[-1]["load"]}
              for dc, entries in data.items()}
    return jsonify(result)

def latest_green():
    data = get_history()
    result = {dc: {"timestamp": entries[-1]["timestamp"], "greenness": entries[-1]["greenness"]}
              for dc, entries in data.items()}
    return jsonify(result)

def history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify(data[dc])

def load_history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify([{"timestamp": d["timestamp"], "load": d["load"]} for d in data[dc]])

def greenness_history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify([{"timestamp": d["timestamp"], "greenness": d["greenness"]} for d in data[dc]])

def latest_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify(data[dc][-1])

@app.get("/locations/<location>/metrics/forecast_load")
def get_load_forecast(location):
    """Get load predictions for next week following unified API schema."""
    try:
        cache_key = f"load_forecast_{location}"
        cached_result = get_cached_prediction(cache_key)
        
        if cached_result:
            return jsonify(cached_result)

        result = generate_next_week_load_prediction(location)
        save_prediction(cache_key, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/locations/<location>/metrics/forecast_greenness")
def get_carbon_forecast(location):
    """Get carbon/greenness predictions for next week following unified API schema."""
    try:
        cache_key = f"greenness_forecast_{location}"
        cached_result = get_cached_prediction(cache_key)
        
        if cached_result:
            return jsonify(cached_result)

        result = generate_next_week_greenness_prediction(location)
        save_prediction(cache_key, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)