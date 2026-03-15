import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import product
from math import ceil
from typing import TypedDict

from OurAPIManager import OurApiManager
from SDKApiManager import SDKApiManager
from test_setups import TestConfig, get_test_configs


# --- FLAT RESULT STRUCTURE ---
class TestResult(TypedDict):
    config_id: str
    model_name: str
    model_gb: int
    system_id: str
    gpu_type: str
    gpu_count: int
    system_type: str
    workload_length_mins: int
    window_size_hours: int
    sdk_emissions: float
    our_emissions: float
    sdk_compute_time_sec: float
    our_compute_time_sec: float


class TestParams(TypedDict):
    config: TestConfig
    window_hours: int


def get_lengths_of_computation() -> list[int]:
    res: list[int] = []
    for i in range(1, 5):
        res.append(i * 30)
    for i in range(1, 10):
        res.append(3 * 60 * i)
    return res


def get_workload_amount(
    length_of_computation: float, power: float, overhead: float
) -> float:
    return (length_of_computation / 60.0) * power + overhead


def get_real_length_of_computation(
    effective_length_of_computation: float, overhead: float, power: float
) -> int:
    return int(ceil(effective_length_of_computation + (overhead / power) * 60.0))


def run_single_parameter_set(params: TestParams) -> list[TestResult]:
    config: TestConfig = params["config"]
    window_hours: int = params["window_hours"]

    start_dt: datetime = datetime(2026, 3, 15, 7, 00, tzinfo=timezone.utc)
    end_dt: datetime = start_dt + timedelta(hours=window_hours)
    start_time: str = start_dt.isoformat().replace("+00:00", "Z")
    end_time: str = end_dt.isoformat().replace("+00:00", "Z")

    results: list[TestResult] = []
    sdkApi: SDKApiManager = SDKApiManager(start_time, end_time)
    ourApi: OurApiManager = OurApiManager(start_time, end_time)

    global my_sanity_test_counter
    my_sanity_test_counter = 0

    for length_of_computation in get_lengths_of_computation():
        print(my_sanity_test_counter)
        my_sanity_test_counter += 1
        full_power: float = config["full_power"]
        overhead: float = config["startup_overhead"]
        workload_amount: float = get_workload_amount(
            float(length_of_computation), full_power, overhead
        )
        real_length: int = get_real_length_of_computation(
            float(length_of_computation), overhead, full_power
        )

        # --- SDK Baseline execution ---
        t0: float = time.perf_counter()
        sdkCarbonIntensity: float = sdkApi.get_min_carbon_intensity_over_locaions(
            float(real_length)
        )
        sdkCarbonEmissions: float = workload_amount * sdkCarbonIntensity
        sdk_time: float = time.perf_counter() - t0

        # --- Our Software execution ---
        t1: float = time.perf_counter()
        ourCarbonEmissions: float = ourApi.get_minimal_carbon_emissions(
            gpu_type=config["system"]["type"],
            length=length_of_computation,
            gpu_count=config["system"]["n"],
            model_size=config["model"]["gb"],
        )
        our_time: float = time.perf_counter() - t1

        results.append(
            {
                "config_id": config["config_id"],
                "model_name": config["model"]["name"],
                "model_gb": config["model"]["gb"],
                "system_id": config["system"]["id"],
                "gpu_type": config["system"]["type"],
                "gpu_count": config["system"]["n"],
                "system_type": config["system"]["type"],
                "workload_length_mins": length_of_computation,
                "window_size_hours": window_hours,
                "sdk_emissions": sdkCarbonEmissions,
                "our_emissions": ourCarbonEmissions,
                "sdk_compute_time_sec": sdk_time,
                "our_compute_time_sec": our_time,
            }
        )
    return results


def run_tests() -> list[TestResult]:
    test_configs: list[TestConfig] = get_test_configs()
    window_sizes: list[int] = [6, 12, 24, 36, 48, 72, 144]
    test_params: list[TestParams] = [
        {"config": c, "window_hours": w} for c, w in product(test_configs, window_sizes)
    ]

    all_results: list[TestResult] = []
    with ThreadPoolExecutor(max_workers=18) as executor:
        for res_list in executor.map(run_single_parameter_set, test_params):
            all_results.extend(res_list)
    return all_results


if __name__ == "__main__":
    res: list[TestResult] = run_tests()
    print(f"Generated {len(res)} discrete result records.")
