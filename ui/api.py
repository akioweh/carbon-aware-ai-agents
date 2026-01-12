from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
import subprocess
import json

router = APIRouter()


# Models from OpenAPI
class JobRequest(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    job_type: str = Field(..., description="Type of AI workload")
    workload_amount: float = Field(..., description="Expected number of units to process")
    data_centre: str = Field(..., description="Selected data centre")
    latest_finish: datetime = Field(..., description="Latest acceptable finish time")


class ScheduleResponse(BaseModel):
    schedule_id: str
    job_id: str
    location: str
    start_time: datetime
    end_time: datetime
    carbon_intensity: float | None = None
    estimated_emissions_kg: float | None = None
    sci_per_unit: float | None = None


class Error(BaseModel):
    error: str


# POST Endpoint: /api/schedule

@router.post(
    "/schedule",
    response_model=ScheduleResponse,
    responses={400: {"model": Error}}
)
def schedule_job(req: JobRequest):

    # TEMPORARY MOCK RESPONSE FOR TESTING, REMOVE ONCE C++ IS ADDED
    return ScheduleResponse( 
        schedule_id="test-123", 
        job_id=req.job_id, 
        location="dc1", 
        start_time=datetime.now(timezone.utc), 
        end_time=datetime.now(timezone.utc),
        carbon_intensity=0.2, 
        estimated_emissions_kg=10.0, 
        sci_per_unit=1.5 
    )

    """
    Accept a job request, forward it to the C scheduler,
    and return the optimized schedule.
    """

    # Convert request to C input
    c_input = {
        "job_id": req.job_id,
        "job_type": req.job_type,
        "workload_amount": req.workload_amount,
        "data_centre": req.data_centre,
        "latest_finish": req.latest_finish.isoformat()
    }

    # Call the C program
    # NOTE: Replace "./scheduler" with your actual executable path
    try:
        result = subprocess.run(
            ["./scheduler"],
            input=json.dumps(c_input).encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"C scheduler failed: {e.stderr.decode()}"
        )

    # Parse C program output
    try:
        output = json.loads(result.stdout.decode())
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Invalid output from C scheduler"
        )

    # Build response model
    return ScheduleResponse(
        schedule_id=output.get("schedule_id", str(uuid.uuid4())),
        job_id=req.job_id,
        location=output.get("location", "unknown"),
        start_time=datetime.fromisoformat(output["start_time"]),
        end_time=datetime.fromisoformat(output["end_time"]),
        carbon_intensity=output.get("carbon_intensity"),
        estimated_emissions_kg=output.get("estimated_emissions_kg"),
        sci_per_unit=output.get("sci_per_unit")
    )
