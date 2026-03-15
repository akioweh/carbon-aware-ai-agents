# --- START OF FILE running_tests.py ---
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import product
from math import ceil
from typing import TypedDict

from APIManagers.OurAPIManager import OurApiManager
from APIManagers.SDKApiManager import SDKApiManager
from testing.test_setups import TestConfig, get_test_configs


# --- STRICT TYPE DEFINITIONS ---
class BaseTestParams(TypedDict):
    config: TestConfig
    window_hours: int


class TestParams(TypedDict):
    config: TestConfig
    window_hours: int
    length_of_computation: float
    volatility_override: float


class TestResult(TypedDict):
    config_id: str
    window_hours: int
    length_of_computation: float
    sdk_emissions_kg: float
    agent_emissions_kg: float
    runtime_sec: float
    volatility_index: float
    p_full_kw: float
    overhead_kwh: float


# --- CORE LOGIC ---
def get_lengths_of_computation() -> list[float]:
    res: list[float] = []
    for i in range(1, 5):
        res.append(float(i * 30))
    for i in range(1, 10):
        res.append(float(3 * 60 * i))
    return res


def get_workload_amount(length_of_computation: float, power: float) -> float:
    return (length_of_computation / 60.0) * power


def get_real_length_of_computation(
    effective_length_of_computation: float, overhead: float, power: float
) -> int:
    return int(ceil(effective_length_of_computation + (overhead / power) * 60.0))


def run_specific_test(params: TestParams) -> TestResult:
    """Self-contained test runner targeting local APIs for on-demand graph generation."""
    c: TestConfig = params["config"]
    length: float = params["length_of_computation"]
    window: int = min(
        params["window_hours"], 144
    )  # Strictly enforce maximum 6 days (144 hours)
    vol_override: float = params["volatility_override"]

    # Only manipulate hours, entirely dropping days/offsets
    start_dt: datetime = datetime(2026, 3, 15, 20, 0, tzinfo=timezone.utc)
    end_dt: datetime = start_dt + timedelta(hours=window)
    start_str: str = start_dt.isoformat().replace("+00:00", "Z")
    end_str: str = end_dt.isoformat().replace("+00:00", "Z")

    p_full: float = c["full_power"]
    overhead: float = c["startup_overhead"]

    real_length: int = get_real_length_of_computation(length, overhead, p_full)
    workload_kwh: float = get_workload_amount(length, p_full)

    # 1. Fetch Baseline GSF SDK
    sdk_api: SDKApiManager = SDKApiManager(start_time=start_str, end_time=end_str)
    sdk_intensity: float = sdk_api.get_min_carbon_intensity_over_locaions(
        float(real_length)
    )
    sdk_emissions: float = (
        (sdk_intensity * workload_kwh) if sdk_intensity != 9999.0 else 9999.0
    )

    # 2. Fetch Dynamic Preemption Agent
    our_api: OurApiManager = OurApiManager(earliest=start_str, latest=end_str)

    t0: float = time.perf_counter()
    agent_emissions: float = our_api.get_minimal_carbon_emissions(
        gpu_type=c["system"]["type"],
        length=int(length),
        gpu_count=c["system"]["n"],
        model_size=c["model"]["gb"],
    )
    runtime_sec: float = time.perf_counter() - t0

    return {
        "config_id": c["config_id"],
        "window_hours": window,
        "length_of_computation": length,
        "sdk_emissions_kg": sdk_emissions,
        "agent_emissions_kg": agent_emissions,
        "runtime_sec": runtime_sec,
        "volatility_index": vol_override,
        "p_full_kw": p_full,
        "overhead_kwh": overhead,
    }


def run_single_parameter_set(base_params: BaseTestParams) -> list[TestResult]:
    """Helper mapper to expand base configurations into lengths based on your skeleton."""
    results: list[TestResult] = []
    lengths: list[float] = get_lengths_of_computation()
    for l in lengths:
        print(base_params["config"], l)
        params: TestParams = {
            "config": base_params["config"],
            "window_hours": base_params["window_hours"],
            "length_of_computation": l,
            "volatility_override": 15.0,  # Base standard deviation fallback
        }
        results.append(run_specific_test(params))

    return results


def run_tests(use_cache: bool = True) -> list[TestResult]:
    cache_file = "testing/test_results_cache.json"

    # 1. Check if cache exists and is requested
    if use_cache and os.path.exists(cache_file):
        print(f"Loading results from cache: {cache_file}")
        with open(cache_file, "r") as f:
            return json.load(f)

    print("Cache not found or disabled. Running live tests...")
    test_configs: list[TestConfig] = get_test_configs()
    window_sizes: list[int] = [48]

    base_params: list[BaseTestParams] = [
        {"config": c, "window_hours": w} for c, w in product(test_configs, window_sizes)
    ]

    all_results: list[TestResult] = []
    with ThreadPoolExecutor(max_workers=18) as executor:
        for res_list in executor.map(run_single_parameter_set, base_params):
            all_results.extend(res_list)

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(all_results, f, indent=4)

    return all_results


if __name__ == "__main__":
    res: list[TestResult] = run_tests()
    print(f"Generated {len(res)} discrete result records.")
# --- END OF FILE running_tests.py ---
