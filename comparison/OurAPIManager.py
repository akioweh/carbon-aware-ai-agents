from typing import Any, Optional, TypedDict

import requests


# --- TYPE DEFINITIONS ---
class JobRequest(TypedDict):
    job_type: str
    workload_amount: int
    earliest_start: str
    latest_finish: str
    additional_constraints: dict[str, Any]
    preferred_datacenter: str


# --- API MANAGER ---
class OurApiManager:
    # Updated to the server port in your OpenAPI schema
    baseURL: str = "http://localhost:6969/api/schedules"

    def __init__(self, earliest: str, latest: str):
        self.earliest: str = earliest
        self.latest: str = latest

    def _construct_payload(self, amount: float, location: str = "") -> JobRequest:
        return {
            "job_type": "training",
            "workload_amount": int(round(amount)),
            "earliest_start": self.earliest,
            "latest_finish": self.latest,
            "additional_constraints": {},
            "preferred_datacenter": location,
        }

    def get_minimal_carbon_emissions(self, amount: float, location: str = "") -> float:
        """
        Orchestrates the full flow: Create -> Fetch Emissions -> Delete -> Return float.
        """
        # 1. Create the schedule
        payload = self._construct_payload(amount, location)
        schedule_id = self._create_schedule(payload)

        if not schedule_id:
            return 9999.0

        # 2. Fetch the emissions data
        emissions = self._get_emissions(schedule_id)

        # 3. Cleanup: Delete the schedule as requested
        self._delete_schedule(schedule_id)

        return emissions

    def _create_schedule(self, payload: JobRequest) -> Optional[str]:
        try:
            response = requests.post(self.baseURL, json=payload)
            response.raise_for_status()
            # Schema says ScheduleCreatedResponse has 'schedule_id'
            return str(response.json().get("schedule_id"))
        except (requests.exceptions.RequestException, KeyError) as e:
            print(f"Create Failed: {e}")
            return None

    def _get_emissions(self, schedule_id: str) -> float:
        try:
            # GET /api/schedules/{schedule_id}
            url = f"{self.baseURL}/{schedule_id}"
            response = requests.get(url)
            response.raise_for_status()

            # Accessing path: response -> impact -> total_emissions
            data = response.json()
            impact = data.get("impact", {})
            return float(impact.get("total_emissions", 9999.0))
        except (requests.exceptions.RequestException, KeyError, TypeError) as e:
            print(f"Fetch Emissions Failed: {e}")
            return 9999.0

    def _delete_schedule(self, schedule_id: str) -> bool:
        try:
            # DELETE /api/schedules/{schedule_id}
            url = f"{self.baseURL}/{schedule_id}"
            response = requests.delete(url)
            return response.status_code == 204
        except requests.exceptions.RequestException as e:
            print(f"Delete Failed: {e}")
            return False


# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    api = OurApiManager("2026-03-13T18:00:00Z", "2026-03-14T17:00:00Z")
    val = api.get_minimal_carbon_emissions(20000.5)
    print(f"Final Float Emission: {val}")
