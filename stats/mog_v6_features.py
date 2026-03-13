#!/usr/bin/env python3
"""
v6 Feature Engineering Module — shared by all v6 models.

Feature groups:
  1. Fourier temporal (12): 4 daily + 2 weekly harmonics
  2. Horizon (4): h_norm, h², log(h), sqrt(h)
  3. Origin summary (8): last, mean/std at 48h & 168h, range_48, zscore, trend
  4. Weather raw (11): lag-1 shifted from Open-Meteo
  5. Weather engineered (5): wind_power, wind_ramp, pressure_change, solar_clearness, temp_dev
  6. Interactions (6): physically motivated cross-terms (Ridge-only)
  7. Calendar (1): is_weekend

Total: 47 features (Ridge/MLP), 41 features (trees, drop interactions)
"""

import json
import sqlite3
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')

DB_PATH = Path(__file__).parent / 'carbon_intensity.db'
WEATHER_CACHE = Path(__file__).parent / 'weather_cache_mog.json'
TEST_DAYS = 7
HORIZON = TEST_DAYS * 48  # 336

REGION_COORDS = {
    'London':              (51.51, -0.13),
    'South East England':  (51.27,  0.52),
    'South Yorkshire':     (53.38, -1.47),
    'North West England':  (53.48, -2.24),
    'North East England':  (54.97, -1.61),
}

WEATHER_COLS = [
    'temperature', 'wind_speed_10m', 'wind_speed_100m', 'wind_gusts',
    'wind_direction', 'shortwave_radiation', 'direct_radiation',
    'diffuse_radiation', 'cloud_cover', 'humidity', 'pressure'
]

WEATHER_VARS_API = (
    'temperature_2m,wind_speed_10m,wind_speed_100m,wind_gusts_10m,'
    'wind_direction_10m,shortwave_radiation,direct_radiation,'
    'diffuse_radiation,cloud_cover,relative_humidity_2m,surface_pressure'
)


# ── Data Loading ──────────────────────────────────────────────────────────

def load_data():
    """Load carbon intensity readings from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT r.name AS region, cr.timestamp_from AS ts, cr.actual
        FROM carbon_readings cr
        JOIN regions r ON cr.region_id = r.region_id
        WHERE cr.actual IS NOT NULL
    """, conn)
    conn.close()
    df['ts'] = pd.to_datetime(df['ts'])
    df = df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
    return df


def load_weather(regions, date_min, date_max):
    """Load weather from cache or fetch from Open-Meteo archive API."""
    if WEATHER_CACHE.exists():
        cache = json.loads(WEATHER_CACHE.read_text())
        if cache.get('date_min') == date_min and cache.get('date_max') == date_max:
            wdf = pd.DataFrame(cache['data'])
            wdf['ts'] = pd.to_datetime(wdf['ts'], utc=True)
            return wdf[wdf['region'].isin(regions)].reset_index(drop=True)

    import requests
    all_rows = []
    for region in regions:
        lat, lon = REGION_COORDS[region]
        url = (f"https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}"
               f"&start_date={date_min}&end_date={date_max}"
               f"&hourly={WEATHER_VARS_API}")
        print(f"  Fetching weather for {region}...")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        hourly = resp.json().get('hourly', {})
        hdf = pd.DataFrame({
            'ts': pd.to_datetime(hourly['time'], utc=True),
            'temperature': hourly.get('temperature_2m', []),
            'wind_speed_10m': hourly.get('wind_speed_10m', []),
            'wind_speed_100m': hourly.get('wind_speed_100m', []),
            'wind_gusts': hourly.get('wind_gusts_10m', []),
            'wind_direction': hourly.get('wind_direction_10m', []),
            'shortwave_radiation': hourly.get('shortwave_radiation', []),
            'direct_radiation': hourly.get('direct_radiation', []),
            'diffuse_radiation': hourly.get('diffuse_radiation', []),
            'cloud_cover': hourly.get('cloud_cover', []),
            'humidity': hourly.get('relative_humidity_2m', []),
            'pressure': hourly.get('surface_pressure', []),
        }).set_index('ts').sort_index()
        full_idx = pd.date_range(hdf.index.min(), hdf.index.max(), freq='30min', tz='UTC')
        hdf = hdf.reindex(full_idx).interpolate(method='time').reset_index()
        hdf.columns = ['ts'] + WEATHER_COLS
        hdf['region'] = region
        all_rows.append(hdf)
    wdf = pd.concat(all_rows, ignore_index=True)
    cache_data = {'date_min': date_min, 'date_max': date_max,
                  'regions': list(set(wdf['region'])),
                  'data': wdf.to_dict(orient='list')}
    cache_data['data']['ts'] = [str(t) for t in cache_data['data']['ts']]
    WEATHER_CACHE.write_text(json.dumps(cache_data))
    return wdf


def prepare_region(df, wdf, region):
    """Prepare train/test split and weather for one region."""
    rdf = df[df['region'] == region].copy()
    rdf = rdf.set_index('ts').sort_index()
    rdf = rdf[~rdf.index.duplicated(keep='first')]
    rdf['actual'] = pd.to_numeric(rdf['actual'], errors='coerce')
    full_idx = pd.date_range(rdf.index.min(), rdf.index.max(), freq='30min')
    rdf = rdf.reindex(full_idx)
    rdf['actual'] = rdf['actual'].interpolate(method='time')

    n_test = TEST_DAYS * 48
    train = rdf.iloc[:-n_test]
    test = rdf.iloc[-n_test:]

    rwdf = wdf[wdf['region'] == region].copy()
    train_weather, test_weather = None, None
    if not rwdf.empty:
        rwdf = rwdf.set_index('ts').sort_index()
        rwdf = rwdf[~rwdf.index.duplicated(keep='first')]
        train_w = rwdf.reindex(train.index).fillna(0)[WEATHER_COLS].values
        test_w = rwdf.reindex(test.index).fillna(0)[WEATHER_COLS].values
        train_weather = np.vstack([train_w[:1], train_w[:-1]])
        test_weather = np.vstack([train_w[-1:], test_w[:-1]])

    return (pd.Series(train.index), train['actual'].values.astype(float),
            pd.Series(test.index), test['actual'].values.astype(float),
            train_weather, test_weather, train.index, test.index)


# ── Feature Builders ──────────────────────────────────────────────────────

def build_fourier(ts):
    """12 Fourier features: 4 daily harmonics + 2 weekly harmonics."""
    t_day = (ts.dt.hour + ts.dt.minute / 60.0) / 24.0
    t_week = (ts.dt.dayofweek + t_day)

    feats = []
    for k in range(1, 5):
        feats.append(np.sin(2 * np.pi * k * t_day))
        feats.append(np.cos(2 * np.pi * k * t_day))
    for k in range(1, 3):
        feats.append(np.sin(2 * np.pi * k * t_week / 7.0))
        feats.append(np.cos(2 * np.pi * k * t_week / 7.0))
    return np.column_stack(feats)


def build_horizon(n_test, max_h=336):
    """4 horizon features for test points."""
    h = np.arange(1, n_test + 1)
    h_norm = h / max_h
    return np.column_stack([
        h_norm,
        h_norm ** 2,
        np.log(h + 1) / np.log(max_h + 1),
        np.sqrt(h_norm),
    ])


def build_origin_features(train_y, min_history=168):
    """8 origin summary features for each training timestep."""
    n = len(train_y)
    feats = np.zeros((n, 8))
    for t in range(min_history, n):
        r48 = train_y[max(0, t - 47):t + 1]
        r168 = train_y[max(0, t - 167):t + 1]
        feats[t, 0] = train_y[t]
        feats[t, 1] = np.mean(r48)
        feats[t, 2] = np.std(r48) if len(r48) > 1 else 0
        feats[t, 3] = np.mean(r168)
        feats[t, 4] = np.std(r168) if len(r168) > 1 else 0
        feats[t, 5] = np.max(r48) - np.min(r48)
        std = feats[t, 2]
        feats[t, 6] = (train_y[t] - feats[t, 1]) / std if std > 0 else 0
        if len(r48) > 1:
            x = np.arange(len(r48))
            feats[t, 7] = np.polyfit(x, r48, 1)[0]
    return feats


def build_weather_engineered(weather, weather_cols=WEATHER_COLS):
    """5 engineered weather features from raw weather array."""
    idx = {name: i for i, name in enumerate(weather_cols)}
    wind100 = weather[:, idx['wind_speed_100m']]
    solar_sw = weather[:, idx['shortwave_radiation']]
    solar_dir = weather[:, idx['direct_radiation']]
    temp = weather[:, idx['temperature']]
    pressure = weather[:, idx['pressure']]

    wind_power = np.clip(wind100 ** 3 / 1e6, 0, 50)

    wind_ramp = np.zeros_like(wind100)
    wind_ramp[1:] = wind100[1:] - wind100[:-1]

    pressure_series = pd.Series(pressure)
    pressure_mean12 = pressure_series.rolling(12, min_periods=1).mean().values
    pressure_change = pressure - pressure_mean12

    solar_clearness = solar_dir / (solar_sw + 1.0)

    temp_series = pd.Series(temp)
    temp_mean336 = temp_series.rolling(336, min_periods=1).mean().values
    temp_deviation = temp - temp_mean336

    return np.column_stack([wind_power, wind_ramp, pressure_change, solar_clearness, temp_deviation])


def build_interactions(fourier, h_feats, origin_feats, weather, weather_eng, is_weekend):
    """6 physically motivated interaction features (for Ridge/MLP)."""
    idx = {name: i for i, name in enumerate(WEATHER_COLS)}
    hour_sin = fourier[:, 0]
    h_norm = h_feats[:, 0]
    wind100 = weather[:, idx['wind_speed_100m']]
    solar = weather[:, idx['shortwave_radiation']]
    cloud = weather[:, idx['cloud_cover']]
    wind_power = weather_eng[:, 0]
    last_val = origin_feats[:, 0]
    std_48 = origin_feats[:, 2]

    return np.column_stack([
        hour_sin * wind100,
        hour_sin * solar,
        last_val * h_norm,
        std_48 * h_norm,
        wind_power * h_norm,
        is_weekend * cloud,
    ])


# ── Direct Feature Matrix Builder ─────────────────────────────────────────

def build_direct_features(train_ts, train_y, test_ts,
                          train_weather, test_weather,
                          include_interactions=True,
                          min_history=168, max_h=336):
    """
    Build the full v6 direct multi-step feature matrices.

    Returns: X_train, y_train, X_test, feature_names
    """
    n_test = len(test_ts)
    n_train = len(train_y)

    all_fourier = build_fourier(train_ts)
    origin_feats = build_origin_features(train_y, min_history)

    has_weather = train_weather is not None and test_weather is not None
    if has_weather:
        train_weather_eng = build_weather_engineered(train_weather)
        test_weather_eng = build_weather_engineered(test_weather)

    is_weekend_train = (train_ts.dt.dayofweek >= 5).astype(float).values

    X_parts, y_parts = [], []
    for h in range(1, min(max_h, n_test) + 1):
        origins = np.arange(min_history, n_train - h)
        if len(origins) == 0:
            continue
        targets = origins + h

        f = all_fourier[targets]

        h_norm = h / max_h
        h_feats = np.full((len(origins), 4), [
            h_norm, h_norm**2,
            np.log(h + 1) / np.log(max_h + 1),
            np.sqrt(h_norm),
        ])

        o = origin_feats[origins]
        weekend = is_weekend_train[targets].reshape(-1, 1)

        x = np.column_stack([f, h_feats, o, weekend])

        if has_weather:
            w_raw = train_weather[targets]
            w_eng = train_weather_eng[targets]
            x = np.column_stack([x, w_raw, w_eng])

            if include_interactions:
                interactions = build_interactions(
                    f, h_feats, o, w_raw, w_eng, weekend.ravel())
                x = np.column_stack([x, interactions])

        X_parts.append(x)
        y_parts.append(train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    test_fourier = build_fourier(test_ts)
    h_test = build_horizon(n_test, max_h)

    t = n_train - 1
    o_test = np.tile(origin_feats[t:t+1], (n_test, 1))

    is_weekend_test = (test_ts.dt.dayofweek >= 5).astype(float).values.reshape(-1, 1)

    X_test = np.column_stack([test_fourier, h_test, o_test, is_weekend_test])

    if has_weather:
        X_test = np.column_stack([X_test, test_weather, test_weather_eng])
        if include_interactions:
            interactions_test = build_interactions(
                test_fourier, h_test, o_test, test_weather, test_weather_eng,
                is_weekend_test.ravel())
            X_test = np.column_stack([X_test, interactions_test])

    names = []
    for k in range(1, 5):
        names.extend([f'sin_daily_k{k}', f'cos_daily_k{k}'])
    for k in range(1, 3):
        names.extend([f'sin_weekly_k{k}', f'cos_weekly_k{k}'])
    names.extend(['h_norm', 'h_sq', 'h_log', 'h_sqrt'])
    names.extend(['last_value', 'mean_48', 'std_48', 'mean_168', 'std_168',
                  'range_48', 'zscore', 'trend_slope'])
    names.append('is_weekend')
    if has_weather:
        names.extend(WEATHER_COLS)
        names.extend(['wind_power', 'wind_ramp', 'pressure_change',
                      'solar_clearness', 'temp_deviation'])
        if include_interactions:
            names.extend(['hour_x_wind', 'hour_x_solar', 'last_x_h',
                         'std48_x_h', 'windpow_x_h', 'weekend_x_cloud'])

    mask = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
    X_train = X_train[mask]
    y_train = y_train[mask]

    return X_train, y_train, X_test, names
