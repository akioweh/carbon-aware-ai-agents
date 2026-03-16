import math
import random
from datetime import datetime, timedelta

import db_utils

# Per-datacenter GPU configurations (30–200 GPUs as per scheduler hardware spec)
# Each tuple: (datacenter_name, gpu_count, gpu_type)
DC_GPU_CONFIGS = [
    ('Data-Center-1', 100, 'A100_SXM4'),
    ('Data-Center-2', 50, 'V100_PCIE'),
    ('Data-Center-3', 150, 'A100_SXM4'),
    ('Data-Center-4', 75, 'V100_PCIE'),
    ('Data-Center-5', 200, 'A100_SXM4'),
]

DATA_CENTRES = [cfg[0] for cfg in DC_GPU_CONFIGS]

# FLOs (Floating-Point Operations) per GPU per 5-minute block.
# These reflect effective throughput for real AI inference/training workloads,
# yielding per-datacenter capacities in the range ~1e14 to ~6e15 FLOs/block
# (i.e. "roughly 1e12 to 1e16" as required).
GPU_FLOS_PER_5MIN = {
    'V100_PCIE': 1e13,  # ~14 TFLOPS peak; effective throughput ~1e13 FLOs/5 min
    'A100_SXM4': 3e13,  # ~78 TFLOPS peak; effective throughput ~3e13 FLOs/5 min
}


def dc_base_capacity(dc_index: int) -> float:
    """Return the base FLO capacity per 5-min block for the given datacenter."""
    _, gpu_count, gpu_type = DC_GPU_CONFIGS[dc_index]
    return gpu_count * GPU_FLOS_PER_5MIN[gpu_type]


def generate_capacity(timestamp: datetime, dc_index: int) -> float:
    """Generate FLO capacity for a 5-min block.

    Capacity is primarily determined by the datacenter's GPU fleet.  Small
    per-day variations model thermal throttling and maintenance windows.
    """
    base = dc_base_capacity(dc_index)

    # Small daily variance (±3%)
    day_seed = timestamp.toordinal() + dc_index * 7
    rng = random.Random(day_seed)
    daily_factor = rng.uniform(0.97, 1.00)

    # Rare capacity reduction (2% chance: one or more GPUs offline)
    if rng.random() < 0.02:
        offline_frac = rng.uniform(0.05, 0.15)
        daily_factor *= 1.0 - offline_frac

    return base * daily_factor


def generate_load(timestamp: datetime, dc_index: int) -> float:
    """Generate utilisation load in FLOs for a 5-min block.

    Returns values in the range roughly 1e12 to 1e16 depending on datacenter
    size (GPU count) and realistic time-of-day usage patterns.
    """
    capacity = dc_base_capacity(dc_index)

    hour = timestamp.hour + timestamp.minute / 60
    weekday = timestamp.weekday()

    # Workday pattern
    is_weekend = weekday >= 5

    if is_weekend:
        # Weekend: lower peak, broad afternoon
        base_utilization = (
            0.30
            + 0.20 * math.exp(-((hour - 14) ** 2) / 20)  # Broad afternoon peak
            + 0.05 * math.cos(hour / 3)  # Some wobbles
        )
    else:
        # Weekday: morning spike, lunch dip, afternoon plateau, evening activity
        base_utilization = (
            0.10  # Baseline
            + 0.50 * math.exp(-((hour - 10) ** 2) / 4)  # Morning peak (10am)
            + 0.40 * math.exp(-((hour - 15) ** 2) / 6)  # Afternoon plateau
            + 0.15 * math.exp(-((hour - 21) ** 2) / 4)  # Evening activity
        )
        # Deep night dip
        if 0 <= hour < 5:
            base_utilization *= 0.5

    # Add randomness/noise (kept mild so the curve shape stays clean)
    noise = random.uniform(-0.05, 0.05)

    # Small random baseline shift per day so consecutive days don't look identical
    day_seed = timestamp.toordinal() + dc_index
    rng_day = random.Random(day_seed)
    noise += rng_day.uniform(-0.03, 0.03)

    # Occasional spikes (server updates, batch jobs) — 1% chance, mild magnitude
    if random.random() < 0.01:
        noise += random.uniform(0.05, 0.10)

    # DC-specific baseline offset
    noise += (dc_index % 3) * 0.02

    utilization = base_utilization + noise

    # Clamp to a realistic utilisation range [5%, 95%]
    utilization = max(0.05, min(0.95, utilization))

    return capacity * utilization


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
                    'capacity': generate_capacity(current, i),
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
