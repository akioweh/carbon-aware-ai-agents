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
  "job_type": "training",
  "functional_unit": "epoch",
  "workload_amount": 20,
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
  "estimated_emissions_kg": 45.5,
  "sci_per_unit": 2.28
}
```

**Key Fields:**
- `functional_unit`: The unit for SCI calculation (epoch, request, GB_processed, etc.)
- `workload_amount`: Number of functional units to process
- `sci_per_unit`: Software Carbon Intensity per functional unit (kg CO₂e)

### 2. Scheduler → Stats: Unified Metrics API

The Stats API uses a **unified, location-based structure** for all metrics:

**Pattern:** `/locations/{location}/metrics/{metric}`

All metrics follow the same time-series structure and query parameters, making the API coherent and easy to use.

#### `GET /locations/{location}/metrics/carbon`
Get grid carbon intensity time-series with forecasts

**Query params:** `start`, `end`, `include_forecast`

```json
{
  "location_id": "dc1",
  "metric": "carbon_intensity",
  "unit": "kg_co2_per_kwh",
  "data": [
    {"timestamp": "2025-12-08T00:00:00Z", "value": 0.25, "is_forecast": false},
    {"timestamp": "2025-12-08T01:00:00Z", "value": 0.22, "is_forecast": true},
    {"timestamp": "2025-12-08T02:00:00Z", "value": 0.15, "is_forecast": true}
  ]
}
```

#### `GET /locations/{location}/metrics/load`
Get data center load time-series with capacity info

**Query params:** `start`, `end`

```json
{
  "location_id": "dc1",
  "metric": "load",
  "unit": "utilization_units",
  "capacity": {
    "max_load": 50.0,
    "total_gpus": 32
  },
  "data": [
    {"timestamp": "2025-12-08T00:00:00Z", "value": 25.5, "available_gpus": 16},
    {"timestamp": "2025-12-08T01:00:00Z", "value": 28.0, "available_gpus": 14}
  ]
}
```

#### `GET /locations/{location}/metrics/weather`
Get weather time-series

**Query params:** `start`, `end`, `include_forecast`

```json
{
  "location_id": "dc1",
  "metric": "weather",
  "data": [
    {
      "timestamp": "2025-12-08T00:00:00Z",
      "temperature_celsius": 22,
      "humidity_percent": 65,
      "is_forecast": false
    }
  ]
}
```

#### `GET /locations/{location}/metrics/cost`
Get compute cost information

```json
{
  "location_id": "dc1",
  "metric": "cost",
  "currency": "USD",
  "effective_date": "2025-12-01T00:00:00Z",
  "rates": {
    "cost_per_gpu_hour": 2.50,
    "cost_per_cpu_hour": 0.10,
    "cost_per_gb_hour": 0.01
  }
}
```

#### `GET /locations`
List all available locations

```json
[
  {"location_id": "dc1", "name": "Data Center 1", "region": "us-east"},
  {"location_id": "dc2", "name": "Data Center 2", "region": "us-west"}
]
```

## Key Design Decisions

### Simplicity for Prototyping

The schemas prioritize:
- **Minimal fields**: Only essential data for core functionality
- **Flat structures**: Easy to implement and debug
- **No premature optimization**: Advanced features can be added later
- **Clear examples**: JSON examples that match real use cases

### SCI Metric Support

Jobs now include functional units for proper SCI calculation:
- `functional_unit`: The unit of work (epoch, request, GB_processed, etc.)
- `workload_amount`: Number of units to process
- Response includes `sci_per_unit`: Software Carbon Intensity per functional unit

**SCI Formula:** `SCI = (Energy × Carbon Intensity) / Functional Unit`

### Unified Stats API Design

Stats API uses a **normalized, location-based structure**:

**Path Pattern:** `/locations/{location}/metrics/{metric}`

**Unified Query Parameters:**
- `start` / `end` - Time range for historical data
- `include_forecast` - Include future predictions

**Normalized Response Structure:**
```json
{
  "location_id": "dc1",
  "metric": "metric_name",
  "unit": "measurement_unit",
  "data": [
    {"timestamp": "...", "value": 0.0, "is_forecast": false}
  ]
}
```

**Benefits:**
- **Consistent interface** - Same query pattern for all metrics
- **Clear hierarchy** - Location → Metric is natural and REST-compliant
- **Time-series native** - All data properly structured as time-series
- **Forecast support** - Built-in via `is_forecast` flag
- **Easy to extend** - New metrics follow the same pattern

### Carbon-Aware Scheduling

The core concept:
1. Jobs specify resource needs, workload type, and time flexibility
2. Scheduler queries carbon forecast and capacity data
3. Scheduler picks the cleanest time window with available capacity
4. Returns schedule with emissions estimate and SCI per functional unit

## Schema Files

Both schemas are valid OpenAPI 3.0.3:

- **`webapp/openapi.yaml`** - 161 lines, 3 schemas, 1 endpoint
- **`model-load-api/openapi.yaml`** - 667 lines, 13 schemas, 11 endpoints
  - 6 legacy endpoints (`/history`, `/latest` - backward compatibility)
  - 5 unified endpoints (`/locations`, `/locations/{location}/metrics/*`)

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
