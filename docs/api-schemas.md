# API Schemas Documentation

This document provides an overview of the OpenAPI schemas that define the REST APIs for the Carbon-Aware AI Agents system.

## Overview

The system comprises three main components that communicate via RESTful HTTP APIs:

1. **UI (webapp)** - User interface for job submission and visualization
2. **Scheduler** - Core optimization logic for workload placement
3. **Stats (model-load-api)** - Environmental and operational data provider

Two OpenAPI 3.0 schemas define these interactions:

- **`webapp/openapi.yaml`** - UI ↔ Scheduler API
- **`model-load-api/openapi.yaml`** - Stats API (including Scheduler ↔ Stats endpoint)

## API Interactions

### 1. UI → Scheduler: Job Submission

**Endpoint:** `POST /api/schedule`

**Purpose:** Submit an AI workload for carbon-aware scheduling

**Request Schema:** `JobSpecification`
```yaml
{
  "workload_id": "train-llm-v3",
  "type": "training",                    # training, inference, batch_job, fine_tuning
  "functional_unit": "epoch",            # epoch, request, gb_processed
  "estimated_workload": 20,              # Number of functional units
  "resources": {
    "gpu_type": "A100",
    "gpu_count": 8,
    "memory_gb": 512,
    "storage_gb": 2000
  },
  "temporal_flexibility": {
    "earliest_start": "2025-12-08T00:00:00Z",
    "latest_finish": "2025-12-10T23:59:59Z"
  },
  "policy": {
    "allowed_providers": ["aws", "azure", "on-prem-dc1"],
    "compliance_requirements": ["gdpr", "soc2"]
  },
  "budget": {
    "max_cost_usd": 5000
  },
  "objective_profile": {
    "weight_sci": 0.5,        # Carbon emissions weight
    "weight_water": 0.2,      # Water usage weight
    "weight_materials": 0.1,  # Hardware wear weight
    "weight_cost": 0.15,      # Cost weight
    "weight_latency": 0.05    # Latency weight
  }
}
```

**Response Schema:** `ScheduleResponse`
```yaml
{
  "schedule_id": "sched-abc123",
  "workload_id": "train-llm-v3",
  "placement": {
    "location": "on-prem-dc1",
    "location_type": "on-premise",
    "start_time": "2025-12-08T03:00:00Z",
    "end_time": "2025-12-08T15:00:00Z",
    "duration_hours": 12
  },
  "expected_metrics": {
    "sci_per_unit": 18.5,          # kg CO₂e per functional unit
    "total_co2e_kg": 370,           # Total emissions
    "total_energy_kwh": 2468,       # Total energy consumption
    "total_water_liters": 1850,     # Total water usage
    "estimated_cost_usd": 3200
  },
  "compliance_proof": {
    "meets_slos": true,
    "meets_policy": true,
    "meets_budget": true
  },
  "explanation": {
    "reasoning": "Selected on-premise DC1 during low grid carbon intensity window..."
  }
}
```

### 2. Scheduler → Stats: Context Query

**Endpoint:** `GET /api/context`

**Purpose:** Retrieve environmental and operational context for scheduling decisions

**Query Parameters:**
- `start_time` (optional) - Beginning of time window (ISO 8601)
- `end_time` (optional) - End of time window (ISO 8601)
- `locations` (optional) - Comma-separated list of locations

**Response Schema:** `SchedulingContext`
```yaml
{
  "timestamp": "2025-12-07T22:47:00Z",
  "time_window": {
    "start": "2025-12-08T00:00:00Z",
    "end": "2025-12-10T23:59:59Z"
  },
  "locations": [
    {
      "location_id": "on-prem-dc1",
      "location_type": "on-premise",
      "current_load": 25.5,              # 0-50 scale (50 = max capacity)
      "max_capacity": 50.0,
      "available_capacity": 24.5,
      "grid_carbon_intensity_forecast": [
        {
          "timestamp": "2025-12-08T00:00:00Z",
          "intensity_kg_per_kwh": 0.25   # kg CO₂e per kWh
        },
        {
          "timestamp": "2025-12-08T03:00:00Z",
          "intensity_kg_per_kwh": 0.15   # Lower = cleaner grid
        }
      ],
      "facility_metrics": {
        "pue": 1.2,                      # Power Usage Effectiveness
        "wue": 1.8,                      # Water Usage Effectiveness (L/kWh)
        "renewable_percentage": 45       # % renewable energy
      },
      "cost_context": {
        "cost_per_gpu_hour": 3.50,
        "cost_per_cpu_hour": 0.25,
        "currency": "USD"
      },
      "hardware_availability": [
        {
          "gpu_type": "A100",
          "available_count": 16,
          "total_count": 32
        }
      ]
    }
  ]
}
```

## Key Design Decisions

### Software Carbon Intensity (SCI) Metric

The APIs are designed around the [Green Software Foundation's SCI metric](https://greensoftware.foundation/):

```
SCI = (Energy × Carbon Intensity) / Functional Unit
```

This allows workload-specific carbon accounting (e.g., kg CO₂e per epoch, per request, etc.).

### Temporal Flexibility

Workloads specify a time window (`earliest_start` to `latest_finish`), enabling the scheduler to:
- Shift execution to cleaner grid windows
- Optimize across time zones
- Balance load across data centers

### Hybrid Cloud + On-Premise Support

The schemas distinguish between:
- **Cloud locations** - Elastic capacity (null for load/capacity fields)
- **On-premise locations** - Fixed capacity (0-50 scale for load tracking)
- **Edge locations** - Future support

### Multi-Objective Optimization

The `objective_profile` allows users to configure trade-offs:
- **Carbon-first**: High `weight_sci`, low others
- **Cost-conscious**: Balance `weight_sci` and `weight_cost`
- **Balanced**: Even distribution across all weights

Weights don't need to sum to 1.0; the scheduler normalizes them automatically.

### Explainable AI

All schedule decisions include:
- Human-readable reasoning
- Expected metrics with transparency
- Alternative schedules considered
- Compliance proof for auditability

## Schema Validation

Both schemas are validated against OpenAPI 3.0.3 specification:

```bash
# Install validator
pip install openapi-spec-validator

# Validate schemas
python -c "
from openapi_spec_validator import validate_spec
from openapi_spec_validator.readers import read_from_filename

spec_dict, spec_url = read_from_filename('webapp/openapi.yaml')
validate_spec(spec_dict)
print('✓ webapp/openapi.yaml is valid')

spec_dict, spec_url = read_from_filename('model-load-api/openapi.yaml')
validate_spec(spec_dict)
print('✓ model-load-api/openapi.yaml is valid')
"
```

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

## Implementation Status

| Component | Schema | Implementation |
|-----------|--------|----------------|
| UI (webapp) | ✅ Complete | 🟡 In Progress |
| Scheduler | ✅ Complete | ⚪ Not Started |
| Stats (model-load-api) | ✅ Complete | 🟡 Partial (history endpoints exist) |

### Next Steps

1. **Scheduler Implementation**
   - Implement `POST /api/schedule` endpoint
   - Integrate constraint solver
   - Add SCI calculations

2. **Stats Enhancement**
   - Implement `GET /api/context` endpoint
   - Add forecasting engine
   - Integrate with external data sources (grid carbon APIs)

3. **UI Enhancement**
   - Build job submission form
   - Create schedule visualization dashboard
   - Add real-time carbon intensity displays

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
