# API Schemas Documentation (Prototype)

This document provides an overview of the simplified OpenAPI schemas for prototyping the Carbon-Aware AI Agents system.

## Overview

The system comprises three main components that communicate via RESTful HTTP APIs:

1. **UI (webapp)** - User interface for job submission and visualization
2. **Scheduler** - Core optimization logic for workload placement
3. **Stats (model-load-api)** - Environmental and operational data provider

Two OpenAPI 3.0 schemas define these interactions:

- **`webapp/openapi.yaml`** - UI ↔ Scheduler API (simplified for prototyping)
- **`model-load-api/openapi.yaml`** - Stats API (including Scheduler ↔ Stats endpoint)

## Design Philosophy

These schemas are intentionally **simplified for prototyping**:
- Minimal required fields
- Flat structure (minimal nesting)
- Focus on core functionality only
- Easy to implement and iterate

## API Interactions

### 1. UI → Scheduler: Job Submission

**Endpoint:** `POST /api/schedule`

**Purpose:** Submit an AI workload for carbon-aware scheduling

**Request Schema:** `JobRequest`
```json
{
  "job_id": "train-model-1",
  "gpu_count": 4,
  "duration_hours": 8,
  "earliest_start": "2025-12-08T00:00:00Z",
  "latest_finish": "2025-12-10T00:00:00Z"
}
```

**Response Schema:** `ScheduleResponse`
```json
{
  "schedule_id": "sched-123",
  "job_id": "train-model-1",
  "location": "dc1",
  "start_time": "2025-12-08T02:00:00Z",
  "end_time": "2025-12-08T10:00:00Z",
  "carbon_intensity": 0.15,
  "estimated_emissions_kg": 45.5
}
```

### 2. Scheduler → Stats: Context Query

**Endpoint:** `GET /api/context`

**Purpose:** Get carbon intensity forecast and data center availability

**Query Parameters:**
- `hours` (optional) - Number of hours to forecast (default 24)

**Response Schema:** `ContextResponse`
```json
{
  "locations": [
    {
      "location_id": "dc1",
      "current_load": 25.5,
      "max_capacity": 50.0,
      "carbon_forecast": [
        {
          "timestamp": "2025-12-08T00:00:00Z",
          "intensity": 0.25
        },
        {
          "timestamp": "2025-12-08T01:00:00Z",
          "intensity": 0.22
        },
        {
          "timestamp": "2025-12-08T02:00:00Z",
          "intensity": 0.15
        }
      ]
    }
  ]
}
```

## Key Design Decisions

### Simplicity for Prototyping

The schemas prioritize:
- **Minimal fields**: Only essential data for core functionality
- **Flat structures**: Easy to implement and debug
- **No premature optimization**: Advanced features can be added later
- **Clear examples**: JSON examples that match real use cases

### Carbon-Aware Scheduling

The core concept:
1. Jobs specify resource needs and time flexibility
2. Scheduler queries carbon intensity forecasts
3. Scheduler picks the cleanest time window
4. Returns schedule with emissions estimate

### Time Flexibility

Jobs can specify:
- `earliest_start` and `latest_finish` (optional)
- Scheduler finds the best time within that window
- If not specified, job runs immediately

### Single Data Center

For prototyping, we assume:
- One primary data center (`dc1`)
- Load tracking on 0-50 scale
- Hourly carbon intensity forecasts
- Simple scheduling logic

## Schema Files

Both schemas are valid OpenAPI 3.0.3:

- **`webapp/openapi.yaml`** - 134 lines, 3 schemas
- **`model-load-api/openapi.yaml`** - 315 lines, 6 schemas (includes existing history endpoints)

## Viewing the Schemas

### Swagger UI

You can view interactive API documentation using Swagger UI:

```bash
# Install Swagger UI tools
npm install -g swagger-ui-watcher

# View UI schema
swagger-ui-watcher webapp/openapi.yaml

# View Stats schema
swagger-ui-watcher model-load-api/openapi.yaml
```

### Redoc

For beautiful static documentation:

```bash
# Install Redoc CLI
npm install -g redoc-cli

# Generate HTML documentation
redoc-cli bundle webapp/openapi.yaml -o webapp-api-docs.html
redoc-cli bundle model-load-api/openapi.yaml -o stats-api-docs.html
```

## Implementation Roadmap

### Phase 1: Prototype Core (Current)
- ✅ Simple API schemas defined
- ⚪ Mock scheduler endpoint
- ⚪ Mock context endpoint with static data
- ⚪ Basic UI to submit jobs

### Phase 2: Add Real Data
- Integrate with carbon intensity API (e.g., ElectricityMaps)
- Add actual data center load tracking
- Simple scheduling algorithm (pick lowest carbon time)

### Phase 3: Enhance
- Add more data centers
- Improve forecasting
- Add cost considerations
- Better UI visualization

## Related Documentation

- [Project Brief](./project-brief.md) - High-level goals and concepts
- [System Component Design](./system_component_design.md) - Architecture overview
- [Sequence Diagram](./sequence_diag.svg) - Component interaction flow
- [System Block Diagram](./system_block_diag.svg) - Component relationships

## References

- [OpenAPI 3.0 Specification](https://spec.openapis.org/oas/v3.0.3)
- [Green Software Foundation - SCI](https://greensoftware.foundation/sci)
- [Electricity Maps API](https://www.electricitymaps.com/) - Grid carbon intensity data
- [Cloud Carbon Footprint](https://www.cloudcarbonfootprint.org/) - Cloud emissions tracking
