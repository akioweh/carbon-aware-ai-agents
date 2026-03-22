#!/usr/bin/env python3
"""
Carbon Intensity Prediction Benchmark

Compares 18 forecasting models across 7 metrics on real UK carbon intensity
data. Model categories:
  - Statistical (7): Ridge, SARIMAX, ARIMA(d=1), Seasonal Naive, Fourier,
    Holt-Winters, Direct-Ridge
  - Direct ML (1): Direct-XGBoost
  - Tree-based (4): Random Forest, XGBoost, CatBoost, LightGBM
  - Transformer (3): Transformer-1K/5K/10K
  - Foundation (1): Chronos-Tiny (zero-shot)
  - Deep forecasting (2): N-BEATS, N-HiTS

Uses lag-1 weather data (wind speed, temperature, solar radiation) from
Open-Meteo as exogenous features where applicable. Supports 7-day and full
backfill training windows. Generates graphs and an auto-generated comparison
report.

Note on generation mix: We considered using lag-1 generation mix (gas, wind,
solar, nuclear, biomass, imports) as exogenous features. However, generation mix
is endogenous — carbon intensity is *computed from* the fuel mix. Providing
test-period generation mix (even lagged by one step) gives models near-perfect
information about the target, inflating accuracy unrealistically. In production,
future generation mix is unknown and would itself need forecasting.

Weather data (wind, temperature, solar radiation) is a true exogenous variable:
it influences carbon intensity indirectly (via renewable generation capacity)
but is independently forecastable. Weather forecasts for 7 days ahead are
readily available from meteorological services, making this a realistic feature
for production deployment.

Usage:
    python benchmark.py                  # run with existing data
    python benchmark.py --backfill 90    # backfill 90 days first, then run
"""

import argparse
import json
import sqlite3
import sys
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.dates import DateFormatter
from sklearn.linear_model import Ridge
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import acf

warnings.filterwarnings('ignore')

# ── Section 0: Config & CLI ─────────────────────────────────────────────

DB_PATH = Path(__file__).parent / 'carbon_intensity.db'
DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
TEST_DAYS = 7

MODEL_NAMES = [
    'Ridge',
    'SARIMAX',
    'ARIMA(d=1)',
    'Seasonal Naive',
    'Fourier',
    'Holt-Winters',
    'Direct-Ridge',
    'Direct-XGBoost',
    'Random Forest',
    'XGBoost',
    'CatBoost',
    'LightGBM',
    'Transformer-1K',
    'Transformer-5K',
    'Transformer-10K',
    'Chronos-Tiny',
    'N-BEATS',
    'N-HiTS',
]

# Tree models run in a separate process (benchmark_trees.py) to avoid
# OpenMP/PyTorch thread pool deadlock. They are excluded from MODEL_RUN_NAMES
# but included in MODEL_NAMES for report/graph generation after merging.
TREE_MODEL_NAMES = {'Random Forest', 'XGBoost', 'CatBoost', 'LightGBM', 'Direct-XGBoost'}
NEW_MODEL_NAMES = {'Chronos-Tiny', 'N-BEATS', 'N-HiTS'}
MODEL_RUN_NAMES = [m for m in MODEL_NAMES if m not in TREE_MODEL_NAMES and m not in NEW_MODEL_NAMES]
TREE_RESULTS_PATH = Path(__file__).parent / 'tree_results.json'
NEW_RESULTS_PATH = Path(__file__).parent / 'new_model_results.json'

MODEL_COLORS = {
    'Ridge': '#F44336',
    'SARIMAX': '#4CAF50',
    'Seasonal Naive': '#9C27B0',
    'Fourier': '#FF9800',
    'Holt-Winters': '#00BCD4',
    'Random Forest': '#795548',
    'XGBoost': '#E91E63',
    'CatBoost': '#3F51B5',
    'LightGBM': '#8BC34A',
    'Transformer-1K': '#607D8B',
    'Transformer-5K': '#009688',
    'Transformer-10K': '#FF5722',
    'ARIMA(d=1)': '#673AB7',
    'Direct-Ridge': '#CDDC39',
    'Direct-XGBoost': '#1B5E20',
    'Chronos-Tiny': '#FF6F00',
    'N-BEATS': '#00695C',
    'N-HiTS': '#AD1457',
}

MODEL_LINESTYLES = {
    'Ridge': '--',
    'SARIMAX': '-.',
    'Seasonal Naive': ':',
    'Fourier': '--',
    'Holt-Winters': '-.',
    'Random Forest': '-',
    'XGBoost': '-',
    'CatBoost': '-',
    'LightGBM': '-',
    'Transformer-1K': '-',
    'Transformer-5K': '-',
    'Transformer-10K': '-',
    'ARIMA(d=1)': '-.',
    'Direct-Ridge': '--',
    'Direct-XGBoost': '--',
    'Chronos-Tiny': '-',
    'N-BEATS': '-',
    'N-HiTS': '-',
}

WEATHER_FEATURES = ['wind_speed', 'temperature', 'solar_radiation']

WEATHER_CACHE_PATH = Path(__file__).parent / 'weather_cache.json'

# Approximate coordinates for UK Carbon Intensity API regions
REGION_COORDS = {
    'London': (51.51, -0.13),
    'South East England': (51.27, 0.52),
    'South Yorkshire': (53.38, -1.47),
    'North West England': (53.48, -2.24),
    'North East England': (54.97, -1.61),
}


def parse_args():
    parser = argparse.ArgumentParser(description='Carbon Intensity Prediction Benchmark')
    parser.add_argument(
        '--backfill', type=int, default=0, help='Backfill N days of data from UK Carbon Intensity API before running'
    )
    return parser.parse_args()


# ── Section 1: Data Loading ─────────────────────────────────────────────


def load_data(db_path: Path) -> pd.DataFrame:
    """Load carbon intensity readings from SQLite."""
    if not db_path.exists():
        print(f'ERROR: Database not found: {db_path}')
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT r.name AS region, cr.timestamp_from AS ts, cr.actual
        FROM carbon_readings cr
        JOIN regions r ON cr.region_id = r.region_id
        WHERE cr.actual IS NOT NULL
    """,
        conn,
    )
    conn.close()

    df['ts'] = pd.to_datetime(df['ts'])
    df = df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
    return df


def fetch_weather_data(regions: list, date_min: str, date_max: str) -> pd.DataFrame:
    """Fetch historical weather data from Open-Meteo archive API.

    Returns DataFrame with columns: region, ts, wind_speed, temperature, solar_radiation.
    Data is hourly from API, interpolated to 30-minute intervals to match carbon data.
    Results are cached in weather_cache.json to avoid repeated API calls.
    """
    import requests

    # Check cache
    if WEATHER_CACHE_PATH.exists():
        try:
            cache = json.loads(WEATHER_CACHE_PATH.read_text())
            if cache.get('date_min') == date_min and cache.get('date_max') == date_max:
                cached_regions = set(cache.get('regions', []))
                if set(regions).issubset(cached_regions):
                    print(f'  Using cached weather data from {WEATHER_CACHE_PATH.name}')
                    wdf = pd.DataFrame(cache['data'])
                    wdf['ts'] = pd.to_datetime(wdf['ts'], utc=True)
                    return wdf[wdf['region'].isin(regions)].reset_index(drop=True)
        except (json.JSONDecodeError, KeyError):
            pass

    all_rows = []
    for region in regions:
        if region not in REGION_COORDS:
            print(f'  WARNING: No coordinates for {region}, skipping weather')
            continue
        lat, lon = REGION_COORDS[region]
        url = (
            f'https://archive-api.open-meteo.com/v1/archive'
            f'?latitude={lat}&longitude={lon}'
            f'&start_date={date_min}&end_date={date_max}'
            f'&hourly=temperature_2m,wind_speed_10m,shortwave_radiation'
        )
        print(f'  Fetching weather for {region} ({lat}, {lon})...')
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            hourly = data.get('hourly', {})
            times = hourly.get('time', [])
            temps = hourly.get('temperature_2m', [])
            winds = hourly.get('wind_speed_10m', [])
            solar = hourly.get('shortwave_radiation', [])

            if not times:
                print(f'    No weather data returned for {region}')
                continue

            # Build hourly DataFrame (Open-Meteo returns UTC times)
            hdf = pd.DataFrame(
                {
                    'ts': pd.to_datetime(times, utc=True),
                    'temperature': temps,
                    'wind_speed': winds,
                    'solar_radiation': solar,
                }
            )
            hdf = hdf.set_index('ts').sort_index()

            # Interpolate to 30-minute intervals
            full_idx = pd.date_range(hdf.index.min(), hdf.index.max(), freq='30min', tz='UTC')
            hdf = hdf.reindex(full_idx).interpolate(method='time').reset_index()
            hdf.columns = ['ts'] + WEATHER_FEATURES
            hdf['region'] = region
            all_rows.append(hdf)
            print(f'    Got {len(hdf)} points ({hdf["ts"].min()} to {hdf["ts"].max()})')
        except Exception as e:
            print(f'    ERROR fetching weather for {region}: {e}')

    if not all_rows:
        return pd.DataFrame()

    weather_df = pd.concat(all_rows, ignore_index=True)

    # Cache results
    cache_data = {
        'date_min': date_min,
        'date_max': date_max,
        'regions': list(set(weather_df['region'])),
        'data': weather_df.to_dict(orient='list'),
    }
    # Convert Timestamps to strings for JSON serialization
    cache_data['data']['ts'] = [str(t) for t in cache_data['data']['ts']]
    WEATHER_CACHE_PATH.write_text(json.dumps(cache_data))
    print(f'  Cached weather data to {WEATHER_CACHE_PATH.name}')

    return weather_df


# ── Section 2: Feature Engineering ───────────────────────────────────────


def build_cyclical_features(timestamps: pd.Series) -> pd.DataFrame:
    """Build sin/cos features for hour, day-of-week, and minute-of-day."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute
    return pd.DataFrame(
        {
            'hour_sin': np.sin(2 * np.pi * hour / 24),
            'hour_cos': np.cos(2 * np.pi * hour / 24),
            'dow_sin': np.sin(2 * np.pi * dow / 7),
            'dow_cos': np.cos(2 * np.pi * dow / 7),
            'min_sin': np.sin(2 * np.pi * minute_of_day / 1440),
            'min_cos': np.cos(2 * np.pi * minute_of_day / 1440),
        }
    )


def build_lag_features(series: np.ndarray, n_lags: int = 48) -> pd.DataFrame:
    """Build lag features and rolling means for tree models."""
    s = pd.Series(series)
    features = {}
    for lag in range(1, n_lags + 1):
        features[f'lag_{lag}'] = s.shift(lag)
    features['rolling_mean_6h'] = s.shift(1).rolling(12, min_periods=1).mean()
    features['rolling_mean_12h'] = s.shift(1).rolling(24, min_periods=1).mean()
    features['rolling_mean_24h'] = s.shift(1).rolling(48, min_periods=1).mean()
    return pd.DataFrame(features)


def build_ml_features(timestamps: pd.Series, values: np.ndarray) -> pd.DataFrame:
    """Combine cyclical + lag features for ML tree models."""
    cyclical = build_cyclical_features(timestamps).reset_index(drop=True)
    lags = build_lag_features(values, n_lags=48).reset_index(drop=True)
    return pd.concat([cyclical, lags], axis=1)


# ── Section 3: Model Definitions ────────────────────────────────────────


def train_predict_ridge(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    X_train = build_cyclical_features(train_ts)
    train_exog = kw.get('train_exog')
    test_exog = kw.get('test_exog')
    if train_exog is not None and test_exog is not None:
        X_train = np.column_stack([X_train.values, train_exog])
    model = Ridge(alpha=1.0)
    model.fit(X_train, train_y)
    X_test = build_cyclical_features(test_ts)
    if train_exog is not None and test_exog is not None:
        X_test = np.column_stack([X_test.values, test_exog])
    preds = np.clip(model.predict(X_test), 0, 500)
    return preds, time.time() - t0


def train_predict_sarimax(train_ts, train_y, test_ts, **kw):
    max_train = 48 * 14  # cap at 14 days
    series = pd.Series(train_y, index=train_ts)
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time').asfreq('30min')
    if len(series) > max_train:
        series = series.iloc[-max_train:]

    t0 = time.time()
    model = SARIMAX(
        series,
        order=(1, 0, 1),
        seasonal_order=(1, 0, 1, 48),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)
    n_test = len(test_ts)
    preds = fit.forecast(steps=n_test)
    preds = np.clip(preds.values, 0, 500)
    return preds, time.time() - t0


def train_predict_arima_d1(train_ts, train_y, test_ts, **kw):
    """ARIMA with first differencing: SARIMAX(1,1,1)(1,0,1,48).

    The key difference from SARIMAX above: d=1 (first differencing) makes the
    series stationary by modeling changes rather than levels. This directly
    addresses persistence in carbon intensity data.
    """
    max_train = 48 * 14  # cap at 14 days
    series = pd.Series(train_y, index=train_ts)
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time').asfreq('30min')
    if len(series) > max_train:
        series = series.iloc[-max_train:]

    t0 = time.time()
    model = SARIMAX(
        series,
        order=(1, 1, 1),
        seasonal_order=(1, 0, 1, 48),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)
    n_test = len(test_ts)
    preds = fit.forecast(steps=n_test)
    preds = np.clip(preds.values, 0, 500)
    return preds, time.time() - t0


def train_predict_seasonal_naive(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    # Repeat the last 7 days (336 half-hour slots) of training data
    period = 48 * 7  # 336
    n_test = len(test_ts)
    if len(train_y) >= period:
        pattern = train_y[-period:]
    else:
        pattern = train_y
    # Tile to cover test length
    repeats = (n_test // len(pattern)) + 1
    preds = np.tile(pattern, repeats)[:n_test]
    return preds, time.time() - t0


def train_predict_fourier(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    # Detect interval in hours
    td = (train_ts.iloc[1] - train_ts.iloc[0]).total_seconds() / 3600.0
    day_period = 24.0 / td
    week_period = 168.0 / td

    def _build_fourier_X(timestamps, ref_start):
        t = (timestamps - ref_start).dt.total_seconds() / 3600.0 / td
        X = [np.ones(len(t)), t.values]
        for k in range(1, 4):  # 3 daily harmonics
            X.append(np.sin(2 * np.pi * k * t.values / day_period))
            X.append(np.cos(2 * np.pi * k * t.values / day_period))
        for k in range(1, 3):  # 2 weekly harmonics
            X.append(np.sin(2 * np.pi * k * t.values / week_period))
            X.append(np.cos(2 * np.pi * k * t.values / week_period))
        return np.column_stack(X)

    ref_start = train_ts.iloc[0]
    X_train = _build_fourier_X(train_ts, ref_start)
    train_exog = kw.get('train_exog')
    test_exog = kw.get('test_exog')
    if train_exog is not None and test_exog is not None:
        X_train = np.column_stack([X_train, train_exog])
    coeffs, _, _, _ = np.linalg.lstsq(X_train, train_y, rcond=None)
    X_test = _build_fourier_X(test_ts, ref_start)
    if train_exog is not None and test_exog is not None:
        X_test = np.column_stack([X_test, test_exog])
    preds = np.clip(X_test @ coeffs, 0, 500)
    return preds, time.time() - t0


def train_predict_holt_winters(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    series = pd.Series(train_y, index=train_ts)
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time').asfreq('30min')

    # Need at least 2 seasonal periods
    sp = 48
    if len(series) < 2 * sp:
        # Fall back to mean prediction
        preds = np.full(len(test_ts), series.mean())
        return preds, time.time() - t0

    model = ExponentialSmoothing(
        series,
        seasonal_periods=sp,
        trend='add',
        seasonal='add',
    )
    fit = model.fit(optimized=True)
    preds = fit.forecast(len(test_ts))
    preds = np.clip(preds.values, 0, 500)
    return preds, time.time() - t0


def train_predict_direct_ridge(train_ts, train_y, test_ts, **kw):
    """Direct multi-step Ridge: single model with horizon as feature.

    Instead of recursive forecasting (predict t+1, feed back, predict t+2...),
    this trains ONE Ridge model that takes the forecast horizon h as a feature.
    Each test point is predicted independently from real historical data —
    no error compounding. Features: cyclical time features of the target
    timestamp, normalized horizon distance, and summary stats of recent history.
    """
    t0 = time.time()
    X, y, X_test = _build_direct_features(
        train_ts,
        train_y,
        test_ts,
        train_exog=kw.get('train_exog'),
        test_exog=kw.get('test_exog'),
    )
    model = Ridge(alpha=1.0)
    model.fit(X, y)
    preds = model.predict(X_test)
    return np.clip(preds, 0, 500), time.time() - t0


def _build_direct_features(train_ts, train_y, test_ts, train_exog=None, test_exog=None):
    """Build feature matrices for direct multi-step forecasting.

    Shared by Direct-Ridge, Direct-XGBoost, etc. Returns (X_train, y_train,
    X_test) where each row is a (cyclical, h, h², origin_summary) vector.
    """
    n_test = len(test_ts)
    n_train = len(train_y)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 48
    max_h = min(n_test, 336)

    all_cyc = build_cyclical_features(train_ts).values

    origin_last = np.zeros(n_train)
    origin_mean = np.zeros(n_train)
    origin_std = np.zeros(n_train)
    for t in range(min_history, n_train):
        recent = train_y[max(0, t - 47) : t + 1]
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
        h2_col = h_col**2
        of = np.column_stack([origin_last[origins], origin_mean[origins], origin_std[origins]])
        x = np.column_stack([cyc, h_col, h2_col, of])
        if has_exog:
            x = np.column_stack([x, train_exog[targets]])
        X_parts.append(x)
        y_parts.append(train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    test_cyc = build_cyclical_features(test_ts).values
    recent = train_y[-48:]
    of_test = np.array([[train_y[-1], np.mean(recent), np.std(recent)]])
    of_test = np.tile(of_test, (n_test, 1))
    h_vals = np.arange(1, n_test + 1).reshape(-1, 1) / 336.0
    X_test = np.column_stack([test_cyc, h_vals, h_vals**2, of_test])
    if has_exog:
        X_test = np.column_stack([X_test, test_exog])

    return X_train, y_train, X_test


def train_predict_direct_xgboost(train_ts, train_y, test_ts, **kw):
    """Direct multi-step XGBoost: same as Direct-Ridge but with gradient-boosted
    trees. No recursive error compounding — each horizon predicted independently.
    """
    from xgboost import XGBRegressor

    t0 = time.time()

    X, y, X_test = _build_direct_features(
        train_ts,
        train_y,
        test_ts,
        train_exog=kw.get('train_exog'),
        test_exog=kw.get('test_exog'),
    )

    # Subsample for large datasets (XGBoost is slower than Ridge)
    max_samples = 500_000
    if len(X) > max_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), max_samples, replace=False)
        X = X[idx]
        y = y[idx]

    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1)
    model.fit(X, y)
    preds = model.predict(X_test)
    return np.clip(preds, 0, 500), time.time() - t0


def _recursive_forecast_tree(model, train_ts, train_y, test_ts, test_y_actual, train_exog=None, test_exog=None):
    """Recursive multi-step forecast for tree models.

    Train once on training set. At each test step t, build lag features
    from training data + the model's own prior predictions (NOT actuals).
    This mirrors production use where future actuals are unavailable.
    """
    n_train = len(train_y)
    n_test = len(test_ts)
    n_lags = 48
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)

    # Start with training actuals; predictions will be appended as we go
    known_values = list(train_y)

    # Build training features
    train_features = build_ml_features(train_ts, train_y)
    # Drop rows with NaN from lag features
    valid_mask = train_features.notna().all(axis=1)
    X_train = train_features[valid_mask].values
    if has_exog:
        X_train = np.column_stack([X_train, train_exog[valid_mask.values]])
    y_train = train_y[valid_mask.values]

    model.fit(X_train, y_train)

    # Predict each test step using training data + own prior predictions
    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        # Build features for this single step
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_cyclical_features(ts_point)

        # Lag features from training actuals + own predictions (no test actuals)
        lag_feats = {}
        for lag in range(1, n_lags + 1):
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = known_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan
        # Rolling means from training actuals + own predictions
        for window, name in [(12, 'rolling_mean_6h'), (24, 'rolling_mean_12h'), (48, 'rolling_mean_24h')]:
            start = max(0, idx - 1 - window + 1)
            end = idx  # exclusive, so up to idx-1
            if end > start:
                lag_feats[name] = np.mean(known_values[start:end])
            else:
                lag_feats[name] = np.nan

        lag_df = pd.DataFrame([lag_feats])
        x_step = pd.concat([cyclical.reset_index(drop=True), lag_df.reset_index(drop=True)], axis=1)
        if has_exog:
            x_step = np.column_stack([x_step.values, test_exog[t : t + 1]])
        else:
            x_step = x_step.values
        pred = model.predict(x_step)[0]
        preds[t] = pred
        known_values.append(pred)  # feed own prediction back, not actual

    return np.clip(preds, 0, 500)


def train_predict_random_forest(train_ts, train_y, test_ts, test_y=None, **kw):
    from sklearn.ensemble import RandomForestRegressor

    t0 = time.time()
    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _recursive_forecast_tree(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_xgboost(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor

    t0 = time.time()
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _recursive_forecast_tree(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_catboost(train_ts, train_y, test_ts, test_y=None, **kw):
    from catboost import CatBoostRegressor

    t0 = time.time()
    model = CatBoostRegressor(iterations=200, depth=6, learning_rate=0.1, random_seed=42, verbose=0)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _recursive_forecast_tree(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_lightgbm(train_ts, train_y, test_ts, test_y=None, **kw):
    import lightgbm as lgb

    t0 = time.time()
    model = lgb.LGBMRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbose=-1, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _recursive_forecast_tree(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def _compute_transformer_d_model(target_params, input_size, n_layers=1, nhead=2):
    """Compute d_model for target param count.

    Per layer: 4d² + 4d (self-attn) + 2*d*4d + 4d + d (FFN) + 4d (norms) = 12d² + 13d
    Plus input proj: I*d + d, output proj: d + 1.
    Total = 12*L*d² + (13*L + I + 2)*d + 1
    """
    import math

    a = 12 * n_layers
    b = 13 * n_layers + input_size + 2
    c = 1 - target_params
    disc = b * b - 4 * a * c
    if disc < 0:
        return nhead
    d_raw = (-b + math.sqrt(disc)) / (2 * a)
    # Try both floor and ceil multiples of nhead, pick closer to target
    d_lo = max(nhead, (int(d_raw) // nhead) * nhead)
    d_hi = d_lo + nhead

    def _params(d):
        return a * d * d + b * d + 1

    if abs(_params(d_hi) - target_params) < abs(_params(d_lo) - target_params):
        return d_hi
    return d_lo


def _build_transformer_model(input_size, d_model, nhead=2, n_layers=1, seq_len=48):
    import math

    import torch
    import torch.nn as nn

    class SinusoidalPE(nn.Module):
        def __init__(self, d_model, max_len):
            super().__init__()
            pe = torch.zeros(max_len, d_model)
            pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer('pe', pe.unsqueeze(0))

        def forward(self, x):
            return x + self.pe[:, : x.size(1)]

    class CarbonTransformer(nn.Module):
        def __init__(self, input_size, d_model, nhead, n_layers, seq_len):
            super().__init__()
            self.input_proj = nn.Linear(input_size, d_model)
            self.pos_enc = SinusoidalPE(d_model, max_len=seq_len)
            enc_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=4 * d_model,
                dropout=0.0,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(enc_layer, num_layers=n_layers)
            self.output_proj = nn.Linear(d_model, 1)

        def forward(self, x):
            x = self.pos_enc(self.input_proj(x))
            x = self.encoder(x)
            return self.output_proj(x[:, -1, :])

    return CarbonTransformer(input_size, d_model, nhead, n_layers, seq_len)


def _recursive_forecast_transformer(train_ts, train_y, test_ts, target_params, train_exog=None, test_exog=None, **kw):
    """Train a small transformer and do recursive multi-step forecasting."""
    import torch
    import torch.nn as nn
    from threadpoolctl import threadpool_limits

    torch.manual_seed(42)

    seq_len = 48
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None
    n_exog = train_exog.shape[1] if has_exog else 0

    # Per-step features: [value, 6 cyclical] + optional exog
    cyc_train = build_cyclical_features(train_ts).values
    cyc_test = build_cyclical_features(test_ts).values

    # Z-score normalize target values
    y_mean = np.mean(train_y)
    y_std = np.std(train_y) + 1e-8
    train_y_norm = (train_y - y_mean) / y_std

    input_size = 7 + n_exog
    d_model = _compute_transformer_d_model(target_params, input_size)

    # Build training feature matrix
    train_feats = np.column_stack([train_y_norm.reshape(-1, 1), cyc_train])
    if has_exog:
        train_feats = np.column_stack([train_feats, train_exog])

    # Sliding windows via unfold — .contiguous() is critical for performance
    feats_tensor = torch.tensor(train_feats, dtype=torch.float32)
    X_tensor = feats_tensor.unfold(0, seq_len, 1).permute(0, 2, 1)[:-1].contiguous()
    y_tensor = torch.tensor(train_y_norm[seq_len:], dtype=torch.float32).unsqueeze(1)

    model = _build_transformer_model(input_size, d_model, seq_len=seq_len)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'[{n_params} params, d={d_model}]', end=' ', flush=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()

    # Limit OpenMP threads to avoid deadlock with tree models' thread pools
    with threadpool_limits(limits=4):
        # Training — 20 epochs, large batches (tiny model converges fast)
        model.train()
        batch_size = min(512, len(X_tensor))
        for epoch in range(20):
            perm = torch.randperm(len(X_tensor))
            for start in range(0, len(X_tensor), batch_size):
                idx = perm[start : start + batch_size]
                xb, yb = X_tensor[idx], y_tensor[idx]
                pred = model(xb)
                loss = loss_fn(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

        # Recursive eval with pre-allocated tensor buffer (no per-step allocations)
        model.eval()
        cyc_test_t = torch.tensor(cyc_test, dtype=torch.float32)
        exog_test_t = torch.tensor(test_exog, dtype=torch.float32) if has_exog else None
        buf = torch.zeros(seq_len + n_test, input_size)
        buf[:seq_len] = feats_tensor[-seq_len:]

        preds = np.zeros(n_test)
        with torch.no_grad():
            for t in range(n_test):
                x_in = buf[t : t + seq_len].unsqueeze(0)  # view, no copy
                pred_norm = model(x_in).item()
                preds[t] = pred_norm * y_std + y_mean
                buf[seq_len + t, 0] = pred_norm
                buf[seq_len + t, 1:7] = cyc_test_t[t]
                if has_exog:
                    buf[seq_len + t, 7:] = exog_test_t[t]

    return np.clip(preds, 0, 500)


def train_predict_transformer_1k(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    preds = _recursive_forecast_transformer(
        train_ts, train_y, test_ts, 1000, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_transformer_5k(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    preds = _recursive_forecast_transformer(
        train_ts, train_y, test_ts, 5000, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_transformer_10k(train_ts, train_y, test_ts, **kw):
    t0 = time.time()
    preds = _recursive_forecast_transformer(
        train_ts, train_y, test_ts, 10000, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


MODEL_FUNCS = {
    'Ridge': train_predict_ridge,
    'SARIMAX': train_predict_sarimax,
    'ARIMA(d=1)': train_predict_arima_d1,
    'Seasonal Naive': train_predict_seasonal_naive,
    'Fourier': train_predict_fourier,
    'Holt-Winters': train_predict_holt_winters,
    'Direct-Ridge': train_predict_direct_ridge,
    'Direct-XGBoost': train_predict_direct_xgboost,
    'Random Forest': train_predict_random_forest,
    'XGBoost': train_predict_xgboost,
    'CatBoost': train_predict_catboost,
    'LightGBM': train_predict_lightgbm,
    'Transformer-1K': train_predict_transformer_1k,
    'Transformer-5K': train_predict_transformer_5k,
    'Transformer-10K': train_predict_transformer_10k,
}


# ── Section 4: Metrics ──────────────────────────────────────────────────


def ljung_box_pvalue(residuals: np.ndarray, n_lags: int = 48) -> float:
    """Ljung-Box test p-value for residual autocorrelation.

    Low p-value (< 0.05) means significant autocorrelation remains (bad).
    High p-value means residuals are consistent with white noise (good).
    Tests up to n_lags (default 48 = 24 hours at 30-min intervals).
    """
    if len(residuals) < n_lags + 1:
        return np.nan
    try:
        result = acorr_ljungbox(residuals, lags=[n_lags], return_df=True)
        return float(result['lb_pvalue'].iloc[0])
    except Exception:
        return np.nan


def max_abs_acf(residuals: np.ndarray, n_lags: int = 48) -> float:
    """Maximum absolute autocorrelation at lags 1 to n_lags.

    Lower is better — a good model leaves no predictable structure.
    Values near 0 mean residuals are white noise.
    """
    if len(residuals) < n_lags + 2:
        return np.nan
    try:
        acf_vals = acf(residuals, nlags=n_lags, fft=True)
        return float(np.max(np.abs(acf_vals[1:])))  # skip lag 0 (always 1.0)
    except Exception:
        return np.nan


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, n_features: int = 0) -> dict:
    """Compute all 7 benchmark metrics."""
    residuals = y_true - y_pred
    n = len(y_true)

    mae = float(np.mean(np.abs(residuals)))
    mse = float(np.mean(residuals**2))
    rmse = float(np.sqrt(mse))

    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        r2 = 0.0
        adj_r2 = 0.0
    else:
        r2 = float(1.0 - ss_res / ss_tot)
        if n - n_features - 1 > 0:
            adj_r2 = float(1.0 - (1.0 - r2) * (n - 1) / (n - n_features - 1))
        else:
            adj_r2 = r2

    lb_pval = ljung_box_pvalue(residuals)
    max_acf = max_abs_acf(residuals)

    return {
        'MAE': mae,
        'MSE': mse,
        'RMSE': rmse,
        'R2': r2,
        'Adj_R2': adj_r2,
        'LjungBox_pval': lb_pval,
        'Max_ACF': max_acf,
    }


# Feature count approximations for adjusted R-squared
MODEL_N_FEATURES = {
    'Ridge': 12,
    'SARIMAX': 6,
    'ARIMA(d=1)': 6,
    'Seasonal Naive': 0,
    'Fourier': 17,
    'Holt-Winters': 3,
    'Direct-Ridge': 14,
    'Direct-XGBoost': 14,
    'Random Forest': 63,
    'XGBoost': 63,
    'CatBoost': 63,
    'LightGBM': 63,
    'Transformer-1K': 1000,
    'Transformer-5K': 5000,
    'Transformer-10K': 10000,
    'Chronos-Tiny': 0,
    'N-BEATS': 0,
    'N-HiTS': 0,
}


# ── Section 5: Experiment Runner ─────────────────────────────────────────


def run_experiment(
    region: str, train_df: pd.DataFrame, test_df: pd.DataFrame, exp_name: str, train_exog=None, test_exog=None
) -> dict:
    """Run statistical + transformer models (tree models run via benchmark_trees.py)."""
    results = {}
    train_ts = train_df['ts'].reset_index(drop=True)
    train_y = train_df['actual'].values
    test_ts = test_df['ts'].reset_index(drop=True)
    test_y = test_df['actual'].values

    for model_name in MODEL_RUN_NAMES:
        print(f'    {model_name}...', end=' ', flush=True)
        func = MODEL_FUNCS[model_name]
        try:
            preds, elapsed = func(
                train_ts=train_ts,
                train_y=train_y,
                test_ts=test_ts,
                test_y=test_y,
                train_exog=train_exog,
                test_exog=test_exog,
            )
            # Ensure prediction length matches test
            if len(preds) != len(test_y):
                min_len = min(len(preds), len(test_y))
                preds = preds[:min_len]
                test_y_eval = test_y[:min_len]
            else:
                test_y_eval = test_y

            metrics = compute_metrics(test_y_eval, preds, n_features=MODEL_N_FEATURES[model_name])
            print(f'MAE={metrics["MAE"]:.2f}  ({elapsed:.2f}s)')
            results[model_name] = {
                'preds': preds,
                'metrics': metrics,
                'time': elapsed,
            }
        except Exception as e:
            print(f'FAILED: {e}')
            results[model_name] = None

    return results


# ── Section 6: Graphs ───────────────────────────────────────────────────


def plot_raw_data(df: pd.DataFrame, regions: list):
    """Plot raw carbon intensity data for all regions."""
    fig, axes = plt.subplots(len(regions), 1, figsize=(16, 3.5 * len(regions)), sharex=True)
    if len(regions) == 1:
        axes = [axes]

    for ax, region in zip(axes, regions):
        rdf = df[df['region'] == region]
        ax.plot(rdf['ts'], rdf['actual'], linewidth=0.6, color='#2196F3')
        ax.set_ylabel('gCO2/kWh')
        ax.set_title(region)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
    fig.suptitle('Raw Carbon Intensity Data by Region', fontsize=14, y=1.01)
    fig.tight_layout()
    path = DOCS_DIR / 'benchmark_raw_data.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


def plot_predictions(all_results: dict, regions: list, window_name: str, test_dfs: dict):
    """Overlay all model predictions on actual for each region."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return
    fig, axes = plt.subplots(len(active_regions), 1, figsize=(18, 4.5 * len(active_regions)), sharex=True)
    if len(active_regions) == 1:
        axes = [axes]

    for ax, region in zip(axes, active_regions):
        res = all_results[region][window_name]
        test = test_dfs[region]
        ax.plot(test['ts'].values, test['actual'].values, linewidth=1.5, color='#2196F3', label='Actual', zorder=10)

        for model_name in MODEL_NAMES:
            if res.get(model_name) is None:
                continue
            r = res[model_name]
            preds = r['preds']
            ts = test['ts'].values[: len(preds)]
            mae = r['metrics']['MAE']
            ax.plot(
                ts,
                preds,
                linewidth=0.9,
                color=MODEL_COLORS[model_name],
                linestyle=MODEL_LINESTYLES[model_name],
                label=f'{model_name} ({mae:.1f})',
                alpha=0.8,
            )

        ax.set_ylabel('gCO2/kWh')
        ax.set_title(region)
        ax.legend(loc='upper right', fontsize=7, ncol=2)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
    wlabel = window_name.replace(' ', '_').lower()
    fig.suptitle(f'Predictions vs Actual — {window_name}', fontsize=14, y=1.01)
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_predictions_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


def plot_zoom_48h(all_results: dict, regions: list, window_name: str, test_dfs: dict):
    """Zoomed 48-hour detail — top 5 models by MAE only."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return

    # Find top 5 models (lowest average MAE across regions)
    model_maes = {m: [] for m in MODEL_NAMES}
    for region in active_regions:
        res = all_results[region][window_name]
        for m in MODEL_NAMES:
            if res.get(m) is not None:
                model_maes[m].append(res[m]['metrics']['MAE'])
    avg_maes = {m: np.mean(v) if v else 1e9 for m, v in model_maes.items()}
    top5 = sorted(avg_maes, key=avg_maes.get)[:5]

    fig, axes = plt.subplots(len(active_regions), 1, figsize=(16, 4 * len(active_regions)), sharex=False)
    if len(active_regions) == 1:
        axes = [axes]

    for ax, region in zip(axes, active_regions):
        res = all_results[region][window_name]
        test = test_dfs[region]
        n_48h = min(96, len(test))  # 48h at 30min intervals

        ax.plot(
            test['ts'].values[:n_48h],
            test['actual'].values[:n_48h],
            linewidth=2,
            color='#2196F3',
            label='Actual',
            zorder=10,
        )

        for model_name in top5:
            if res.get(model_name) is None:
                continue
            r = res[model_name]
            preds = r['preds'][:n_48h]
            ts = test['ts'].values[: len(preds)]
            mae = r['metrics']['MAE']
            ax.plot(
                ts,
                preds,
                linewidth=1.2,
                color=MODEL_COLORS[model_name],
                linestyle=MODEL_LINESTYLES[model_name],
                label=f'{model_name} ({mae:.1f})',
            )

        ax.set_ylabel('gCO2/kWh')
        ax.set_title(f'{region} — First 48 Hours')
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(DateFormatter('%b %d %H:%M'))

    wlabel = window_name.replace(' ', '_').lower()
    fig.suptitle(f'48-Hour Detail — {window_name} (Top 5 Models)', fontsize=14, y=1.01)
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_zoom_48h_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


def plot_heatmap(all_results: dict, regions: list, window_name: str):
    """Metrics heatmap with per-column rank-based coloring.

    Each metric column is ranked independently (1=best, N=worst).
    Green = best rank, red = worst rank. Raw metric values shown as text.
    """
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return

    metric_names = ['MAE', 'MSE', 'RMSE', 'R2', 'Adj_R2', 'LjungBox_pval', 'Max_ACF']
    # Higher is better for these metrics
    higher_is_better = {'R2', 'Adj_R2', 'LjungBox_pval'}
    active_models = []
    data = []

    for model_name in MODEL_NAMES:
        vals = []
        for metric in metric_names:
            region_vals = []
            for region in active_regions:
                res = all_results[region][window_name]
                if res.get(model_name) is not None:
                    v = res[model_name]['metrics'][metric]
                    if np.isfinite(v):
                        region_vals.append(v)
            vals.append(np.mean(region_vals) if region_vals else np.nan)
        if not all(np.isnan(v) for v in vals):
            active_models.append(model_name)
            data.append(vals)

    if not data:
        return

    data_arr = np.array(data)
    n_models = len(active_models)
    n_metrics = len(metric_names)

    # Build rank matrix: per column, rank 1 (best) to N (worst)
    rank_arr = np.full_like(data_arr, np.nan)
    for j in range(n_metrics):
        col = data_arr[:, j]
        valid = np.isfinite(col)
        if not valid.any():
            continue
        # Rank: lower value = rank 1 for lower-is-better, flip for higher-is-better
        vals = col[valid]
        if metric_names[j] in higher_is_better:
            order = np.argsort(-vals)  # descending — highest value gets rank 1
        else:
            order = np.argsort(vals)  # ascending — lowest value gets rank 1
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(vals) + 1)
        rank_arr[valid, j] = ranks

    # Normalize ranks to [0, 1] for colormap: 0 = best (green), 1 = worst (red)
    norm_arr = np.full_like(rank_arr, 0.5)
    for j in range(n_metrics):
        col = rank_arr[:, j]
        valid = np.isfinite(col)
        if valid.sum() > 1:
            norm_arr[valid, j] = (col[valid] - 1) / (valid.sum() - 1)
        elif valid.sum() == 1:
            norm_arr[valid, j] = 0.0

    fig, ax = plt.subplots(figsize=(12, max(4, n_models * 0.7)))
    cmap = plt.cm.RdYlGn_r
    im = ax.imshow(norm_arr, cmap=cmap, aspect='auto', vmin=0, vmax=1)

    ax.set_xticks(range(n_metrics))
    ax.set_xticklabels(metric_names, rotation=45, ha='right', fontsize=9)
    ax.set_yticks(range(n_models))
    ax.set_yticklabels(active_models, fontsize=9)

    # Annotate cells with raw metric values
    for i in range(n_models):
        for j in range(n_metrics):
            val = data_arr[i, j]
            if np.isfinite(val):
                text = f'{val:.2f}' if abs(val) < 100 else f'{val:.0f}'
                # Pick text color based on background brightness
                bg_val = norm_arr[i, j]
                text_color = 'white' if 0.3 < bg_val < 0.7 else 'black'
                ax.text(j, i, text, ha='center', va='center', fontsize=7, color=text_color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Rank (green=best, red=worst)', fontsize=9)
    wlabel = window_name.replace(' ', '_').lower()
    ax.set_title(f'Metrics Heatmap — {window_name} (Rank-Based Coloring)')
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_heatmap_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


def plot_training_comparison(all_results: dict, regions: list, windows: list):
    """Grouped bar chart: MAE per model, comparing training windows."""
    # Gather average MAEs per model per window
    model_window_mae = {w: {} for w in windows}
    for window_name in windows:
        for model_name in MODEL_NAMES:
            maes = []
            for region in regions:
                if region in all_results and window_name in all_results[region]:
                    res = all_results[region][window_name]
                    if res.get(model_name) is not None:
                        maes.append(res[model_name]['metrics']['MAE'])
            if maes:
                model_window_mae[window_name][model_name] = np.mean(maes)

    active_models = [m for m in MODEL_NAMES if any(m in model_window_mae[w] for w in windows)]
    if not active_models:
        return

    x = np.arange(len(active_models))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, window_name in enumerate(windows):
        vals = [model_window_mae[window_name].get(m, 0) for m in active_models]
        offset = (i - (len(windows) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=window_name, color=f'C{i}', alpha=0.8)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.5,
                    f'{val:.1f}',
                    ha='center',
                    va='bottom',
                    fontsize=7,
                )

    ax.set_ylabel('MAE (gCO2/kWh)')
    ax.set_title('MAE by Model — Training Window Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels(active_models, rotation=30, ha='right')
    ax.legend()
    ax.grid(True, axis='y', alpha=0.3)
    fig.tight_layout()
    path = DOCS_DIR / 'benchmark_training_comparison.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


def plot_residuals(all_results: dict, regions: list, window_name: str, test_dfs: dict):
    """Max |ACF| bar chart + residual ACF for top models."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return

    # Average Max_ACF per model (lower is better)
    model_max_acf = {}
    for model_name in MODEL_NAMES:
        vals = []
        for region in active_regions:
            res = all_results[region][window_name]
            if res.get(model_name) is not None:
                v = res[model_name]['metrics']['Max_ACF']
                if np.isfinite(v):
                    vals.append(v)
        if vals:
            model_max_acf[model_name] = np.mean(vals)

    if not model_max_acf:
        return

    # Top 5 models by MAE for ACF subplot
    model_maes = {}
    for model_name in MODEL_NAMES:
        maes = []
        for region in active_regions:
            res = all_results[region][window_name]
            if res.get(model_name) is not None:
                maes.append(res[model_name]['metrics']['MAE'])
        if maes:
            model_maes[model_name] = np.mean(maes)
    top5 = sorted(model_maes, key=model_maes.get)[:5]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Bar chart of Max |ACF| (lower is better — sorted ascending)
    sorted_models = sorted(model_max_acf, key=model_max_acf.get)
    colors = [MODEL_COLORS.get(m, 'gray') for m in sorted_models]
    ax1.barh(range(len(sorted_models)), [model_max_acf[m] for m in sorted_models], color=colors, alpha=0.8)
    ax1.set_yticks(range(len(sorted_models)))
    ax1.set_yticklabels(sorted_models, fontsize=9)
    ax1.set_xlabel('Max |ACF| at lags 1-48 (lower = better)')
    ax1.set_title('Residual Autocorrelation (worst lag)')
    ax1.set_xlim(0, 1)
    ax1.grid(True, axis='x', alpha=0.3)

    # ACF of residuals for top 5 models (use first active region)
    region = active_regions[0]
    res = all_results[region][window_name]
    test_y = test_dfs[region]['actual'].values
    n_lags_acf = min(48, len(test_y) // 2 - 1)
    if n_lags_acf > 2:
        for model_name in top5:
            if res.get(model_name) is None:
                continue
            preds = res[model_name]['preds']
            residuals = test_y[: len(preds)] - preds
            acf_vals = acf(residuals, nlags=n_lags_acf, fft=True)
            ax2.plot(range(n_lags_acf + 1), acf_vals, color=MODEL_COLORS[model_name], label=model_name, linewidth=1.2)
        ax2.axhline(0, color='gray', linewidth=0.5)
        ax2.axhline(1.96 / np.sqrt(len(test_y)), color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        ax2.axhline(-1.96 / np.sqrt(len(test_y)), color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        ax2.set_xlabel('Lag (30-min intervals)')
        ax2.set_ylabel('ACF')
        ax2.set_title(f'Residual ACF — {region}')
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

    wlabel = window_name.replace(' ', '_').lower()
    fig.suptitle(f'Residual Analysis — {window_name}', fontsize=14, y=1.02)
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_residuals_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


# ── Section 7: Report Generation ─────────────────────────────────────────


def generate_report(
    all_results: dict, regions: list, data_info: dict, windows: list, noexog_results: dict = None
) -> str:
    """Generate markdown report from benchmark results."""
    lines = []
    lines.append('# Carbon Intensity Prediction Benchmark')
    lines.append('')
    lines.append('## Overview')
    lines.append('')
    lines.append(
        'This report compares 18 forecasting models (7 statistical + 1 direct ML + 4 tree-based + 3 transformer '
        '+ 1 foundation + 2 deep forecasting) on real UK carbon intensity data (gCO2/kWh). Models '
        'are evaluated on 7 metrics that measure both point accuracy and residual structure. Where '
        'applicable, models use lag-1 weather data (wind speed, temperature, solar radiation) from '
        'Open-Meteo as exogenous features. The benchmark tests different training window sizes '
        'to assess the effect of data volume on prediction quality.'
    )
    lines.append('')

    # Test setup
    lines.append('## Test Setup')
    lines.append('')
    lines.append('| Parameter | Value |')
    lines.append('|-----------|-------|')
    lines.append(f'| **Data source** | `carbon_intensity.db` (UK Carbon Intensity API) |')
    lines.append(f'| **Regions** | {", ".join(regions)} |')
    lines.append(f'| **Date range** | {data_info["date_min"]} to {data_info["date_max"]} |')
    lines.append(f'| **Total readings** | {data_info["total_rows"]} |')
    lines.append(f'| **Frequency** | 30-minute intervals |')
    lines.append(f'| **Test set** | Last {TEST_DAYS} days |')
    for w in windows:
        lines.append(f'| **Training ({w})** | {data_info.get(f"train_info_{w}", "N/A")} |')
    lines.append('')

    # Raw data graph
    lines.append('## Raw Data')
    lines.append('')
    lines.append('![Raw Data](benchmark_raw_data.png)')
    lines.append('')

    # Metrics explanation
    lines.append('## Metrics Explained')
    lines.append('')
    lines.append('| Metric | Purpose |')
    lines.append('|--------|---------|')
    lines.append('| **MAE** | Mean Absolute Error — primary accuracy in gCO2/kWh |')
    lines.append('| **MSE** | Mean Squared Error — penalizes large errors quadratically |')
    lines.append('| **RMSE** | Root MSE — same scale as MAE, sensitive to outliers |')
    lines.append('| **R-squared** | Fraction of variance explained; negative = worse than predicting the mean |')
    lines.append('| **Adjusted R-squared** | R-squared penalized by number of model features |')
    lines.append(
        '| **Ljung-Box p-value** | Ljung-Box test at lag 48 (24h). '
        'High p-value (> 0.05) = residuals consistent with white noise (good). '
        'Low = significant autocorrelation remains (model missed structure) |'
    )
    lines.append(
        '| **Max \\|ACF\\|** | Maximum absolute autocorrelation at lags 1-48. '
        'Lower is better — near 0 means no predictable structure left in residuals |'
    )
    lines.append('')

    # Results per window
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f'## Results: {window_name}')
        lines.append('')

        # Accuracy table
        lines.append('### Accuracy Table')
        lines.append('')
        metric_cols = ['MAE', 'RMSE', 'R2', 'LjungBox_pval', 'Max_ACF']
        header = '| Model | ' + ' | '.join(metric_cols) + ' | Time (s) |'
        sep = '|-------|' + '|'.join(['-------'] * len(metric_cols)) + '|----------|'
        lines.append(header)
        lines.append(sep)

        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]

        for model_name in MODEL_NAMES:
            avg_metrics = {}
            avg_time = []
            for metric in metric_cols:
                vals = []
                for region in active_regions:
                    res = all_results[region][window_name]
                    if res.get(model_name) is not None:
                        v = res[model_name]['metrics'][metric]
                        if np.isfinite(v):
                            vals.append(v)
                avg_metrics[metric] = np.mean(vals) if vals else np.nan
            for region in active_regions:
                res = all_results[region][window_name]
                if res.get(model_name) is not None:
                    avg_time.append(res[model_name]['time'])

            vals_str = []
            for metric in metric_cols:
                v = avg_metrics[metric]
                if np.isnan(v):
                    vals_str.append('N/A')
                elif abs(v) < 10:
                    vals_str.append(f'{v:.3f}')
                else:
                    vals_str.append(f'{v:.2f}')

            t_str = f'{np.mean(avg_time):.2f}' if avg_time else 'N/A'
            row = f'| {model_name} | ' + ' | '.join(vals_str) + f' | {t_str} |'
            lines.append(row)

        lines.append('')
        lines.append(
            f'*Averaged across {len(active_regions)} regions. Lower MAE/RMSE/Max_ACF is better. Higher R2/LjungBox_pval is better.*'
        )
        lines.append('')

        # Graphs
        lines.append('### Predictions vs Actual')
        lines.append('')
        lines.append(f'![Predictions {window_name}](benchmark_predictions_{wlabel}.png)')
        lines.append('')
        lines.append('### Zoomed 48-Hour Detail')
        lines.append('')
        lines.append(f'![48h Detail {window_name}](benchmark_zoom_48h_{wlabel}.png)')
        lines.append('')

    # Training comparison
    if len(windows) > 1:
        lines.append('## Training Data Volume Comparison')
        lines.append('')
        lines.append('![Training Comparison](benchmark_training_comparison.png)')
        lines.append('')
        lines.append(
            'This chart compares MAE across training windows. Models that improve '
            'significantly with more data have learned meaningful temporal patterns. '
            'Models that stay flat or get worse may be overfitting or are insensitive '
            'to training volume.'
        )
        lines.append('')

    # Residual analysis
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f'## Residual Analysis — {window_name}')
        lines.append('')
        lines.append(f'![Residuals {window_name}](benchmark_residuals_{wlabel}.png)')
        lines.append('')
        lines.append(
            "**Max |ACF|** near 0 means the model's residuals look like white noise —"
            'it captured all the periodic structure in the data. Higher values suggest the model'
            'missed recurring patterns. The **ACF plot** shows autocorrelation in residuals;'
            ' significant spikes at lag 48 (1 day) or lag 336 (1 week) indicate unmodelled seasonality.'
        )
        lines.append('')

    # Heatmaps
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f'## Metrics Heatmap — {window_name}')
        lines.append('')
        lines.append(f'![Heatmap {window_name}](benchmark_heatmap_{wlabel}.png)')
        lines.append('')

    # Model details
    lines.append('## Model Details')
    lines.append('')
    lines.append('### Statistical Models')
    lines.append('')
    lines.append(
        '- **Ridge Regression**: Ridge(alpha=1.0) with cyclical sin/cos features for hour, '
        'day-of-week, minute-of-day. Fast, interpretable, but limited to capturing smooth seasonality.'
    )
    lines.append(
        '- **SARIMAX**: SARIMAX(1,0,1)(1,0,1,48) with training capped at 14 days. '
        'Captures autoregressive momentum and seasonal patterns. Uses d=0 (no differencing). Slower to fit.'
    )
    lines.append(
        '- **ARIMA(d=1)**: SARIMAX(1,1,1)(1,0,1,48) — same as SARIMAX but with first differencing '
        '(d=1). Models changes rather than levels, making the series stationary. Addresses '
        'the persistence structure that d=0 misses.'
    )
    lines.append(
        '- **Seasonal Naive**: Repeats the last 7 days of training data. Zero parameters, '
        'instant. Strong baseline when weekly patterns dominate.'
    )
    lines.append(
        '- **Fourier Regression**: 3 daily + 2 weekly harmonics solved via OLS (numpy.linalg.lstsq). '
        "Prophet's core math without the overhead."
    )
    lines.append(
        '- **Holt-Winters**: Triple exponential smoothing with additive trend and seasonality '
        '(seasonal_periods=48). Struggles with noisy, multi-seasonal data.'
    )
    lines.append(
        '- **Direct-Ridge**: Direct multi-step Ridge regression. Instead of recursive forecasting '
        '(predict t+1, feed back, repeat), trains a single Ridge model with the forecast horizon h '
        'as a feature. Each test point is predicted independently from real historical data — '
        'no error compounding. Features: cyclical time features, h/h-squared, recent history summary.'
    )
    lines.append(
        '- **Direct-XGBoost**: Same direct multi-step approach as Direct-Ridge but using '
        'XGBRegressor(n_estimators=200, max_depth=6, lr=0.1). Gradient-boosted trees can '
        'capture nonlinear horizon-dependent patterns that Ridge cannot. Subsampled to 500K '
        'training pairs for efficiency.'
    )
    lines.append('')
    lines.append('### ML Tree-Based Models')
    lines.append('')
    lines.append(
        '- **Random Forest**: RF(n_estimators=200, max_depth=15) with lag + cyclical features. '
        'Walk-forward evaluation using actual history for lag computation.'
    )
    lines.append(
        '- **XGBoost**: XGB(n_estimators=200, max_depth=6, lr=0.1). Gradient-boosted trees '
        'with the same feature set and walk-forward evaluation.'
    )
    lines.append(
        '- **CatBoost**: CB(iterations=200, depth=6, lr=0.1). Ordered boosting with '
        'symmetric trees. Walk-forward evaluation.'
    )
    lines.append(
        '- **LightGBM**: LGBM(n_estimators=200, max_depth=6, lr=0.1). Histogram-based '
        'gradient boosting. Walk-forward evaluation.'
    )
    lines.append('')
    lines.append('### Transformer Models')
    lines.append('')
    lines.append(
        '- **Transformer-1K**: Small transformer encoder (~1K parameters). '
        'Input projection + sinusoidal positional encoding + 1-layer TransformerEncoder '
        '(dim_feedforward=4*d_model, no dropout) + linear head on last position. '
        'Trained on sliding windows (seq_len=48, 50 epochs, Adam lr=0.001, grad clip=1.0). '
        'Recursive multi-step forecasting with Z-score normalization.'
    )
    lines.append('- **Transformer-5K**: Same architecture (~5K parameters), larger d_model.')
    lines.append('- **Transformer-10K**: Same architecture (~10K parameters), largest d_model.')
    lines.append('')
    lines.append('### Foundation Models')
    lines.append('')
    lines.append(
        "- **Chronos-Tiny**: Amazon's pre-trained time series foundation model (Chronos-T5-Tiny, "
        '~8M parameters). Zero-shot forecasting — no training on local data. Tokenizes the '
        'historical series and generates predictions autoregressively using a T5 language model '
        'backbone trained on millions of diverse time series. Median of 20 sample trajectories.'
    )
    lines.append('')
    lines.append('### Deep Forecasting Models')
    lines.append('')
    lines.append(
        '- **N-BEATS**: Neural Basis Expansion Analysis for Time Series (Oreshkin et al., 2019). '
        'Direct multi-horizon forecasting — predicts all h steps at once, avoiding recursive error '
        'compounding. Decomposes forecast into interpretable trend and seasonality basis functions. '
        'Trained from scratch on local data (300 steps, input_size=96).'
    )
    lines.append(
        '- **N-HiTS**: Neural Hierarchical Interpolation for Time Series (Challu et al., 2022). '
        'Improved N-BEATS with multi-rate signal sampling — uses hierarchical interpolation at '
        'different temporal scales. Direct multi-horizon output, no recursive forecasting. '
        'Trained from scratch (300 steps, input_size=96).'
    )
    lines.append('')

    # Key findings
    lines.append('## Key Findings')
    lines.append('')

    # Compute best model per window
    for window_name in windows:
        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
        best_mae = {}
        for model_name in MODEL_NAMES:
            maes = []
            for region in active_regions:
                res = all_results[region][window_name]
                if res.get(model_name) is not None:
                    maes.append(res[model_name]['metrics']['MAE'])
            if maes:
                best_mae[model_name] = np.mean(maes)

        if best_mae:
            sorted_models = sorted(best_mae, key=best_mae.get)
            lines.append(f'**{window_name}** — Top 3 by MAE:')
            for i, m in enumerate(sorted_models[:3]):
                lines.append(f'{i + 1}. {m}: MAE = {best_mae[m]:.2f} gCO2/kWh')
            lines.append('')

    lines.append(
        '**Residual structure**: Models with high Ljung-Box p-values and low Max |ACF| '
        "leave no predictable structure in their residuals — they've captured the signal fully. "
        'Tree-based models with lag features tend to score well here because they can '
        'replicate recent patterns.'
    )
    lines.append('')
    lines.append(
        '**Training volume effect**: More training data generally helps autoregressive '
        'models (SARIMAX, tree models) but has diminishing returns for models that only '
        'use time-of-day features (Ridge, Fourier).'
    )
    lines.append('')
    lines.append(
        '**Speed/accuracy tradeoffs**: Ridge and Fourier are near-instant. SARIMAX and '
        'tree models take seconds. For production use, the best model depends on whether '
        'you need sub-second predictions or can afford batch computation.'
    )
    lines.append('')

    # Methodology
    lines.append('## Methodology Notes')
    lines.append('')
    lines.append(
        '- **Walk-forward evaluation** for tree models: trained once, then at each test step '
        'lag features are built from actual historical values (not predictions). This simulates '
        'production usage where recent actuals are available.'
    )
    lines.append(
        '- **SARIMAX training cap**: Limited to 14 days to avoid excessive fit time. '
        'This is consistent with the production predictor.'
    )
    lines.append(
        '- **No hyperparameter tuning**: All models use reasonable defaults. Results could '
        'improve with tuning, but the comparison is fair since no model was optimized.'
    )
    lines.append(
        '- **Ljung-Box test**: Tests whether residual autocorrelations at lags 1-48 are '
        'jointly zero. A p-value > 0.05 means residuals are consistent with white noise. '
        'This directly measures whether the model left predictable structure.'
    )
    lines.append(
        '- **Max |ACF|**: The worst-case autocorrelation at any single lag from 1 to 48. '
        'A complementary diagnostic to Ljung-Box — pinpoints the lag where the most '
        'structure remains.'
    )
    lines.append(
        '- **Weather features (exogenous)**: Lag-1 weather data (wind speed at 10m, temperature '
        'at 2m, shortwave solar radiation) from the Open-Meteo archive API is used as exogenous '
        'features for Ridge, Fourier, tree-based, and transformer models. SARIMAX, Seasonal Naive, '
        'and Holt-Winters do not support exogenous inputs. The lag-1 shift ensures no data '
        "leakage — at each prediction step, only the previous step's weather is visible. "
        'Weather is a true exogenous variable: it influences carbon intensity indirectly '
        '(via renewable generation capacity) but is independently forecastable.\n'
        '- **Why not generation mix?**: We considered using lag-1 generation mix (gas, wind, solar, '
        'nuclear, biomass, imports) as features. However, carbon intensity is directly *computed from* '
        'the fuel mix — providing test-period generation mix data essentially provides the answer. '
        'In production, future generation mix is unknown and would itself need forecasting, making '
        'it an invalid exogenous feature for a forecasting benchmark.'
    )
    lines.append(
        '- **Direct multi-step forecasting**: Direct-Ridge trains a single model with the forecast '
        'horizon h as a feature. Each test point is predicted independently from real historical '
        'data — no recursive error compounding. This contrasts with recursive approaches (tree models, '
        'transformers) where prediction errors feed forward into subsequent steps.'
    )
    lines.append(
        '- **Foundation model (Chronos)**: Zero-shot inference — no training on local data. '
        'The model was pre-trained on hundreds of millions of time series from diverse domains. '
        'Uses the smallest variant (Chronos-T5-Tiny, ~8M params) for benchmarking speed.'
    )
    lines.append(
        '- **N-BEATS / N-HiTS**: Direct multi-horizon deep learning models from the neuralforecast '
        'library. They predict all h steps simultaneously (no recursive step), using learned basis '
        'expansions. Require input_size + h training points, so may fail on short training windows.'
    )
    lines.append('')

    # Ablation: with vs without exogenous features
    if noexog_results:
        lines.append('## Ablation: With vs Without Weather Features')
        lines.append('')
        lines.append(
            'To measure the impact of weather features, all models were run both with '
            'and without lag-1 weather data (wind speed, temperature, solar radiation). '
            "Models that don't use exogenous features (SARIMAX, Seasonal Naive, Holt-Winters) "
            'are unchanged.'
        )
        lines.append('')

        for window_name in windows:
            lines.append(f'### {window_name}')
            lines.append('')
            lines.append('| Model | MAE (with weather) | MAE (no weather) | Delta |')
            lines.append('|-------|-------------------|-----------------|-------|')

            active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
            noexog_regions = [r for r in regions if r in noexog_results and window_name in noexog_results[r]]

            for model_name in MODEL_NAMES:
                # With weather
                maes_with = []
                for region in active_regions:
                    res = all_results[region][window_name]
                    if res.get(model_name) is not None:
                        maes_with.append(res[model_name]['metrics']['MAE'])
                # Without weather
                maes_without = []
                for region in noexog_regions:
                    res = noexog_results[region][window_name]
                    if res.get(model_name) is not None:
                        maes_without.append(res[model_name]['metrics']['MAE'])

                if maes_with and maes_without:
                    avg_with = np.mean(maes_with)
                    avg_without = np.mean(maes_without)
                    delta = avg_with - avg_without
                    sign = '+' if delta > 0 else ''
                    lines.append(f'| {model_name} | {avg_with:.2f} | {avg_without:.2f} | {sign}{delta:.2f} |')
                elif maes_with:
                    lines.append(f'| {model_name} | {np.mean(maes_with):.2f} | — | — |')

            lines.append('')

        lines.append(
            'Negative delta means weather features helped (lower MAE). '
            "Models that don't accept exogenous features show no change."
        )
        lines.append('')

    return '\n'.join(lines)


# ── Section 8: Main ─────────────────────────────────────────────────────


def main():
    args = parse_args()

    # Optionally backfill
    if args.backfill > 0:
        print(f'Backfilling {args.backfill} days of data...')
        from carbon_collector import backfill, init_database

        conn = init_database(DB_PATH)
        backfill(conn, args.backfill)
        conn.close()
        print()

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f'Regions: {regions}')
    print(f'Date range: {df["ts"].min()} -> {df["ts"].max()}')
    print(f'Total rows: {len(df)}')

    total_days = (df['ts'].max() - df['ts'].min()).days
    print(f'Total span: {total_days} days')

    if total_days < 14:
        print(
            f'\nWARNING: Only {total_days} days of data. Need >= 14 days for meaningful '
            'full backfill experiment. Use --backfill N to collect more data.'
        )

    # Fetch weather data (exogenous features)
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print('\nFetching weather data...')
    weather_df = fetch_weather_data(regions, date_min, date_max)
    has_weather = len(weather_df) > 0
    if has_weather:
        print(f'Weather data: {len(weather_df)} points across {weather_df["region"].nunique()} regions')
    else:
        print('WARNING: No weather data available — running without exogenous features')

    # Determine training windows
    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)
    short_train_start = split_date - pd.Timedelta(days=7)

    windows = [('7-day', short_train_start)]
    if total_days > 14:
        windows.append(('Full backfill', None))

    # Data info for report
    data_info = {
        'date_min': str(df['ts'].min()),
        'date_max': str(df['ts'].max()),
        'total_rows': len(df),
    }

    # Ensure docs dir exists
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Plot raw data
    print('\nGenerating raw data plot...')
    plot_raw_data(df, regions)

    # Run experiments
    all_results = {}
    test_dfs = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f'\n{region}: no test data, skipping')
            continue

        test_dfs[region] = test
        all_results[region] = {}

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

            if len(train) < 48:
                print(f'\n{region} [{window_name}]: insufficient training data ({len(train)} points), skipping')
                continue

            train_days = (train['ts'].max() - train['ts'].min()).days
            data_info[f'train_info_{window_name}'] = f'{len(train)} points ({train_days} days)'
            print(f'\n{"=" * 60}')
            print(f'  {region} [{window_name}]: train={len(train)} ({train_days}d), test={len(test)}')
            print(f'{"=" * 60}')

            # Build lag-1 exogenous features from weather data
            train_exog = None
            test_exog = None
            if has_weather:
                rwx = weather_df[weather_df['region'] == region].sort_values('ts')
                if len(rwx) > 0:
                    combined = pd.concat([train, test]).reset_index(drop=True)
                    merged = combined.merge(rwx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
                    # Interpolate any gaps in weather data
                    merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].interpolate(method='linear')
                    # Lag-1: at each step, model sees previous step's weather
                    for feat in WEATHER_FEATURES:
                        merged[feat] = merged[feat].shift(1)
                    merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].fillna(0)
                    n_train = len(train)
                    train_exog = merged[WEATHER_FEATURES].iloc[:n_train].values
                    test_exog = merged[WEATHER_FEATURES].iloc[n_train:].values

            all_results[region][window_name] = run_experiment(
                region,
                train,
                test,
                window_name,
                train_exog=train_exog,
                test_exog=test_exog,
            )

    # ── Ablation: run without exogenous features ──
    print('\n' + '=' * 70)
    print('  ABLATION: Running models WITHOUT exogenous weather features')
    print('=' * 70)
    noexog_results = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)
        if len(test) == 0:
            continue
        noexog_results[region] = {}

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
            if len(train) < 48:
                continue

            train_days = (train['ts'].max() - train['ts'].min()).days
            print(f'\n  {region} [{window_name}] (no exog): train={len(train)} ({train_days}d), test={len(test)}')

            noexog_results[region][window_name] = run_experiment(
                region,
                train,
                test,
                window_name,
                train_exog=None,
                test_exog=None,
            )

    # Merge no-exog tree results
    noexog_tree_path = Path(__file__).parent / 'tree_results_noexog.json'
    if noexog_tree_path.exists():
        print('\nMerging no-exog tree results...')
        tree_data = json.loads(noexog_tree_path.read_text())
        for region in tree_data:
            if region not in noexog_results:
                noexog_results[region] = {}
            for window_name in tree_data[region]:
                if window_name not in noexog_results[region]:
                    noexog_results[region][window_name] = {}
                for model_name, res in tree_data[region][window_name].items():
                    if res is not None:
                        res['preds'] = np.array(res['preds'])
                        noexog_results[region][window_name][model_name] = res

    # Merge tree model results (from benchmark_trees.py)
    if TREE_RESULTS_PATH.exists():
        print('\nMerging tree model results from tree_results.json...')
        tree_data = json.loads(TREE_RESULTS_PATH.read_text())
        for region in tree_data:
            if region not in all_results:
                all_results[region] = {}
            for window_name in tree_data[region]:
                if window_name not in all_results[region]:
                    all_results[region][window_name] = {}
                for model_name, res in tree_data[region][window_name].items():
                    if res is not None:
                        res['preds'] = np.array(res['preds'])
                        all_results[region][window_name][model_name] = res
                        print(f'    {region}/{window_name}/{model_name}: MAE={res["metrics"]["MAE"]:.2f}')
    else:
        print(
            f'\nNOTE: No tree results found ({TREE_RESULTS_PATH.name}). '
            'Run benchmark_trees.py first to include tree models.'
        )

    # Merge new model results (from benchmark_new_models.py)
    if NEW_RESULTS_PATH.exists():
        print('\nMerging new model results from new_model_results.json...')
        new_data = json.loads(NEW_RESULTS_PATH.read_text())
        for region in new_data:
            if region not in all_results:
                all_results[region] = {}
            for window_name in new_data[region]:
                if window_name not in all_results[region]:
                    all_results[region][window_name] = {}
                for model_name, res in new_data[region][window_name].items():
                    if res is not None:
                        res['preds'] = np.array(res['preds'])
                        all_results[region][window_name][model_name] = res
                        print(f'    {region}/{window_name}/{model_name}: MAE={res["metrics"]["MAE"]:.2f}')
        # New models (Chronos, N-BEATS, N-HiTS) don't use exog — copy into noexog_results
        for region in new_data:
            if region not in noexog_results:
                noexog_results[region] = {}
            for window_name in new_data[region]:
                if window_name not in noexog_results[region]:
                    noexog_results[region][window_name] = {}
                for model_name, res in new_data[region][window_name].items():
                    if res is not None:
                        noexog_results[region][window_name][model_name] = {
                            'preds': np.array(res['preds']),
                            'metrics': res['metrics'],
                            'time': res['time'],
                        }
    else:
        print(
            f'\nNOTE: No new model results found ({NEW_RESULTS_PATH.name}). '
            'Run benchmark_new_models.py first to include Chronos/N-BEATS/N-HiTS.'
        )

    # Generate graphs
    window_names = [w[0] for w in windows]
    print('\nGenerating graphs...')

    for window_name in window_names:
        plot_predictions(all_results, regions, window_name, test_dfs)
        plot_zoom_48h(all_results, regions, window_name, test_dfs)
        plot_heatmap(all_results, regions, window_name)
        plot_residuals(all_results, regions, window_name, test_dfs)

    if len(window_names) > 1:
        plot_training_comparison(all_results, regions, window_names)

    # Generate report
    print('\nGenerating report...')
    report = generate_report(all_results, regions, data_info, window_names, noexog_results=noexog_results)
    report_path = DOCS_DIR / 'comparison_report.md'
    report_path.write_text(report)
    print(f'  Saved: {report_path}')

    # Summary
    print('\n' + '=' * 70)
    print('BENCHMARK COMPLETE')
    print('=' * 70)

    for window_name in window_names:
        print(f'\n--- {window_name} ---')
        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
        model_maes = {}
        for model_name in MODEL_NAMES:
            maes = []
            for region in active_regions:
                res = all_results[region][window_name]
                if res.get(model_name) is not None:
                    maes.append(res[model_name]['metrics']['MAE'])
            if maes:
                model_maes[model_name] = np.mean(maes)

        if model_maes:
            sorted_models = sorted(model_maes, key=model_maes.get)
            for i, m in enumerate(sorted_models):
                marker = ' <-- best' if i == 0 else ''
                print(f'  {i + 1:2d}. {m:<20s} MAE={model_maes[m]:6.2f}{marker}')

    print(f'\nReport: {DOCS_DIR / "comparison_report.md"}')
    print(f'Graphs: {DOCS_DIR}/benchmark_*.png')


if __name__ == '__main__':
    main()
