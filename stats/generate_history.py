import json
import math
import random
from datetime import datetime, timedelta

MAX_CAPACITY = 50

def generate_load(timestamp):
    hour = timestamp.hour + timestamp.minute / 60

    phase_shift = -3  # moves the peak to 3pm and dip to 3am
    x = (hour + phase_shift) / 24 * 2 * math.pi

    daily_cycle = (math.sin(x) + 1) / 2

    weekday = timestamp.weekday()
    if weekday >= 5:  # saturday or sunday less load
        weekend_factor = 0.7
    else:
        weekend_factor = 1.0

    base_load = daily_cycle * MAX_CAPACITY * weekend_factor

    noise = random.uniform(-0.1 * MAX_CAPACITY, 0.1 * MAX_CAPACITY)

    value = base_load + noise

    value = max(0, min(MAX_CAPACITY, value))

    return value

def generate_greenness(timestamp):
    hour = timestamp.hour

    # opposite of load, high in day (sun) and low in night
    base = (
        10 if hour < 6 else
        50 if hour < 10 else
        80 if hour < 16 else
        40 if hour < 20 else
        10
    )

    noise = random.uniform(-9, 9)
    value = max(0, min(100, base + noise))  # 0–100 scale
    return value

def generate_history():
    data = []
    now = datetime.now()
    start = now - timedelta(days=30)

    current = start

    while current <= now:
        data.append({
            "timestamp": current.isoformat(),
            "load": generate_load(current),
            "greenness": generate_greenness(current)
        })
        current += timedelta(minutes=5)

    with open("history.json", "w") as f:
        json.dump(data, f, indent=2)

    print("history.json generated.")

if __name__ == "__main__":
    generate_history()
