# Model Load API

A Flask-based API for tracking and retrieving data center load and greenness metrics.

## Overview

This API provides historical and current data about:
- **Load**: Data center load ranging from 0-50 arbitrary units (50 being capacity)
- **Greenness**: Energy greenness score from 0-100 (higher values indicate greener energy)

Data is collected at 5-minute intervals and is pattern-based to enable forecasting and task scheduling.

## Getting Started

### Prerequisites

- Python 3.x
- Flask

### Installation

```bash
pip install flask
```

### Generate History Data

Before running the API, generate sample history data:

```bash
python generate_history.py
```

This will create a `history.json` file with 30 days of historical data.

### Run the API

```bash
python app.py
```

The API will start on `http://localhost:5000` by default.

## API Documentation

The API is fully documented using OpenAPI 3.0 specification. See `openapi.yaml` for the complete specification.

### Endpoints

#### History Endpoints

- `GET /history` - Returns complete history with timestamp, load, and greenness
- `GET /load/history` - Returns load history only (timestamp + load)
- `GET /greenness/history` - Returns greenness history only (timestamp + greenness)

#### Latest Endpoints

- `GET /latest` - Returns the most recent data point (timestamp, load, greenness)
- `GET /load/latest` - Returns the most recent load data (timestamp + load)
- `GET /greenness/latest` - Returns the most recent greenness data (timestamp + greenness)

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

## OpenAPI Schema

The complete OpenAPI 3.0 schema is available in `openapi.yaml`. You can use this schema with various tools:

### Validation

Validate the OpenAPI schema:

```bash
pip install openapi-spec-validator
openapi-spec-validator openapi.yaml
```

### Swagger UI

You can view the API documentation using Swagger UI or other OpenAPI tools by importing the `openapi.yaml` file.

### Viewing with Swagger Editor

1. Go to [Swagger Editor](https://editor.swagger.io/)
2. Import the `openapi.yaml` file
3. View the interactive documentation

## Data Generation

The `generate_history.py` script creates synthetic data with the following patterns:

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

## Notes

This is a prototype API designed for demonstrating carbon-aware scheduling concepts. The data is synthetic and pattern-based to enable predictable forecasting and task scheduling.
