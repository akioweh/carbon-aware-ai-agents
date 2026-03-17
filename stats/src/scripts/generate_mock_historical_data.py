import math
import random
from datetime import datetime, timedelta

from ..core.settings import (
    DATACENTER_LOAD_SCALING_MULTIPLIER,
    MAXIMUM_DATACENTER_CAPACITY_IN_UNITS,
    SUPPORTED_DATACENTER_NAMES,
)
from ..database import repository


def calculate_simulated_datacenter_load(metric_timestamp, datacenter_list_index):
    time_in_hours = metric_timestamp.hour + metric_timestamp.minute / 60
    day_of_week = metric_timestamp.weekday()

    # Workday pattern vs Weekend pattern
    is_weekend_day = day_of_week >= 5

    if is_weekend_day:
        # Weekend: lazier, lower peak, starts later
        base_load_curve = (
            20
            + 15 * math.exp(-((time_in_hours - 14) ** 2) / 20)  # Broad afternoon peak
            + 5 * math.cos(time_in_hours / 3)  # Some wobbles
        )
    else:
        # Weekday: Morning spike, lunch dip, afternoon work, evening streaming
        base_load_curve = (
            5  # Baseline
            + 35 * math.exp(-((time_in_hours - 10) ** 2) / 4)  # Morning peak (10am)
            + 30 * math.exp(-((time_in_hours - 15) ** 2) / 6)  # Afternoon plateau
            + 10 * math.exp(-((time_in_hours - 21) ** 2) / 4)  # Evening activity
        )
        # Deep night dip
        if 0 <= time_in_hours < 5:
            base_load_curve *= 0.5

    # Add randomness/noise (kept mild so the curve shape stays clean)
    random_noise_factor = random.uniform(-3, 3)

    # Small random baseline shift per day so consecutive days don't look identical
    daily_random_seed = metric_timestamp.toordinal() + datacenter_list_index
    daily_random_generator = random.Random(daily_random_seed)
    random_noise_factor += daily_random_generator.uniform(-2, 2)

    # Occasional spikes (server updates, batch jobs) — 1% chance, mild magnitude
    if random.random() < 0.01:
        random_noise_factor += random.uniform(2, 5)

    base_value_with_noise = max(
        0,
        min(
            MAXIMUM_DATACENTER_CAPACITY_IN_UNITS, base_load_curve + random_noise_factor
        ),
    )

    # Datacenter specific variance
    base_value_with_noise += (datacenter_list_index % 3) * 2  # Slight offset per DC

    final_load_value = max(
        0, min(MAXIMUM_DATACENTER_CAPACITY_IN_UNITS, base_value_with_noise)
    )
    return final_load_value * DATACENTER_LOAD_SCALING_MULTIPLIER


def calculate_simulated_carbon_intensity(metric_timestamp):
    # 2. Varying Carbon Intensity (Sine wave + noise to make "Greenness" move)
    # Base of 200, swings +/- 150 based on time of day, + random noise
    day_progress = (metric_timestamp.hour + metric_timestamp.minute / 60) / 24
    variation = 150 * math.sin(2 * math.pi * day_progress)
    noise = random.uniform(-20, 20)
    sim_carbon = max(50, min(500, 250 + variation + noise))
    return sim_carbon


def generate_and_store_mock_historical_data(days=30):
    current_time = datetime.now()
    start_time = current_time - timedelta(days=days)
    iterating_time = start_time

    load_payload = []
    carbon_payload = []

    while iterating_time <= current_time:
        for index, datacenter_name in enumerate(SUPPORTED_DATACENTER_NAMES):
            simulated_utilization = calculate_simulated_datacenter_load(
                iterating_time, index
            )
            load_payload.append(
                {
                    'location': datacenter_name,
                    'timestamp': iterating_time,
                    'load': simulated_utilization,
                }
            )

            simulated_carbon = calculate_simulated_carbon_intensity(iterating_time)
            carbon_payload.append(
                {
                    'location': datacenter_name,
                    'timestamp': iterating_time,
                    'carbon_intensity': simulated_carbon,
                }
            )

        iterating_time += timedelta(minutes=15)

    repository.insert_or_update_historical_load_metrics(load_payload)
    repository.insert_or_update_historical_carbon_metrics(carbon_payload)
