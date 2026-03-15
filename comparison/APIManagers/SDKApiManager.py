from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, TypedDict

import requests


class RequestParamters(TypedDict):
    location: list[str]
    dataStartAt: str
    dataEndAt: str
    windowSize: int


class SDKApiManager:
    sdkBestWindowURL = "http://localhost:5073/emissions/forecasts/current"
    sdkLocationUrl = "http://localhost:5073/locations"

    def __init__(self, start_time: str, end_time: str):
        self.start_time: str = start_time
        self.end_time: str = end_time

    def parse_length_to_closest_int(self, length: float) -> int:
        return int(round(length, 0))

    def construct_request_params(self, length: int, location: str) -> Mapping[str, Any]:
        payload: RequestParamters = {
            "location": [location],
            "dataStartAt": self.start_time,
            "dataEndAt": self.end_time,
            "windowSize": length,
        }
        return payload

    def get_locations(self) -> list[str]:
        try:
            response = requests.get(self.sdkLocationUrl)
            response.raise_for_status()
            data = response.json()
            return list(data.keys())
        except requests.exceptions.RequestException as e:
            print(f"SDK Locations Request Failed with: {e}")
            return []

    def make_request(self, length: float, location: str) -> Any:
        window_size = self.parse_length_to_closest_int(length)

        params = self.construct_request_params(window_size, location)

        try:
            response = requests.get(self.sdkBestWindowURL, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"SDK best window Request Failed with: {e}")
            return None

    def parse_response_for_carbon_intensity(self, response: Any) -> float:
        try:
            location_result = response[0]
            points = location_result.get("optimalDataPoints", [])
            if points:
                return float(points[0].get("value", 0.0))
            return 9999
        except (IndexError, TypeError, AttributeError) as e:
            print(f"Parsing error: {e}")
            return 9999

    def query_all_locations(self, length: float) -> list[float]:
        locations = self.get_locations()
        carbon_intensities: list[float] = []
        for location in locations:
            response = self.make_request(length, location)
            carbon_intensities.append(
                self.parse_response_for_carbon_intensity(response)
            )
        return carbon_intensities

    def get_min_carbon_intensity_over_locaions(self, length: float) -> float:
        carbon_intensities = self.query_all_locations(length)
        return min(carbon_intensities)


if __name__ == "__main__":
    # 1. Create a datetime object for 2026-03-13 18:00 UTC
    start_dt = datetime(2026, 3, 13, 18, 0, tzinfo=timezone.utc)

    # 2. Create an end time by adding 18 hours to the start
    end_dt = start_dt + timedelta(hours=18)

    # 3. Convert objects to ISO strings
    # .isoformat() produces: "2026-03-13T18:00:00+00:00"
    # We use .replace("+00:00", "Z") if your SDK specifically requires the 'Z' suffix
    start_str: str = start_dt.isoformat().replace("+00:00", "Z")
    end_str: str = end_dt.isoformat().replace("+00:00", "Z")

    # 4. Initialize and Run
    sdk_manager = SDKApiManager(start_time=start_str, end_time=end_str)

    print("--- Querying SDK ---")
    print(f"ISO Start: {start_str}")
    print(f"ISO End:   {end_str}")

    try:
        min_intensity = sdk_manager.get_min_carbon_intensity_over_locaions(120.7)
        print(f"Result: {min_intensity}")
    except ValueError:
        print("No data found.")
