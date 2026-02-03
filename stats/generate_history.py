import math
import random
from datetime import datetime, timedelta
import db_utils

MAX_CAPACITY = 50
DATA_CENTRES = [
    'Data-Center-1',
    'Data-Center-2',
    'Data-Center-3',
    'Data-Center-4',
    'Data-Center-5',
]


class WeatherSystem:
    def __init__(self):
        self.wind_speed = random.uniform(0, 100)
        self.cloud_cover = random.uniform(0, 100)
        self.trend_duration = 0
        self.wind_trend = 0
        self.cloud_trend = 0

    def update(self):
        # Update weather patterns slowly
        if self.trend_duration <= 0:
            self.trend_duration = random.randint(
                12, 48
            )  # 1-4 hours (in 5-min intervals)
            self.wind_trend = random.uniform(-2, 2)
            self.cloud_trend = random.uniform(-5, 5)

        self.wind_speed = max(
            0, min(100, self.wind_speed + self.wind_trend + random.uniform(-1, 1))
        )
        self.cloud_cover = max(
            0, min(100, self.cloud_cover + self.cloud_trend + random.uniform(-2, 2))
        )
        self.trend_duration -= 1


def get_solar_intensity(timestamp, cloud_cover):
    hour = timestamp.hour + timestamp.minute / 60
    # Peak at noon (12), zero before 6 and after 18
    if 6 <= hour <= 18:
        # Simple bell-ish curve
        intensity = math.sin((hour - 6) / 12 * math.pi) * 100
        # Cloud cover reduces solar
        intensity *= 1 - (cloud_cover / 100) * 0.8
    else:
        intensity = 0
    return max(0, intensity)


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

    # Add randomness/noise
    noise = random.uniform(-2, 2)

    # Occasional spikes (server updates, batch jobs) - more likely at night
    if random.random() < 0.01:
        noise += random.uniform(10, 20)

    value = base_curve + noise

    # DC specific variance
    value += (dc_index % 3) * 2  # Slight offset per DC

    return max(0, min(MAX_CAPACITY, value))


def generate_greenness(timestamp, weather):
    solar = get_solar_intensity(timestamp, weather.cloud_cover)
    wind = weather.wind_speed * 0.7  # Wind contribution

    # Base grid mix (nuclear/hydro/coal/gas) - varies slowly
    grid_base = 30 + 10 * math.sin(timestamp.hour / 24 * 2 * math.pi)

    total_greenness = 0.4 * solar + 0.4 * wind + 0.2 * grid_base

    noise = random.uniform(-2, 2)
    return max(0, min(100, total_greenness + noise))


def generate_history():
    now = datetime.now()
    start = now - timedelta(days=30)
    current = start

    # Prepare bulk data for efficient insertion
    bulk_data = []

    # Shared weather system (or could be per region)
    weather = WeatherSystem()

    while current <= now:
        weather.update()

        for i, dc in enumerate(DATA_CENTRES):
            bulk_data.append({
                'location': dc,
                'timestamp': current,
                'load': generate_load(current, i),
                'greenness': generate_greenness(current, weather),
            })
        current += timedelta(minutes=5)

    # Insert all data into database
    db_utils.insert_historical_data_bulk(bulk_data)
    print(f'Generated and inserted {len(bulk_data)} historical data points into database.')


if __name__ == '__main__':
    generate_history()
