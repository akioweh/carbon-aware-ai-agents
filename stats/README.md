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

#### History Endpoints

- `GET /history` - Returns complete history with timestamp, load, and greenness
- `GET /load/history` - Returns load history only (timestamp + load)
- `GET /greenness/history` - Returns greenness history only (timestamp +
  greenness)

#### Latest Endpoints

- `GET /latest` - Returns the most recent data point (timestamp, load,
  greenness)
- `GET /load/latest` - Returns the most recent load data (timestamp + load)
- `GET /greenness/latest` - Returns the most recent greenness data (timestamp +
  greenness)

### Example Responses

#### Full Data Point

```json
{
  "timestamp": "2025-12-05T18:20:39.679404",
  "load": 25.5,
  "greenness": 75.3
}
```

#### Load Data Point

```json
{
  "timestamp": "2025-12-05T18:20:39.679404",
  "load": 25.5
}
```

#### Greenness Data Point

```json
{
  "timestamp": "2025-12-05T18:20:39.679404",
  "greenness": 75.3
}
```

## Data Generation

The `generate_history.py` script creates synthetic data with the following
patterns:

- **Load**: Follows a daily sinusoidal pattern with peak at 3pm and low at 3am
  - Weekends have 30% less load than weekdays
  - Random noise is added for realism
  - Values range from 0-50 units

- **Greenness**: Varies by time of day to simulate solar energy availability
  - High during sunny hours (10am-4pm): ~80
  - Medium during morning/evening (6am-10am, 4pm-8pm): ~40-50
  - Low during night (8pm-6am): ~10
  - Random noise is added for realism
  - Values range from 0-100

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
