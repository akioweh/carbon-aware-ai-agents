# Stats Component

This API provides historical and forecasted data on:

- data center load
- data center capacity
- grid energy greenness

## Getting Started

Python 3.14.

You should probably use a virtual environment. Using `uv`:

```bash
uv venv .venv
```

(`uv run` and `uv pip` will auto-activate the venv in the cwd.)

### Install dependencies

```bash
uv pip install -r requirements.txt
```

### Run the API

```bash
uv run app.py
```

The API will start on `http://localhost:5000` by default.

...or directly using `uvicorn`:

```bash
uv run uvicorn app:app --reload
```

### Development Tooling

Use ruff to format and lint (sort imports):

```bash
ruff check --select I --fix .
ruff format .
```

## API Documentation

An OpenAPI 3.0 specification, [openapi.yaml](./openapi.yaml), is auto-generated
as per the endpoints every time `app` is ran.

## Testing

The project uses `pytest`.  
`schemathesis` is used for property-based API testing.

Run all tests:

```bash
uv run pytest tests
```

Run a specific test suite:

```bash
uv run pytest tests/<test_name>.py
```

Note: The tests require the API server to be running on `http://localhost:5000`.

## Service Behavior

- On startup, the service initializes the SQLite database (`cache.db`).
<!-- (TODO: out of date info?) -->
- If a legacy `history.json` exists and the database is empty, it migrates the
data.
<!-- (TODO: out of date info?) -->
- If the database is empty and no history exists, it generates fresh historical
  data.
- The service concurrently (in a background thread) computes new predictions
  (every 5 minutes).
- On each request, the service returns the latest data point from the history.

The background worker writes to the sqlite database that the request handlers
also read from.

> [!TIP]  
> This architecture avoids stale data while also maintaining API latency.
