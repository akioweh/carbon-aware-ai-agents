from flask import Flask, jsonify
import json
import sqlite3
import time
import threading
from predictor import generate_next_week_load_prediction, generate_next_week_greenness_prediction

app = Flask(__name__)

DB_FILE = "cache.db"
from generate_history import DATA_CENTRES

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

def prediction_loop():
    while True:
        for dc in DATA_CENTRES:
            try:
                load_data = generate_next_week_load_prediction(dc)
                save_prediction(f"load_forecast_{dc}", load_data)

                greenness_data = generate_next_week_greenness_prediction(dc)
                save_prediction(f"greenness_forecast_{dc}", greenness_data)
            except Exception as e:
                print(f"Error at {dc}, {e}")
        time.sleep(300)
threading.Thread(target=prediction_loop, daemon=True).start()


@app.get("/locations/<location>/metrics/forecast_load")
def get_load_forecast(location):
    """Get load predictions for next week following unified API schema."""
    try:
        cache_key = f"load_forecast_{location}"
        cached_result = get_cached_prediction(cache_key)
        return jsonify(cached_result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/locations/<location>/metrics/forecast_greenness")
def get_carbon_forecast(location):
    """Get carbon/greenness predictions for next week following unified API schema."""
    try:
        cache_key = f"greenness_forecast_{location}"
        cached_result = get_cached_prediction(cache_key)
        return jsonify(cached_result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/datacenter")
def get_datacenters():
    try:
        return jsonify(DATA_CENTRES)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)