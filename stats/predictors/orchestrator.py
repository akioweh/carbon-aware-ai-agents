import json
from datetime import datetime, timedelta, timezone

import pandas as pd

import db_utils
from config import DEFAULT_CAPACITY, PREDICTION_WINDOW_HOURS
from data.generate_history import generate_load

from .load import get_next_week_load
from .ridge import get_next_week_carbon_intensity


def generate_next_week_load_prediction(location):
    """Generate load predictions for the next week at a specific location."""
    now = pd.Timestamp.now().ceil('5min')
    location_history = db_utils.get_historical_data(location)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_load = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'load': entry['load'],
            }
            for entry in location_history
        ]
    )
    next_week_load_df = get_next_week_load(historical_load, now=now)

    return {
        'location_id': location,
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': [
            {
                'timestamp': next_week_load_df.iloc[i]['ds'].isoformat(),
                'value': max(0.0, float(next_week_load_df.iloc[i]['yhat'])),
                'is_forecast': True,
                'capacity': DEFAULT_CAPACITY,
            }
            for i in range(len(next_week_load_df))
        ],
    }


def generate_next_week_carbon_intensity_prediction(location):
    """Generate carbon intensity predictions for the next week at a specific location."""
    now = pd.Timestamp.now().ceil('5min')
    location_history = db_utils.get_historical_data(location)

    if not location_history:
        raise ValueError(f'No history found for location: {location}')

    historical_df = pd.DataFrame(
        [
            {
                'timestamp': entry['timestamp'],
                'carbon_intensity': entry.get('carbon_intensity'),
                'location': location,
            }
            for entry in location_history
        ]
    )

    if historical_df['carbon_intensity'].isna().all():
        raise ValueError(f'No carbon intensity data available for location: {location}')

    next_week_ci_df = get_next_week_carbon_intensity(historical_df, now=now)

    return {
        'location_id': location,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2/kWh',
        'data': [
            {
                'timestamp': next_week_ci_df.iloc[i]['ds'].isoformat(),
                'value': float(next_week_ci_df.iloc[i]['yhat']),
                'is_forecast': True,
            }
            for i in range(len(next_week_ci_df))
        ],
    }


def _upsample_historical(entries, fill_until=None):
    """Upsample 30-min historical observations to 5-min intervals via forward-fill.

    Args:
        entries: List of dicts from db_utils.get_historical_data()
        fill_until: Optional UTC-aware datetime — forward-fill the last
                    observation up to this point (bridges gap to forecasts)

    Returns:
        List of dicts at 5-min intervals in the same format as the input.
    """
    if not entries:
        return entries

    df = pd.DataFrame(entries)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp').sort_index()

    # Build a 5-min grid from the first observation to fill_until (or last obs)
    end = df.index[-1]
    if fill_until is not None:
        fill_ts = (
            pd.Timestamp(fill_until).tz_localize('UTC')
            if pd.Timestamp(fill_until).tzinfo is None
            else pd.Timestamp(fill_until)
        )
        fill_ts = fill_ts.ceil('5min')
        end = max(end, fill_ts)

    idx = pd.date_range(start=df.index[0], end=end, freq='5min')
    df = df.reindex(df.index.union(idx)).ffill().reindex(idx)

    result = []
    for ts, row in df.iterrows():
        load = row['load']
        entry = {
            'timestamp': ts.to_pydatetime(),
            'load': None if (load is None or pd.isna(load)) else load,
        }
        ci = row.get('carbon_intensity')
        entry['carbon_intensity'] = None if (ci is None or pd.isna(ci)) else ci
        result.append(entry)
    return result


def refresh_historical_cache(location):
    """Pre-compute and cache upsampled 7-day historical data for a location."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    raw_history = db_utils.get_historical_data(location, week_ago, None)
    upsampled = _upsample_historical(raw_history, fill_until=now)

    # Fill missing load values with synthetic data (load has no real source)
    for entry in upsampled:
        load = entry['load']
        if load is None or (isinstance(load, float) and pd.isna(load)):
            entry['load'] = generate_load(entry['timestamp'], 0)

    db_utils.save_historical_cache(location, upsampled)


def _get_cached_historical(location, start, end):
    """Try to serve historical data from the pre-upsampled cache.

    Returns a list of entry dicts on cache hit, or None on miss.
    The cache only covers the last 7 days — requests older than that
    fall back to the raw historical_data table + upsample.
    """
    if not start:
        return None

    return db_utils.get_historical_cache(location, start, end)


def _resolve_time_window(start_time, end_time, now):
    """Compute effective start/end from optional params.

    Returns (effective_start, effective_end) as UTC-aware datetimes.
    """
    effective_end = end_time if end_time else now + timedelta(hours=PREDICTION_WINDOW_HOURS)
    effective_start = start_time  # None means "all available history"
    return effective_start, effective_end


def _slice_cached_data(data_points, start_time, end_time):
    """Filter cached data points to those within [start_time, end_time]."""
    result = []
    for point in data_points:
        ts = datetime.fromisoformat(point['timestamp'])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if start_time and ts < start_time:
            continue
        if end_time and ts > end_time:
            continue
        result.append(point)
    return result


def _get_forecast_data(location, metric):
    """Get forecast data from cache or generate fresh.

    Args:
        location: Datacenter location ID
        metric: 'load' or 'carbon_intensity'

    Returns:
        List of data point dicts with timestamp, value, is_forecast, etc.
    """
    if metric == 'load':
        cache_key = f'load_forecast_{location}'
    else:
        cache_key = f'carbon_intensity_forecast_{location}'

    cached = db_utils.get_cached_prediction(cache_key)
    if cached:
        return cached['data']

    if metric == 'load':
        result = generate_next_week_load_prediction(location)
    else:
        result = generate_next_week_carbon_intensity_prediction(location)

    db_utils.save_prediction(cache_key, result)
    return result['data']


def get_load_time_series(location, start_time=None, end_time=None):
    """Get load time series stitching historical observations and forecasts.

    Args:
        location: Datacenter location ID
        start_time: Optional UTC-aware start datetime
        end_time: Optional UTC-aware end datetime

    Returns:
        Response dict with location_id, metric, unit, data
    """
    now = datetime.now(timezone.utc)
    effective_start, effective_end = _resolve_time_window(start_time, end_time, now)

    data_points = []

    # Historical data (past) — upsampled from 30-min to 5-min
    if effective_start is None or effective_start < now:
        hist_end = min(effective_end, now)
        # Try cache first
        historical = _get_cached_historical(location, effective_start, hist_end)
        if historical is None:
            raw_history = db_utils.get_historical_data(location, effective_start, hist_end)
            historical = _upsample_historical(raw_history, fill_until=hist_end)
        else:
            # Cache may be stale (last refresh up to 30 min ago).
            # Forward-fill the last cached point to hist_end so there's no
            # gap between historical and forecast that the scheduler would
            # fill with zeros.
            historical = _upsample_historical(historical, fill_until=hist_end)
        for entry in historical:
            load = entry['load']
            if load is None or (isinstance(load, float) and pd.isna(load)):
                load = generate_load(entry['timestamp'], 0)
            data_points.append(
                {
                    'timestamp': entry['timestamp'].isoformat(),
                    'value': max(0.0, float(load)),
                    'is_forecast': False,
                    'capacity': DEFAULT_CAPACITY,
                }
            )

    # Forecast data (future)
    if effective_end > now:
        forecast_data = _get_forecast_data(location, 'load')
        forecast_start = max(effective_start, now) if effective_start else now
        sliced = _slice_cached_data(forecast_data, forecast_start, effective_end)
        for point in sliced:
            point_copy = dict(point)
            point_copy['is_forecast'] = True
            data_points.append(point_copy)

    # Deduplicate at boundary — prefer historical (is_forecast=False)
    seen = {}
    deduped = []
    for point in data_points:
        ts = point['timestamp']
        if ts in seen:
            # Prefer historical over forecast
            if not point['is_forecast']:
                # Replace the forecast entry
                deduped[seen[ts]] = point
        else:
            seen[ts] = len(deduped)
            deduped.append(point)

    return {
        'location_id': location,
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': deduped,
    }


def get_carbon_intensity_time_series(location, start_time=None, end_time=None):
    """Get carbon intensity time series stitching historical observations and forecasts.

    Args:
        location: Datacenter location ID
        start_time: Optional UTC-aware start datetime
        end_time: Optional UTC-aware end datetime

    Returns:
        Response dict with location_id, metric, unit, data
    """
    now = datetime.now(timezone.utc)
    effective_start, effective_end = _resolve_time_window(start_time, end_time, now)

    data_points = []

    # Historical data (past) — upsampled from 30-min to 5-min
    if effective_start is None or effective_start < now:
        hist_end = min(effective_end, now)
        # Try cache first
        historical = _get_cached_historical(location, effective_start, hist_end)
        if historical is None:
            raw_history = db_utils.get_historical_data(location, effective_start, hist_end)
            historical = _upsample_historical(raw_history, fill_until=hist_end)
        else:
            historical = _upsample_historical(historical, fill_until=hist_end)
        for entry in historical:
            ci = entry.get('carbon_intensity')
            if ci is not None:
                data_points.append(
                    {
                        'timestamp': entry['timestamp'].isoformat(),
                        'value': float(ci),
                        'is_forecast': False,
                    }
                )

    # Forecast data (future)
    if effective_end > now:
        forecast_data = _get_forecast_data(location, 'carbon_intensity')
        forecast_start = max(effective_start, now) if effective_start else now
        sliced = _slice_cached_data(forecast_data, forecast_start, effective_end)
        for point in sliced:
            point_copy = dict(point)
            point_copy['is_forecast'] = True
            data_points.append(point_copy)

    # Deduplicate at boundary — prefer historical (is_forecast=False)
    seen = {}
    deduped = []
    for point in data_points:
        ts = point['timestamp']
        if ts in seen:
            if not point['is_forecast']:
                deduped[seen[ts]] = point
        else:
            seen[ts] = len(deduped)
            deduped.append(point)

    return {
        'location_id': location,
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2/kWh',
        'data': deduped,
    }


if __name__ == '__main__':
    all_predictions = {}

    db_utils.initialize_db()
    data_centres = db_utils.get_all_datacenter_ids(include_inactive=True)

    for dc in data_centres:
        load_pred = generate_next_week_load_prediction(dc)
        print(f'Generated {len(load_pred["data"])} load predictions for {dc}')

        try:
            ci_pred = generate_next_week_carbon_intensity_prediction(dc)
            print(f'Generated {len(ci_pred["data"])} carbon intensity predictions for {dc}')
        except ValueError as exc:
            ci_pred = {'error': str(exc)}
            print(f'Skipping carbon intensity for {dc}: {exc}')

        all_predictions[dc] = {
            'load_prediction': load_pred,
            'carbon_intensity_prediction': ci_pred,
        }

    with open('predictions.json', 'w') as f:
        json.dump(all_predictions, f, indent=2)

    print('Predictions saved to predictions.json')
