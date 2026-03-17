import math
import random
from datetime import datetime, timedelta

import db_utils
from config import DATA_CENTRES, LOAD_SCALE_FACTOR, MAX_CAPACITY_UNITS


def generate_load(timestamp, dc_index):
    hour = timestamp.hour + timestamp.minute / 60
    weekday = timestamp.weekday()

    # Workday pattern
    is_weekend = weekday >= 5

    if is_weekend:
        # Weekend: lazier, lower peak, starts later
        base_curve = (
            20
            + 15 * math.exp(-((hour - 14) ** 2) / 20)  # Broad afternoon peak
            + 5 * math.cos(hour / 3)  # Some wobbles
        )
    else:
        # Weekday: Morning spike, lunch dip, afternoon work, evening streaming
        base_curve = (
            5  # Baseline
            + 35 * math.exp(-((hour - 10) ** 2) / 4)  # Morning peak (10am)
            + 30 * math.exp(-((hour - 15) ** 2) / 6)  # Afternoon plateau
            + 10 * math.exp(-((hour - 21) ** 2) / 4)  # Evening activity
        )
        # Deep night dip
        if 0 <= hour < 5:
            base_curve *= 0.5

    # Add randomness/noise (kept mild so the curve shape stays clean)
    noise = random.uniform(-3, 3)

    # Small random baseline shift per day so consecutive days don't look identical
    day_seed = timestamp.toordinal() + dc_index
    rng_day = random.Random(day_seed)
    noise += rng_day.uniform(-2, 2)

    # Occasional spikes (server updates, batch jobs) — 1% chance, mild magnitude
    if random.random() < 0.01:
        noise += random.uniform(2, 5)

    base_value = max(0, min(MAX_CAPACITY_UNITS, base_curve + noise))

    # DC specific variance
    base_value += (dc_index % 3) * 2  # Slight offset per DC

    return max(0, min(MAX_CAPACITY_UNITS, base_value)) * LOAD_SCALE_FACTOR


def generate_history():
    now = datetime.now()
    start = now - timedelta(days=30)
    current = start

    bulk_data = []

    while current <= now:
        for i, dc in enumerate(DATA_CENTRES):
            bulk_data.append(
                {
                    'location': dc,
                    'timestamp': current,
                    'load': generate_load(current, i),
                    'carbon_intensity': 250.0,
                }
            )
        current += timedelta(minutes=5)

    # Insert all data into database
    db_utils.insert_historical_data_bulk(bulk_data)
    print(
        f'Generated and inserted {len(bulk_data)} historical data points into database.'
    )


if __name__ == '__main__':
    # ensure database is initialized
    db_utils.initialize_db()
    generate_history()
