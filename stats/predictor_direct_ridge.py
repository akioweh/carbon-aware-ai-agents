"""Direct Ridge predictor for carbon intensity forecasting.

Uses a direct multi-step Ridge regression with weather exogenous features
from Open-Meteo. Predicts carbon intensity at 30-min resolution, upsamples
to 5-min for API compatibility. Greenness is derived from CI.

Ported from benchmark.py's Direct-Ridge model which achieved the best
overall MAE (32.99) in the 18-model benchmark comparison.
"""

import logging
import warnings

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge

warnings.filterwarnings('ignore', module='sklearn')

logger = logging.getLogger('stats.direct_ridge')

# DC → region name and coordinates (inverse of db_utils.UK_REGION_TO_DC)
DC_REGION_MAP = {
    'Data-Center-1': ('London', 51.51, -0.13),
    'Data-Center-2': ('South East England', 51.27, 0.52),
    'Data-Center-3': ('South Yorkshire', 53.38, -1.47),
    'Data-Center-4': ('North West England', 53.48, -2.24),
    'Data-Center-5': ('North East England', 54.97, -1.61),
}

WEATHER_FEATURES = ['wind_speed', 'temperature', 'solar_radiation']


# ── Weather helpers ──────────────────────────────────────────────────────

def _fetch_weather_archive(lat, lon, start_date, end_date):
    """Fetch historical weather from Open-Meteo archive API.

    Returns DataFrame with 30-min timestamps and columns: wind_speed,
    temperature, solar_radiation.  Returns empty DataFrame on failure.
    """
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&hourly=temperature_2m,wind_speed_10m,shortwave_radiation"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get('hourly', {})
        times = hourly.get('time', [])
        if not times:
            return pd.DataFrame()

        hdf = pd.DataFrame({
            'ts': pd.to_datetime(times, utc=True),
            'temperature': hourly.get('temperature_2m', []),
            'wind_speed': hourly.get('wind_speed_10m', []),
            'solar_radiation': hourly.get('shortwave_radiation', []),
        })
        hdf = hdf.set_index('ts').sort_index()

        # Interpolate to 30-min
        full_idx = pd.date_range(hdf.index.min(), hdf.index.max(), freq='30min', tz='UTC')
        hdf = hdf.reindex(full_idx).interpolate(method='time').reset_index()
        hdf.columns = ['ts'] + WEATHER_FEATURES
        return hdf
    except Exception as e:
        logger.warning('Failed to fetch archive weather: %s', e)
        return pd.DataFrame()


def _fetch_weather_forecast(lat, lon):
    """Fetch 7-day weather forecast from Open-Meteo forecast API.

    Returns DataFrame with 30-min timestamps and columns: wind_speed,
    temperature, solar_radiation.  Returns empty DataFrame on failure.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,wind_speed_10m,shortwave_radiation"
        f"&forecast_days=8"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get('hourly', {})
        times = hourly.get('time', [])
        if not times:
            return pd.DataFrame()

        hdf = pd.DataFrame({
            'ts': pd.to_datetime(times, utc=True),
            'temperature': hourly.get('temperature_2m', []),
            'wind_speed': hourly.get('wind_speed_10m', []),
            'solar_radiation': hourly.get('shortwave_radiation', []),
        })
        hdf = hdf.set_index('ts').sort_index()

        # Interpolate to 30-min
        full_idx = pd.date_range(hdf.index.min(), hdf.index.max(), freq='30min', tz='UTC')
        hdf = hdf.reindex(full_idx).interpolate(method='time').reset_index()
        hdf.columns = ['ts'] + WEATHER_FEATURES
        return hdf
    except Exception as e:
        logger.warning('Failed to fetch forecast weather: %s', e)
        return pd.DataFrame()


# ── Feature engineering ──────────────────────────────────────────────────

def build_cyclical_features(timestamps):
    """Build sin/cos features for hour, day-of-week, and minute-of-day."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute
    return pd.DataFrame({
        'hour_sin': np.sin(2 * np.pi * hour / 24),
        'hour_cos': np.cos(2 * np.pi * hour / 24),
        'dow_sin':  np.sin(2 * np.pi * dow / 7),
        'dow_cos':  np.cos(2 * np.pi * dow / 7),
        'min_sin':  np.sin(2 * np.pi * minute_of_day / 1440),
        'min_cos':  np.cos(2 * np.pi * minute_of_day / 1440),
    })


def _build_direct_features(train_ts, train_y, train_origin_ts, test_ts,
                            train_exog=None, test_exog=None):
    """Build feature matrices for direct multi-step forecasting.

    Unlike the benchmark version which uses array indices for horizon h,
    this computes h from actual time deltas in 30-min steps. This handles
    gaps in the observation data without distorting the horizon encoding.

    Parameters
    ----------
    train_ts : array-like of datetime
        Timestamps of training targets.
    train_y : ndarray
        Training target values (carbon intensity).
    train_origin_ts : datetime
        The origin timestamp (last observation) for computing horizons.
    test_ts : array-like of datetime
        Timestamps of prediction targets.
    train_exog, test_exog : ndarray or None
        Exogenous weather features for train/test rows.

    Returns (X_train, y_train, X_test).
    """
    n_test = len(test_ts)
    n_train = len(train_y)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 48
    max_h = min(n_test, 336)

    all_cyc = build_cyclical_features(train_ts).values

    # Precompute origin summary stats for each potential origin point
    origin_last = np.zeros(n_train)
    origin_mean = np.zeros(n_train)
    origin_std = np.zeros(n_train)
    for t in range(min_history, n_train):
        recent = train_y[max(0, t - 47):t + 1]
        origin_last[t] = train_y[t]
        origin_mean[t] = np.mean(recent)
        origin_std[t] = np.std(recent) if len(recent) > 1 else 0

    X_parts = []
    y_parts = []
    for h in range(1, max_h + 1):
        origins = np.arange(min_history, n_train - h)
        if len(origins) == 0:
            continue
        targets = origins + h
        cyc = all_cyc[targets]
        h_col = np.full((len(origins), 1), h / 336.0)
        h2_col = h_col ** 2
        of = np.column_stack([origin_last[origins], origin_mean[origins], origin_std[origins]])
        x = np.column_stack([cyc, h_col, h2_col, of])
        if has_exog:
            x = np.column_stack([x, train_exog[targets]])
        X_parts.append(x)
        y_parts.append(train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    # Build test features using time-based horizon computation
    test_cyc = build_cyclical_features(test_ts).values
    recent = train_y[-48:]
    of_test = np.array([[train_y[-1], np.mean(recent), np.std(recent)]])
    of_test = np.tile(of_test, (n_test, 1))

    # Compute horizon from actual time deltas (30-min steps)
    test_ts_series = pd.Series(test_ts)
    h_vals = ((test_ts_series - train_origin_ts).dt.total_seconds() / 1800.0).values.reshape(-1, 1) / 336.0

    X_test = np.column_stack([test_cyc, h_vals, h_vals ** 2, of_test])
    if has_exog:
        X_test = np.column_stack([X_test, test_exog])

    return X_train, y_train, X_test


# ── Core prediction pipeline ────────────────────────────────────────────

def _predict_carbon_intensity(historical_df, dc_name=None):
    """Run the Direct Ridge pipeline on historical carbon intensity data.

    Parameters
    ----------
    historical_df : DataFrame
        Must have 'timestamp' and 'carbon_intensity' columns.
    dc_name : str or None
        Data center name for fetching region-specific weather.

    Returns
    -------
    DataFrame with columns 'ds' (5-min datetime) and 'yhat' (CI, 0-500).
    """
    df = historical_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Use actual discrete observations — no gap interpolation
    series = df[['timestamp', 'carbon_intensity']].dropna(subset=['carbon_intensity'])
    series = series.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)

    if len(series) < 96:  # need at least ~2 days of 30-min data
        raise ValueError('Not enough carbon intensity data for Direct Ridge (need >= 96 points)')

    train_ts = series['timestamp'].values
    train_y = series['carbon_intensity'].values.astype(float)
    origin_ts = series['timestamp'].iloc[-1]

    # Generate 337 forecast timestamps at 30-min intervals
    n_forecast = 337
    forecast_30min = pd.date_range(
        start=origin_ts + pd.Timedelta(minutes=30),
        periods=n_forecast,
        freq='30min',
    )

    # Fetch weather data (graceful fallback if unavailable)
    train_exog = None
    test_exog = None

    if dc_name and dc_name in DC_REGION_MAP:
        _, lat, lon = DC_REGION_MAP[dc_name]

        # Archive weather for training period
        train_start = series['timestamp'].iloc[0].strftime('%Y-%m-%d')
        train_end = series['timestamp'].iloc[-1].strftime('%Y-%m-%d')
        archive_wx = _fetch_weather_archive(lat, lon, train_start, train_end)

        # Forecast weather for prediction period
        forecast_wx = _fetch_weather_forecast(lat, lon)

        if not archive_wx.empty and not forecast_wx.empty:
            # Merge archive weather with training data (left join)
            train_df = series.copy()
            train_df['ts'] = train_df['timestamp'].dt.round('30min')
            archive_wx['ts'] = archive_wx['ts'].dt.round('30min')
            merged = train_df.merge(archive_wx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
            for feat in WEATHER_FEATURES:
                merged[feat] = merged[feat].fillna(0)

            # Lag-1 shift weather features (use previous step's weather)
            for feat in WEATHER_FEATURES:
                merged[feat] = merged[feat].shift(1).fillna(0)

            train_exog = merged[WEATHER_FEATURES].values

            # Merge forecast weather with test timestamps
            test_df = pd.DataFrame({'ts': forecast_30min})
            test_df['ts'] = test_df['ts'].dt.round('30min')
            forecast_wx['ts'] = forecast_wx['ts'].dt.round('30min')
            test_merged = test_df.merge(forecast_wx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
            for feat in WEATHER_FEATURES:
                test_merged[feat] = test_merged[feat].fillna(0)

            # Lag-1 shift: first forecast step uses last training weather
            last_train_wx = merged[WEATHER_FEATURES].iloc[-1].values
            test_wx = test_merged[WEATHER_FEATURES].values
            test_exog = np.vstack([last_train_wx.reshape(1, -1), test_wx[:-1]])

            logger.info('Using weather exogenous features (%d train, %d test)',
                        len(train_exog), len(test_exog))
        else:
            logger.info('Weather data unavailable, predicting without exogenous features')

    # Build features and train
    train_ts_pd = pd.to_datetime(train_ts)
    test_ts_pd = pd.to_datetime(forecast_30min)

    X_train, y_train, X_test = _build_direct_features(
        train_ts_pd, train_y, origin_ts, test_ts_pd,
        train_exog=train_exog, test_exog=test_exog,
    )

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    preds = np.clip(preds, 0, 500)

    # Upsample 30-min → 5-min via linear interpolation
    fc_series = pd.Series(preds, index=forecast_30min)
    fc_5min = fc_series.resample('5min').interpolate(method='linear')
    fc_5min = fc_5min.iloc[:2016]  # exactly 7 days at 5-min

    yhat = np.clip(fc_5min.values, 0, 500)
    return pd.DataFrame({'ds': fc_5min.index, 'yhat': yhat})


# ── Public API (same signatures as predictor_sarimax.py) ────────────────

def get_next_week_greenness(historical_greenness_df):
    """Predict next-week greenness using Direct Ridge on carbon intensity.

    Args:
        historical_greenness_df: DataFrame with columns
            'timestamp', 'greenness', and optionally 'carbon_intensity'.

    Returns:
        DataFrame with columns 'ds' (datetime), 'yhat' (greenness 0-100),
        and 'ci' (carbon intensity).
    """
    df = historical_greenness_df.copy()

    has_ci = (
        'carbon_intensity' in df.columns
        and df['carbon_intensity'].notna().any()
    )

    if not has_ci:
        # Fall back: derive CI from greenness using inverse formula
        # greenness = 100.0 - ((ci - 50) / 3.5) → ci = (100 - greenness) * 3.5 + 50
        df['carbon_intensity'] = (100.0 - df['greenness']) * 3.5 + 50.0

    # Try to infer DC name from the data for weather fetching
    dc_name = _infer_dc_name(df)

    ci_df = _predict_carbon_intensity(df, dc_name=dc_name)

    # Convert CI → greenness
    ci = ci_df['yhat'].values
    greenness = 100.0 - ((ci - 50) / 3.5)
    greenness = np.clip(greenness, 0, 100)

    result = pd.DataFrame({'ds': ci_df['ds'], 'yhat': greenness, 'ci': ci})
    return result


def get_next_week_carbon_intensity(historical_df):
    """Predict next-week carbon intensity (gCO2/kWh) using Direct Ridge.

    Args:
        historical_df: DataFrame with columns 'timestamp' and 'carbon_intensity'.

    Returns:
        DataFrame with columns 'ds' (datetime) and 'yhat' (gCO2/kWh, 0-500).
    """
    dc_name = _infer_dc_name(historical_df)
    return _predict_carbon_intensity(historical_df, dc_name=dc_name)


def _infer_dc_name(df):
    """Try to infer data center name from DataFrame metadata.

    The predictor.py caller doesn't pass the DC name directly, but we can
    try to detect it. Returns None if not determinable (weather will be
    skipped gracefully).
    """
    # Check if there's a 'location' column (sometimes present)
    if 'location' in df.columns:
        locations = df['location'].dropna().unique()
        if len(locations) == 1 and locations[0] in DC_REGION_MAP:
            return locations[0]
    return None
