"""TEMPORARY: API-based forecast predictor.

Uses the UK Carbon Intensity API's 48h regional forecast for the first 48 hours,
then fills the remaining ~5 days with last week's actual data shifted forward.

To revert to SARIMAX predictions, delete this file and restore the import in
predictor.py back to:
    from predictor_sarimax import get_next_week_greenness, get_next_week_carbon_intensity

TODO: Replace with proper ML-based predictions.
"""

import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta

from db_utils import UK_REGION_TO_DC, carbon_intensity_to_greenness

API_BASE_URL = "https://api.carbonintensity.org.uk"

# Reverse mapping: Data Center -> UK region ID
DC_TO_UK_REGION = {dc: rid for rid, dc in UK_REGION_TO_DC.items()}


def _fetch_48h_regional_forecast(region_id: int) -> pd.Series:
    """Fetch 48h carbon intensity forecast for a UK region from the API.

    Returns a pandas Series indexed by datetime with forecast intensity values,
    or an empty Series on failure.
    """
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')
    url = f"{API_BASE_URL}/regional/intensity/{now}/fw48h/regionid/{region_id}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        slots = resp.json().get("data", {}).get("data", [])

        times, values = [], []
        for slot in slots:
            ts_str = slot.get("from", "")
            forecast = slot.get("intensity", {}).get("forecast")
            if forecast is None:
                continue
            ts_str = ts_str.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(ts_str).replace(tzinfo=None)
            except ValueError:
                continue
            times.append(dt)
            values.append(float(forecast))

        if not times:
            return pd.Series(dtype=float)
        return pd.Series(values, index=pd.DatetimeIndex(times)).sort_index()
    except Exception as e:
        print(f"[api_forecast] Error fetching 48h forecast for region {region_id}: {e}")
        return pd.Series(dtype=float)


def _last_week_series(historical_df: pd.DataFrame, col: str) -> pd.Series:
    """Extract last 7 days of a column from historical data, shifted forward 7 days."""
    df = historical_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').dropna(subset=[col])

    if df.empty:
        return pd.Series(dtype=float)

    latest = df['timestamp'].max()
    week_ago = latest - timedelta(days=7)
    last_week = df[df['timestamp'] >= week_ago].set_index('timestamp')[col]

    # Shift forward by 7 days so it lines up with "next week"
    last_week.index = last_week.index + timedelta(days=7)
    return last_week


def _build_forecast(
    api_series: pd.Series,
    last_week: pd.Series,
    clip_min: float,
    clip_max: float,
) -> pd.DataFrame:
    """Combine API 48h forecast with last-week backfill into a 7-day, 5-min DataFrame.

    Returns DataFrame with columns 'ds' and 'yhat' (2016 rows).
    """
    now = pd.Timestamp(datetime.utcnow())
    start = now.ceil('5min')
    full_index = pd.date_range(start, periods=2016, freq='5min')

    # Start with last-week data as the base (covers all 7 days)
    base = last_week.reindex(full_index).interpolate(method='time')

    # Overlay API forecast for the first ~48h (API data is 30-min, upsample to 5-min)
    if not api_series.empty:
        api_5min = api_series.resample('5min').interpolate(method='linear')
        overlap = api_5min.index.intersection(full_index)
        if len(overlap):
            base.loc[overlap] = api_5min.loc[overlap]

    # Fill any remaining gaps (sparse history, or no history at all)
    base = base.ffill().bfill()

    yhat = np.clip(base.values, clip_min, clip_max)
    return pd.DataFrame({'ds': full_index, 'yhat': yhat})


def get_next_week_load(historical_df, location: str) -> pd.DataFrame:
    """TEMPORARY: Generate noisy-but-realistic random load data for the next week.

    Calls generate_load() directly — no training, no regression.
    Returns DataFrame with 'ds' and 'yhat' columns (2016 rows, 7 days × 288/day).

    To revert, delete this function and restore the import in predictor.py to:
        from predictor_linreg import get_next_week_load
    """
    from generate_history import generate_load, DATA_CENTRES

    dc_index = 0
    if location in DATA_CENTRES:
        dc_index = DATA_CENTRES.index(location)

    now = pd.Timestamp.now()
    start = now.ceil('5min')
    timestamps = pd.date_range(start, periods=2016, freq='5min')

    values = [generate_load(ts.to_pydatetime(), dc_index) for ts in timestamps]
    return pd.DataFrame({'ds': timestamps, 'yhat': values})


def get_next_week_carbon_intensity(historical_df, location: str) -> pd.DataFrame:
    """Predict next-week carbon intensity using API forecast + last week's actuals.

    Args:
        historical_df: DataFrame with 'timestamp' and 'carbon_intensity' columns.
        location: Data center identifier (e.g. "Data-Center-1").

    Returns:
        DataFrame with columns 'ds' (datetime) and 'yhat' (gCO2/kWh, 0-500).
    """
    region_id = DC_TO_UK_REGION.get(location)
    if region_id is None:
        raise ValueError(f"No UK region mapping for location: {location}")

    api_series = _fetch_48h_regional_forecast(region_id)
    last_week = _last_week_series(historical_df, 'carbon_intensity')

    return _build_forecast(api_series, last_week, clip_min=0, clip_max=500)


def get_next_week_greenness(historical_df, location: str) -> pd.DataFrame:
    """Predict next-week greenness using API forecast + last week's actuals.

    Fetches carbon intensity forecast from the API, converts to greenness.
    Falls back to raw greenness history if no carbon_intensity data exists.

    Args:
        historical_df: DataFrame with 'timestamp', 'greenness', and optionally
                       'carbon_intensity' columns.
        location: Data center identifier (e.g. "Data-Center-1").

    Returns:
        DataFrame with columns 'ds' (datetime) and 'yhat' (greenness 0-100).
    """
    region_id = DC_TO_UK_REGION.get(location)

    if region_id is not None:
        # Build carbon intensity forecast, then convert to greenness
        api_series = _fetch_48h_regional_forecast(region_id)
        has_ci = (
            'carbon_intensity' in historical_df.columns
            and historical_df['carbon_intensity'].notna().any()
        )
        last_week = (_last_week_series(historical_df, 'carbon_intensity')
                     if has_ci else pd.Series(dtype=float))
        ci_df = _build_forecast(api_series, last_week, clip_min=1, clip_max=500)
        # Convert: 1/CI normalised to 0-100 (matches db_utils.carbon_intensity_to_greenness)
        greenness = 100.0 / np.maximum(ci_df['yhat'].values, 1)
        ci_df['yhat'] = np.clip(greenness, 0, 100)
        return ci_df

    # Fallback: unknown region — use raw greenness history
    last_week = _last_week_series(historical_df, 'greenness')
    return _build_forecast(pd.Series(dtype=float), last_week, clip_min=0, clip_max=100)
