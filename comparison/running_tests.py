from concurrent.futures import ThreadPoolExecutor

from OurAPIManager import OurApiManager
from SDKApiManager import SDKApiManager
from test_setups import TestConfig, get_test_configs


def get_workload_amounts() -> list[float]:
    """Workload amounts in KWh"""
    return [0.5, 1.0, 1.5, 2, 4, 8, 16]


def power_coeficients() -> list[float]:
    """Full power (1), or half power (0.5)"""
    return [1, 0.5]


def calc_length_of_computation(workload: float, power_mode: float) -> float:
    return workload / power_mode


def run_single_test(
    test_config: TestConfig,
):
    start_time = "2026-03-13T18:00:00Z"
    end_time = "2026-03-14T17:00:00Z"
    results: dict[tuple[float, float], tuple[float, float]] = {}
    for workload in get_workload_amounts():
        for power_mode in power_coeficients():
            print("running", workload, power_mode)
            sdkApi = SDKApiManager(start_time, end_time)
            ourApi = OurApiManager(start_time, end_time)
            length_of_computation = calc_length_of_computation(workload, power_mode)
            sdkCarbonEmissions = (
                workload
                * sdkApi.get_min_carbon_intensity_over_locaions(length_of_computation)
            )
            ourCarbonEmissions = ourApi.get_minimal_carbon_emissions(workload)
            results[(workload, length_of_computation)] = (
                sdkCarbonEmissions,
                ourCarbonEmissions,
            )
    return results


def run_tests():
    test_configs = get_test_configs()
    with ThreadPoolExecutor(max_workers=18) as executor:
        results = list(executor.map(run_single_test, test_configs))

    return results


if __name__ == "__main__":
    print(run_tests())
