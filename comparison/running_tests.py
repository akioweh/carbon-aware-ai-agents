from concurrent.futures import ThreadPoolExecutor
from math import ceil

from OurAPIManager import OurApiManager
from SDKApiManager import SDKApiManager
from test_setups import TestConfig, get_test_configs


def get_lengths_of_computation() -> list[int]:
    """Workload amounts in KWh"""
    res: list[int] = []
    for i in range(1, 10):
        res.append(i * 15)
    for i in range(1, 10):
        res.append(3 * 60 * i)
    return res


def get_workload_amount(
    length_of_comoputation: float, power: float, overhead: float
) -> float:
    return (length_of_comoputation / 60.0) * power + overhead


def get_real_length_of_computation(
    effective_length_of_computation: float, overhead: float, power: float
):

    return int(ceil(effective_length_of_computation + (overhead / power) * 60))


def run_single_test(
    test_config: TestConfig,
):
    start_time = "2026-03-14T20:30:00Z"
    end_time = "2026-03-20T13:30:00Z"
    results: dict[int, tuple[float, float]] = {}
    for length_of_computation in get_lengths_of_computation():
        print(length_of_computation, test_config["system"]["n"])
        sdkApi = SDKApiManager(start_time, end_time)
        ourApi = OurApiManager(start_time, end_time)
        full_power: float = test_config["full_power"]
        workload_amount: float = get_workload_amount(
            length_of_computation, full_power, test_config["startup_overhead"]
        )

        sdkCarbonIntensity = sdkApi.get_min_carbon_intensity_over_locaions(
            get_real_length_of_computation(
                length_of_computation, test_config["startup_overhead"], full_power
            )
        )
        sdkCarbonEmissions: float = workload_amount * sdkCarbonIntensity

        ourCarbonEmissions = ourApi.get_minimal_carbon_emissions(
            test_config["system"]["type"],
            length_of_computation,
            test_config["system"]["n"],
            test_config["model"]["gb"],
        )

        results[length_of_computation] = (
            sdkCarbonEmissions,
            ourCarbonEmissions,
        )
    return results


def run_tests():
    test_configs = get_test_configs()
    results: list[dict[int, tuple[float, float]]]
    with ThreadPoolExecutor(max_workers=18) as executor:
        results = list(executor.map(run_single_test, test_configs))
    print(len(test_configs), len(results))
    return results


if __name__ == "__main__":
    print(run_tests())
