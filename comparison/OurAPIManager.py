from typing import Any, Optional, TypedDict

import requests


# --- TYPE DEFINITIONS ---
# Using inheritance with `total=False` allows us to strictly require the mandatory
# fields while making `preferred_datacenter` safely optional without validation errors.
class RequiredJobRequest(TypedDict):
    job_type: str
    earliest_start: str
    latest_finish: str
    additional_constraints: dict[str, Any]
    gpu_type: str
    length: int
    gpu_count: int
    model_size: int


class JobRequest(RequiredJobRequest, total=False):
    preferred_datacenter: str


# --- API MANAGER ---
class OurApiManager:
    baseURL: str = "http://localhost:6969/api/schedules"

    def __init__(self, earliest: str, latest: str) -> None:
        self.earliest: str = earliest
        self.latest: str = latest

    def _construct_payload(
        self,
        gpu_type: str,
        length: int,
        gpu_count: int,
        model_size: int,
        location: str = "",
    ) -> JobRequest:

        payload: JobRequest = {
            "job_type": "training",
            "earliest_start": self.earliest,
            "latest_finish": self.latest,
            "additional_constraints": {},
            "gpu_type": gpu_type,
            "length": length,
            "gpu_count": gpu_count,
            "model_size": model_size,
        }

        # Handle the with/without location approach
        if location:
            payload["preferred_datacenter"] = location

        return payload

    def get_minimal_carbon_emissions(
        self,
        gpu_type: str,
        length: int,
        gpu_count: int,
        model_size: int,
        location: str = "",
    ) -> float:
        """
        Orchestrates the full flow: Create -> Fetch Emissions -> Delete -> Return float.
        """
        # 1. Create the schedule
        payload: JobRequest = self._construct_payload(
            gpu_type=gpu_type,
            length=length,
            gpu_count=gpu_count,
            model_size=model_size,
            location=location,
        )
        schedule_id: Optional[str] = self._create_schedule(payload)

        if not schedule_id:
            return 9999.0

        # 2. Fetch the emissions data
        emissions: float = self._get_emissions(schedule_id)

        # 3. Cleanup: Delete the schedule
        self._delete_schedule(schedule_id)

        return emissions

    def _create_schedule(self, payload: JobRequest) -> Optional[str]:
        try:
            response: requests.Response = requests.post(self.baseURL, json=payload)
            response.raise_for_status()

            data: dict[str, Any] = response.json()
            return str(data["schedule_id"])
        except (requests.exceptions.RequestException, KeyError) as e:
            print(f"Create Failed: {e}")
            return None

    def _get_emissions(self, schedule_id: str) -> float:
        try:
            url: str = f"{self.baseURL}/{schedule_id}"
            response: requests.Response = requests.get(url)
            response.raise_for_status()

            data: dict[str, Any] = response.json()
            impact: dict[str, Any] = data.get("impact", {})
            return float(impact.get("total_emissions", 9999.0))
        except (
            requests.exceptions.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as e:
            print(f"Fetch Emissions Failed: {e}")
            return 9999.0

    def _delete_schedule(self, schedule_id: str) -> bool:
        try:
            url: str = f"{self.baseURL}/{schedule_id}"
            response: requests.Response = requests.delete(url)
            return response.status_code == 204
        except requests.exceptions.RequestException as e:
            print(f"Delete Failed: {e}")
            return False


# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    api: OurApiManager = OurApiManager(
        earliest="2026-03-13T18:00:00Z", latest="2026-03-14T17:00:00Z"
    )

    val: float = api.get_minimal_carbon_emissions(
        gpu_type="V100_PCIE", length=20, gpu_count=5, model_size=26
    )

    print(f"Final Float Emission: {val}")
