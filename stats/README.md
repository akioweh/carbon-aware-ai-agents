# Stats Component

A RESTful API for tracking and retrieving data center load and grid energy
greenness metrics.

## Overview

This API provides historical and current data about:

- **Load**: Data center load ranging from 0-50 arbitrary units (50 being
  capacity)
- **Greenness**: Energy greenness score from 0-100 (higher values indicate
  greener energy)

Data is collected at 5-minute intervals and is pattern-based to enable
forecasting and task scheduling.

## Getting Started

### Installation

```bash
pip install -r requirements.txt
```

### Generate History Data

Before running the API, optionally generate sample history data:

```bash
python generate_history.py
```

This will create a `history.json` file with 30 days of historical data.

### Run the API

```bash
python app.py
```

The API will start on `http://localhost:5000` by default.

...or directly using `uvicorn`:

```bash
uvicorn app:app --reload
```

## API Documentation

An OpenAPI 3.0 specification, [openapi.yaml](./openapi.yaml), is auto-generated
as per the endpoints every time `app` is ran.

### Endpoints

#### Forecast Endpoints

- `GET /locations/{location}/metrics/forecast_load` - Returns load forecast for
  the next week
- `GET /locations/{location}/metrics/forecast_greenness` - Returns greenness
  forecast for the next week

#### Datacenter Endpoints

- `GET /datacenter` - Returns a list of available datacenter names

### Example Responses

#### Load Forecast Response

```json
{
  "location_id": "Data-Center-1",
  "metric": "forecast_load",
  "unit": "utilization_units",
  "capacity": {
    "max_load": 50.0,
    "total_gpus": 32
  },
  "data": [
    {
      "timestamp": "2026-01-23T19:00:00",
      "value": 25.5,
      "is_forecast": true,
      "available_gpus": 16
    }
  ]
}
```

#### Greenness Forecast Response

```json
{
  "location_id": "Data-Center-1",
  "metric": "forecast_greenness",
  "unit": "greenness_score",
  "data": [
    {
      "timestamp": "2026-01-23T19:00:00",
      "value": 75.3,
      "is_forecast": true
    }
  ]
}
```

## Data Generation

The `generate_history.py` script creates synthetic data with complex, realistic
patterns:

- **Load**: Follows a realistic "workday" vs "weekend" schedule.
  - **Weekdays**: Feature a morning spike (start of work), a slight lunch dip,
    sustained afternoon load, and evening activity.
  - **Weekends**: Smoother, lower overall load peaking in the afternoon.
  - **Micro-bursts**: Random, short-duration spikes in load (simulating batch
    jobs or traffic surges).
  - Values range from 0-50 units.

- **Greenness**: Modeled using a simulated "Weather System" that persists state
  over time.
  - **Solar**: Bell curve based on time of day, modulated by dynamic **Cloud
    Cover**.
  - **Wind**: Random walk "wind speed" trend that changes slowly over
    hours/days.
  - **Grid Baseline**: A slowly fluctuating baseline representing other grid
    sources.
  - The final score is a weighted sum of Solar, Wind, and Grid factors.
  - Values range from 0-100.

## Service Behavior

- On startup, the service loads historical data from `history.json` and
  generates them fresh if not found.
- The service concurrently (in a background thread) computes new predictions
  (every 5 minutes)
- On each request, the service returns the latest data point from the history.

Specifically, the background worker writes to a sqlite database that the request
handlers also read from.

> [!TIP]  
> This architecture avoids stale data while also maintaining API latency.
