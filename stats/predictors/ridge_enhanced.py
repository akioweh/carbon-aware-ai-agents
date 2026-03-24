"""Enhanced Direct-Ridge predictor for carbon intensity forecasting (v2).

Uses RidgeCV with 65-feature engineering: 22 Fourier temporal, 4 horizon
encodings, 13 origin summary stats, 16 weather (with engineered features),
and 10 interaction terms. StandardScaler applied before Ridge.

Reads directly from carbon_intensity.db for full historical data (~1 year).
Achieves MAE 24.88 — a 24.6% improvement over the v1 Direct-Ridge (32.99).

Import for production:
    from predictors.ridge_enhanced import get_next_week_carbon_intensity
"""

import logging
import os
import pickle
import sqlite3
import threading
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

import db_utils

warnings.filterwarnings('ignore')
logger = logging.getLogger('stats.ridge_enhanced')

# ── Configuration ────────────────────────────────────────────────────────

CARBON_DB = Path(
    os.environ.get('CARBON_DB_PATH', Path(__file__).parent / 'carbon_intensity.db')
)
WEATHER_CACHE_DIR = Path(__file__).parent / '.weather_cache'

# Benchmark regions (used by plot scripts / experiments only)
REGIONS = {
    13: ('Data-Center-1', 'London', 51.51, -0.13),
    14: ('Data-Center-2', 'South East England', 51.27, 0.52),
    5:  ('Data-Center-3', 'South Yorkshire', 53.38, -1.47),
    3:  ('Data-Center-4', 'North West England', 53.48, -2.24),
    4:  ('Data-Center-5', 'North East England', 54.97, -1.61),
}

# Production DC→region mapping — built from the canonical registry in db_utils
# so it stays aligned with the rest of the system.
def _build_dc_region_map():
    """Build datacenter→(region_id, name, lat, lon) mapping from db_utils registry."""
    dc_map = {}
    for dc in db_utils.DEFAULT_DATACENTERS:
        location_id = dc['location_id']
        region_id = dc['region_id']
        name = dc['name']
        latitude = dc.get('latitude')
        longitude = dc.get('longitude')
        if latitude is not None and longitude is not None:
            dc_map[location_id] = (region_id, name, latitude, longitude)
    return dc_map


DC_REGION_MAP = _build_dc_region_map()

OPEN_METEO_HOURLY = (
    'temperature_2m,relative_humidity_2m,dewpoint_2m,pressure_msl,'
    'cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m,'
    'shortwave_radiation,precipitation'
)

RAW_WX_COLS = [
    'temperature', 'relative_humidity', 'dewpoint', 'pressure',
    'cloud_cover', 'wind_speed', 'wind_direction', 'wind_gusts',
    'solar_radiation', 'precipitation',
]

WX_FEATURES = [
    'temperature', 'relative_humidity', 'dewpoint', 'pressure',
    'cloud_cover', 'wind_speed', 'wind_dir_sin', 'wind_dir_cos',
    'wind_gusts', 'solar_radiation', 'precipitation',
    'wind_power', 'wind_ramp', 'pressure_change',
    'solar_clearness', 'temp_deviation',
]


# ── Data Loading ─────────────────────────────────────────────────────────


def load_carbon_from_db(region_id=None, db_path=None):
    """Load carbon intensity readings directly from carbon_intensity.db."""
    db = db_path or CARBON_DB
    if not Path(db).exists():
        raise FileNotFoundError(f'Carbon DB not found: {db}')

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    if region_id is not None:
        rows = conn.execute(
            'SELECT region_id, timestamp_from, actual FROM carbon_readings '
            'WHERE region_id = ? AND actual IS NOT NULL ORDER BY timestamp_from',
            (region_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT region_id, timestamp_from, actual FROM carbon_readings '
            'WHERE actual IS NOT NULL ORDER BY region_id, timestamp_from'
        ).fetchall()
    conn.close()

    records = []
    for r in rows:
        ts_str = r['timestamp_from'].replace('Z', '+00:00')
        try:
            ts = pd.Timestamp(ts_str)
            if ts.tzinfo is None:
                ts = ts.tz_localize('UTC')
        except Exception:
            continue
        records.append({
            'region_id': r['region_id'],
            'timestamp': ts,
            'carbon_intensity': float(r['actual']),
        })

    return pd.DataFrame(records)


# ── Weather Helpers ──────────────────────────────────────────────────────


def _parse_open_meteo(resp_json):
    hourly = resp_json.get('hourly', {})
    times = hourly.get('time', [])
    if not times:
        return pd.DataFrame()
    return pd.DataFrame({
        'ts': pd.to_datetime(times, utc=True),
        'temperature': hourly.get('temperature_2m', []),
        'relative_humidity': hourly.get('relative_humidity_2m', []),
        'dewpoint': hourly.get('dewpoint_2m', []),
        'pressure': hourly.get('pressure_msl', []),
        'cloud_cover': hourly.get('cloud_cover', []),
        'wind_speed': hourly.get('wind_speed_10m', []),
        'wind_direction': hourly.get('wind_direction_10m', []),
        'wind_gusts': hourly.get('wind_gusts_10m', []),
        'solar_radiation': hourly.get('shortwave_radiation', []),
        'precipitation': hourly.get('precipitation', []),
    })


def _fetch_archive_weather(lat, lon, start_date, end_date):
    url = (
        f'https://archive-api.open-meteo.com/v1/archive'
        f'?latitude={lat}&longitude={lon}'
        f'&start_date={start_date}&end_date={end_date}'
        f'&hourly={OPEN_METEO_HOURLY}'
    )
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return _parse_open_meteo(resp.json())
    except Exception as e:
        logger.warning('Archive weather fetch failed: %s', e)
        return pd.DataFrame()


def _fetch_forecast_weather(lat, lon, days=8):
    url = (
        f'https://api.open-meteo.com/v1/forecast'
        f'?latitude={lat}&longitude={lon}'
        f'&hourly={OPEN_METEO_HOURLY}'
        f'&forecast_days={days}'
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _parse_open_meteo(resp.json())
    except Exception as e:
        logger.warning('Forecast weather fetch failed: %s', e)
        return pd.DataFrame()


def _engineer_weather_features(df):
    df = df.copy()
    for col in RAW_WX_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    wd_rad = np.deg2rad(df['wind_direction'])
    df['wind_dir_sin'] = np.sin(wd_rad)
    df['wind_dir_cos'] = np.cos(wd_rad)
    df['wind_power'] = (df['wind_speed'] ** 3) / 1000.0
    df['wind_ramp'] = df['wind_speed'].diff().fillna(0)
    df['pressure_change'] = df['pressure'].diff().fillna(0)
    df['solar_clearness'] = df['solar_radiation'] / 1000.0
    roll = df['temperature'].rolling(168, min_periods=1).mean()
    df['temp_deviation'] = df['temperature'] - roll
    return df


def _resample_30min(df):
    if df.empty:
        return df
    df = df.set_index('ts').sort_index()
    idx = pd.date_range(df.index.min(), df.index.max(), freq='30min', tz='UTC')
    df = df.reindex(idx).interpolate('time').bfill().ffill()
    return df.reset_index().rename(columns={'index': 'ts'})


def get_weather(lat, lon, start_date, end_date, cache_key=None):
    if cache_key:
        WEATHER_CACHE_DIR.mkdir(exist_ok=True)
        cache_file = WEATHER_CACHE_DIR / f'{cache_key}.pkl'
        if cache_file.exists():
            try:
                cached = pickle.loads(cache_file.read_bytes())
                if isinstance(cached, pd.DataFrame) and not cached.empty:
                    return cached
            except Exception:
                pass

    df = _fetch_archive_weather(lat, lon, start_date, end_date)
    if df.empty:
        return df

    df = _engineer_weather_features(df)
    df = _resample_30min(df)

    if cache_key and not df.empty:
        try:
            WEATHER_CACHE_DIR.mkdir(exist_ok=True)
            (WEATHER_CACHE_DIR / f'{cache_key}.pkl').write_bytes(pickle.dumps(df))
        except Exception:
            pass

    return df


def _align_weather(wx_df, target_ts):
    if wx_df is None or wx_df.empty:
        return None
    target_df = pd.DataFrame({'ts': pd.to_datetime(target_ts).round('30min')})
    if target_df['ts'].dt.tz is None:
        target_df['ts'] = target_df['ts'].dt.tz_localize('UTC')
    wx_rounded = wx_df.copy()
    wx_rounded['ts'] = wx_rounded['ts'].dt.round('30min')
    merged = target_df.merge(wx_rounded, on='ts', how='left')
    for col in WX_FEATURES:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
        else:
            merged[col] = 0.0
    return merged[WX_FEATURES].values


# ── Feature Engineering ──────────────────────────────────────────────────


def build_temporal_features(timestamps):
    """Fourier temporal features + binary flags. Returns (N, 22)."""
    ts = pd.to_datetime(timestamps)
    if ts.tz is None:
        ts = ts.tz_localize('UTC')
    hour = ts.hour + ts.minute / 60.0
    dow = ts.dayofweek.astype(float)
    doy = ts.dayofyear.astype(float)

    cols = []
    for k in range(1, 7):
        cols.append(np.sin(2 * k * np.pi * hour / 24))
        cols.append(np.cos(2 * k * np.pi * hour / 24))
    for k in range(1, 3):
        cols.append(np.sin(2 * k * np.pi * dow / 7))
        cols.append(np.cos(2 * k * np.pi * dow / 7))
    for k in range(1, 3):
        cols.append(np.sin(2 * k * np.pi * doy / 365.25))
        cols.append(np.cos(2 * k * np.pi * doy / 365.25))
    cols.append((dow >= 5).astype(float))
    cols.append(((hour < 6) | (hour >= 22)).astype(float))
    return np.column_stack(cols)


def build_origin_stats(y):
    """Vectorised origin summary statistics. Returns dict of arrays."""
    n = len(y)
    s = pd.Series(y, dtype=float)
    stats = {
        'last_value': y.copy(),
        'mean_24h': s.rolling(48, min_periods=1).mean().values,
        'std_24h': s.rolling(48, min_periods=1).std().fillna(0).values,
        'median_24h': s.rolling(48, min_periods=1).median().values,
        'min_24h': s.rolling(48, min_periods=1).min().values,
        'max_24h': s.rolling(48, min_periods=1).max().values,
        'mean_7d': s.rolling(336, min_periods=1).mean().values,
        'std_7d': s.rolling(336, min_periods=1).std().fillna(0).values,
        'last_diff': s.diff().fillna(0).values,
    }
    short = s.rolling(24, min_periods=1).mean()
    long = s.rolling(48, min_periods=1).mean()
    stats['trend'] = ((short - long) / 24).fillna(0).values

    lag48 = np.zeros(n)
    lag336 = np.zeros(n)
    for t in range(n):
        lag48[t] = y[t - 48] if t >= 48 else y[t]
        lag336[t] = y[t - 336] if t >= 336 else y[t]
    stats['lag_24h'] = lag48
    stats['lag_7d'] = lag336

    same_hour = np.zeros(n)
    cum_sum, cum_cnt = {}, {}
    for t in range(n):
        b = t % 48
        if b in cum_cnt and cum_cnt[b] > 0:
            same_hour[t] = cum_sum[b] / cum_cnt[b]
        else:
            same_hour[t] = y[t]
        cum_sum[b] = cum_sum.get(b, 0.0) + y[t]
        cum_cnt[b] = cum_cnt.get(b, 0) + 1
    stats['same_hour_mean'] = same_hour
    return stats


ORIGIN_KEYS = [
    'last_value', 'mean_24h', 'std_24h', 'median_24h',
    'min_24h', 'max_24h', 'mean_7d', 'std_7d', 'last_diff', 'trend',
    'lag_24h', 'lag_7d', 'same_hour_mean',
]


def _concat_origin_array(stats_dict):
    return np.column_stack([stats_dict[k] for k in ORIGIN_KEYS])


def _interactions(temporal, h_feat, origin, wx=None):
    """Build interaction features (stable set that works across all regions)."""
    hour_sin = temporal[:, 0:1]
    hour_cos = temporal[:, 1:2]
    is_weekend = temporal[:, -2:-1]
    last_val = origin[:, 0:1]
    h_norm = h_feat[:, 0:1]

    parts = [last_val * h_norm, is_weekend * hour_sin, is_weekend * hour_cos]

    if wx is not None and wx.shape[1] >= 16:
        ws = wx[:, 5:6]
        sol = wx[:, 9:10]
        temp = wx[:, 0:1]
        parts += [
            hour_sin * ws, hour_cos * ws,
            hour_sin * sol, hour_cos * sol,
            ws * sol, temp * hour_sin,
            last_val * ws,
        ]

    return np.column_stack(parts)


def build_direct_features(
    train_ts, train_y, test_ts,
    train_wx=None, test_wx=None,
    origin_idx=None, subsample=5,
    test_only=False,
):
    """Build feature matrices for direct multi-step forecasting."""
    n_train = len(train_y)
    n_test = len(test_ts)
    min_hist = 48
    max_h = min(n_test, 336)
    has_wx = train_wx is not None and test_wx is not None

    origin_stats = build_origin_stats(train_y)
    origin_arr = _concat_origin_array(origin_stats)

    X_train = y_train = None

    if not test_only:
        all_temporal = build_temporal_features(train_ts)

        X_parts, y_parts = [], []
        for h in range(1, max_h + 1):
            all_origins = np.arange(min_hist, n_train - h)
            if len(all_origins) == 0:
                continue
            origins = all_origins[::subsample] if subsample > 1 else all_origins
            targets = origins + h

            temporal = all_temporal[targets]
            h_norm = h / 336.0
            h_feat = np.column_stack([
                np.full(len(origins), h_norm),
                np.full(len(origins), h_norm ** 2),
                np.full(len(origins), h_norm ** 3),
                np.full(len(origins), np.log1p(h) / np.log(337)),
            ])
            of = origin_arr[origins]

            x = np.column_stack([temporal, h_feat, of])
            wx_slice = train_wx[targets] if has_wx else None
            if has_wx:
                x = np.column_stack([x, wx_slice])
            x = np.column_stack([x, _interactions(temporal, h_feat, of, wx_slice)])

            X_parts.append(x)
            y_parts.append(train_y[targets])

        X_train = np.vstack(X_parts)
        y_train = np.concatenate(y_parts)

    # Test features
    test_temporal = build_temporal_features(test_ts)
    if origin_idx is None:
        origin_idx = n_train - 1
    of_test = np.tile(origin_arr[origin_idx:origin_idx + 1], (n_test, 1))

    train_origin_ts = pd.Timestamp(train_ts[origin_idx])
    if train_origin_ts.tzinfo is None:
        train_origin_ts = train_origin_ts.tz_localize('UTC')
    test_ts_dt = pd.to_datetime(test_ts)
    if test_ts_dt.tz is None:
        test_ts_dt = test_ts_dt.tz_localize('UTC')
    deltas = (test_ts_dt - train_origin_ts).total_seconds() / 1800.0
    h_vals = np.asarray(deltas, dtype=float)
    h_norm_test = h_vals / 336.0
    h_feat_test = np.column_stack([
        h_norm_test,
        h_norm_test ** 2,
        h_norm_test ** 3,
        np.log1p(h_vals) / np.log(337),
    ])

    X_test = np.column_stack([test_temporal, h_feat_test, of_test])
    if has_wx:
        X_test = np.column_stack([X_test, test_wx])
    X_test = np.column_stack([
        X_test, _interactions(test_temporal, h_feat_test, of_test, test_wx),
    ])

    return X_train, y_train, X_test


# ── Model Training / Prediction ─────────────────────────────────────────


def train_ridge(X_train, y_train):
    """Train RidgeFull model. Fast (<1s), deterministic."""
    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X_train)
    ridge = RidgeCV(alphas=[0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0])
    ridge.fit(X_sc, y_train)
    return ridge, scaler


def predict_ridge(ridge, scaler, X):
    """Predict with RidgeFull model."""
    X_sc = scaler.transform(X)
    return np.clip(ridge.predict(X_sc), 0, 500)


# ── Model Cache ──────────────────────────────────────────────────────────

# Cache trained models per datacenter to avoid rebuilding the ~2M-row
# training matrix on every prediction cycle.  Keyed by DC name; invalidated
# when the training data fingerprint (row count + last timestamp) changes.
_model_cache: dict[str, dict] = {}
_train_lock = threading.Lock()


# ── Production API ───────────────────────────────────────────────────────


def _predict_ci(series_df, dc_name=None, now=None):
    df = series_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp').drop_duplicates('timestamp').dropna(subset=['carbon_intensity'])
    df = df.reset_index(drop=True)

    if len(df) < 96:
        raise ValueError(f'Need >= 96 observations, got {len(df)}')

    train_ts = df['timestamp'].values
    train_y = df['carbon_intensity'].values.astype(float)
    origin_ts = df['timestamp'].iloc[-1]
    start = pd.Timestamp(now, tz='UTC') if now else origin_ts
    start_rounded = start.ceil('5min')

    fc_30 = pd.date_range(start_rounded + pd.Timedelta(minutes=30), periods=337, freq='30min')
    fc_30 = fc_30.insert(0, start_rounded)

    train_wx = test_wx = None
    if dc_name and dc_name in DC_REGION_MAP:
        rid, _, lat, lon = DC_REGION_MAP[dc_name]
        s_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')
        e_date = df['timestamp'].iloc[-1].strftime('%Y-%m-%d')
        archive = get_weather(lat, lon, s_date, e_date, cache_key=f'{rid}_archive_{s_date}_{e_date}')
        forecast = _fetch_forecast_weather(lat, lon)
        if not forecast.empty:
            forecast = _engineer_weather_features(forecast)
            forecast = _resample_30min(forecast)
        if not archive.empty:
            train_wx = _align_weather(archive, train_ts)
        if not forecast.empty:
            test_wx = _align_weather(forecast, fc_30)

    # Check model cache — avoids rebuilding the massive training matrix
    fingerprint = (len(train_y), str(train_ts[-1]))
    cache_key = dc_name or '__default__'
    cached = _model_cache.get(cache_key)

    if cached and cached['fingerprint'] == fingerprint:
        ridge, scaler = cached['ridge'], cached['scaler']
        _, _, X_test = build_direct_features(
            train_ts, train_y, fc_30,
            train_wx=train_wx, test_wx=test_wx,
            subsample=3, test_only=True,
        )
        logger.info('Model cache hit for %s — skipping training', cache_key)
    else:
        with _train_lock:
            # Re-check after acquiring lock (another thread may have trained)
            cached = _model_cache.get(cache_key)
            if cached and cached['fingerprint'] == fingerprint:
                ridge, scaler = cached['ridge'], cached['scaler']
                _, _, X_test = build_direct_features(
                    train_ts, train_y, fc_30,
                    train_wx=train_wx, test_wx=test_wx,
                    subsample=3, test_only=True,
                )
                logger.info('Model cache hit for %s after lock — skipping training', cache_key)
            else:
                logger.info('Training new model for %s (data: %d points)', cache_key, len(train_y))
                X_train, y_train_arr, X_test = build_direct_features(
                    train_ts, train_y, fc_30,
                    train_wx=train_wx, test_wx=test_wx,
                    subsample=3,
                )
                ridge, scaler = train_ridge(X_train, y_train_arr)
                _model_cache[cache_key] = {
                    'ridge': ridge,
                    'scaler': scaler,
                    'fingerprint': fingerprint,
                }
                logger.info('Model cached for %s', cache_key)

    preds = predict_ridge(ridge, scaler, X_test)

    fc_series = pd.Series(preds, index=fc_30)
    fc_5 = fc_series.resample('5min').interpolate('linear').bfill()
    fc_5 = fc_5.iloc[:2016]
    return pd.DataFrame({'ds': fc_5.index, 'yhat': np.clip(fc_5.values, 0, 500)})


def get_next_week_carbon_intensity(historical_df, now=None):
    dc_name = None
    if 'location' in historical_df.columns:
        locs = historical_df['location'].dropna().unique()
        if len(locs) == 1 and locs[0] in DC_REGION_MAP:
            dc_name = locs[0]
    return _predict_ci(historical_df, dc_name=dc_name, now=now)


def get_next_week_greenness(historical_greenness_df):
    dc_name = None
    if 'location' in historical_greenness_df.columns:
        locs = historical_greenness_df['location'].dropna().unique()
        if len(locs) == 1 and locs[0] in DC_REGION_MAP:
            dc_name = locs[0]
    ci_df = _predict_ci(historical_greenness_df, dc_name=dc_name)
    ci = ci_df['yhat'].values
    greenness = np.clip(100.0 * (1.0 - ci / 350.0), 0, 100)
    return pd.DataFrame({'ds': ci_df['ds'], 'yhat': greenness, 'ci': ci})
