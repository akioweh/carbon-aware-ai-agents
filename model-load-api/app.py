from flask import Flask, jsonify
import json

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
    result = {
        dc: [{"timestamp": d["timestamp"], "load": d["load"]} for d in entries]
        for dc, entries in data.items()
    }
    return jsonify(result)

@app.get("/greenness/history")
def greenness_history():
    data = get_history()
    result = {
        dc: [{"timestamp": d["timestamp"], "greenness": d["greenness"]} for d in entries]
        for dc, entries in data.items()
    }
    return jsonify(result)

@app.get("/latest")
def latest():
    data = get_history()
    result = {dc: entries[-1] for dc, entries in data.items()}
    return jsonify(result)

@app.get("/load/latest")
def latest_load():
    data = get_history()
    result = {dc: {"timestamp": entries[-1]["timestamp"], "load": entries[-1]["load"]}
              for dc, entries in data.items()}
    return jsonify(result)

@app.get("/greenness/latest")
def latest_green():
    data = get_history()
    result = {dc: {"timestamp": entries[-1]["timestamp"], "greenness": entries[-1]["greenness"]}
              for dc, entries in data.items()}
    return jsonify(result)

@app.get("/history/<dc>")
def history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify(data[dc])

@app.get("/load/history/<dc>")
def load_history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify([{"timestamp": d["timestamp"], "load": d["load"]} for d in data[dc]])

@app.get("/greenness/history/<dc>")
def greenness_history_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify([{"timestamp": d["timestamp"], "greenness": d["greenness"]} for d in data[dc]])

@app.get("/latest/<dc>")
def latest_for_dc(dc):
    data = get_history()
    if dc not in data:
        return jsonify({"error": f"Data centre '{dc}' not found"}), 404
    return jsonify(data[dc][-1])

if __name__ == "__main__":
    app.run(debug=True)