# Stats Component

This FastAPI service provides historical observations and high-resolution
forecasts for data center load and carbon intensity. It serves as the primary
data source for the [Scheduler](../scheduler), enabling carbon-aware workload
placement.

## Development Setup

### Software

- **Python 3.14+**
- **uv**: Recommended for fast package management and virtual environments.

### Toolchain

1. **Virtual Environment**:

   ```bash
   uv venv .venv
   source .venv/bin/activate  # or use `uv run` for automatic activation
   ```

2. **Install Dependencies**:

   ```bash
   uv pip install -r requirements.txt
   ```

3. **Development Tooling**: The project uses `ruff` for linting and formatting.

   ```bash
   ruff check --fix .
   ruff format .
   ```

### Quickstart

1. Ensure `cache.db` and `carbon_intensity.db` can be initialized in the
   component root.
2. Run the API:

   ```bash
   uv run app.py
   ```

   The service will start on `http://127.0.0.1:5000` by default.

3. **OpenAPI Docs**: Available at `http://127.0.0.1:5000/docs` or via the
   auto-generated [`openapi.yaml`](./openapi.yaml).

### Testing

The component uses `pytest` for unit/integration tests and `schemathesis` for
property-based API testing.

```bash
uv run pytest tests
```

Note: API tests require the server to be running locally at
`http://localhost:5000`.

## Implementation Details

### Forecasting Models

#### Carbon Intensity (CI)

The service uses a **Direct Multi-step Ridge Regression** model to forecast
carbon intensity.

- **Data Source**: Historical 30-minute readings from the
  [UK Carbon Intensity API](https://carbonintensity.org.uk/).
- **Features**: Cyclical time features (hour, day, minute) and exogenous weather
  features (wind speed, temperature, solar radiation) fetched from the
  [Open-Meteo API](https://open-meteo.com/).
- **Resolution**: Predicts at 30-minute intervals and upsamples to **5-minute
  resolution** via linear interpolation for the scheduler.

#### Data Center Load

As no real-time load source is available, the service generates synthetic load
patterns combined with historical averages to provide a realistic baseline for
the scheduler.

### Data Collection & Syncing

1. **Backfill**: On startup, the service performs an incremental backfill from
   the UK Carbon Intensity API for all tracked regions.
2. **Background Collection**: A dedicated thread (`carbon_collector_loop`)
   fetches new readings every 5-30 minutes.
3. **Syncing**: Raw readings from `carbon_intensity.db` are periodically synced
   into the main `cache.db` historical tables to ensure the predictors have
   access to the latest ground truth.

## System Design

### Architecture Overview

```
stats/
├── app.py                # Entry point & lifespan management
├── routes.py             # FastAPI endpoint definitions
├── background.py         # Periodic task loops (predictions, sync)
├── predictors/           # Forecasting logic & orchestrator
│   ├── ridge.py          # Direct Ridge CI model
│   └── load.py           # Load forecasting logic
├── data/                 # External data collection
│   ├── carbon_collector.py # UK API client
│   └── generate_history.py # Synthetic load generator
├── db_utils.py           # SQLite persistence layer
├── models.py             # Pydantic DTOs & API schemas
└── config.py             # Environment & constant configuration
```

### Data Flows

#### 1. Startup & Initialization

The service follows a strict initialization sequence:

1. Initialize SQLite databases.
2. Backfill missing carbon data from the external API.
3. Sync new data to historical tables.
4. Launch background threads for prediction updates and carbon collection.

> [!IMPORTANT]  
> **Cold Start Performance**: On startup, the service initiates the first full
> training pass for all active datacenters. This process typically takes **~10
> minutes** to reach stability, during which the service will exhibit **high CPU
> and RAM usage**. API requests made during this window may return cached
> (stale) forecasts until the initial models are fit and cached.

#### 2. Forecast Request (`GET /locations/{id}/metrics/forecast_load`)

1. **Request**: Scheduler or UI requests a time window.
2. **Stitching**: The orchestrator fetches historical observations from
   `cache.db` and future predictions from the prediction cache.
3. **Alignment**: Historical data is upsampled to 5-minute intervals. Boundary
   points are deduplicated to ensure a smooth transition from "actual" to
   "forecast" data.
4. **Response**: Returns a unified time series with `is_forecast` flags.

#### 3. Prediction Update Loop

To maintain low API latency, forecasts are not computed on-demand. Instead:

1. Every 30 minutes, `prediction_loop` runs the Ridge model for all active
   datacenters.
2. 7-day forecasts (2016 data points) are serialized to JSON and stored in the
   `predictions` table in `cache.db`.
3. The API serves these pre-computed results instantly.

## Component Design Notes

### Persistence Layer

The component uses two SQLite databases to separate concerns:

- **`carbon_intensity.db`**: Stores raw, normalized readings from the UK Carbon
  Intensity API. Used for long-term history and model training.
- **`cache.db`**: Stores upsampled historical data, pre-computed forecasts, and
  datacenter configuration. Optimized for fast retrieval by the API.

### Prediction Window

All forecasts are fixed to a **168-hour (7-day)** window at **5-minute
resolution**. This allows the Scheduler to perform long-term optimizations while
maintaining high granularity for near-term placement.

### Error Handling & Alerts

Background loops track consecutive failures. If a loop (e.g., prediction
generation) fails multiple times (default 5), a `CRITICAL` log is issued to
signal that forecasts may be becoming stale.

