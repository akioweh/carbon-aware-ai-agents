"""Ensemble predictor for carbon intensity forecasting.

Ridge + LightGBM ensemble with rich feature engineering.
Reads directly from carbon_intensity.db for full historical data.

Run directly for benchmark:
    python3 predictor_ensemble.py [--no-weather]

Import for production:
    from predictor_ensemble import get_next_week_carbon_intensity
"""

import logging
import os
import pickle
import sqlite3
import sys
import time
import warnings
from pathlib import Path

# Prevent OpenMP thread conflicts between LightGBM and PyTorch
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests
import torch
import torch.nn as nn
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')
logger = logging.getLogger('stats.ensemble')

# ── Configuration ────────────────────────────────────────────────────────

CARBON_DB = Path(
    os.environ.get('CARBON_DB_PATH', Path(__file__).parent / 'carbon_intensity.db')
)
WEATHER_CACHE_DIR = Path(__file__).parent / '.weather_cache'

REGIONS = {
    13: ('Data-Center-1', 'London', 51.51, -0.13),
    14: ('Data-Center-2', 'South East England', 51.27, 0.52),
    5:  ('Data-Center-3', 'South Yorkshire', 53.38, -1.47),
    3:  ('Data-Center-4', 'North West England', 53.48, -2.24),
    4:  ('Data-Center-5', 'North East England', 54.97, -1.61),
}

DC_TO_REGION = {v[0]: (k, v[1], v[2], v[3]) for k, v in REGIONS.items()}

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


# ── PyTorch MLP ─────────────────────────────────────────────────────────

DEVICE = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')


class TorchMLP(nn.Module):
    def __init__(self, input_dim, hidden_dims=(2048, 1024, 512), dropout=0.15):
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers.extend([
                nn.Linear(prev, h),
                nn.BatchNorm1d(h),
                nn.GELU(),
                nn.Dropout(dropout),
            ])
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(-1)


class TorchMLPWrapper:
    """Sklearn-compatible wrapper around PyTorch MLP."""

    def __init__(self, hidden_dims=(2048, 1024, 512), dropout=0.15,
                 lr=1e-3, batch_size=2048, max_epochs=300,
                 patience=20, val_frac=0.15, max_samples=250_000):
        self.hidden_dims = hidden_dims
        self.dropout = dropout
        self.lr = lr
        self.batch_size = batch_size
        self.max_epochs = max_epochs
        self.patience = patience
        self.val_frac = val_frac
        self.max_samples = max_samples
        self.model = None

    def fit(self, X, y):
        rng = np.random.RandomState(42)
        n = len(X)
        if n > self.max_samples:
            idx = rng.choice(n, size=self.max_samples, replace=False)
            X, y = X[idx], y[idx]
            n = self.max_samples

        val_size = int(n * self.val_frac)
        perm = rng.permutation(n)
        val_idx, train_idx = perm[:val_size], perm[val_size:]

        X_tr = torch.FloatTensor(X[train_idx]).to(DEVICE)
        y_tr = torch.FloatTensor(y[train_idx]).to(DEVICE)
        X_va = torch.FloatTensor(X[val_idx]).to(DEVICE)
        y_va = torch.FloatTensor(y[val_idx]).to(DEVICE)

        self.model = TorchMLP(X.shape[1], self.hidden_dims, self.dropout).to(DEVICE)
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.max_epochs)

        best_val_loss = float('inf')
        best_state = None
        wait = 0

        for epoch in range(self.max_epochs):
            self.model.train()
            perm_e = torch.randperm(len(X_tr), device=DEVICE)

            for i in range(0, len(X_tr), self.batch_size):
                bi = perm_e[i:i + self.batch_size]
                pred = self.model(X_tr[bi])
                loss = nn.functional.mse_loss(pred, y_tr[bi])
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            scheduler.step()

            # Validation
            self.model.eval()
            with torch.no_grad():
                val_loss = nn.functional.mse_loss(self.model(X_va), y_va).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
                wait = 0
            else:
                wait += 1
                if wait >= self.patience:
                    break

        self.model.load_state_dict(best_state)
        self.model.eval()
        self.model.cpu()
        return self

    def predict(self, X):
        self.model.eval()
        with torch.no_grad():
            X_t = torch.FloatTensor(X)
            # Batch predict to avoid OOM
            if len(X_t) > 10000:
                parts = []
                for i in range(0, len(X_t), 10000):
                    parts.append(self.model(X_t[i:i+10000]).numpy())
                return np.concatenate(parts)
            return self.model(X_t).numpy()


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
    # 6 harmonics for hour-of-day (captures complex daily patterns)
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

    # Lag features: same time yesterday, same time last week
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
        ws = wx[:, 5:6]       # wind_speed
        sol = wx[:, 9:10]     # solar_radiation
        temp = wx[:, 0:1]     # temperature
        wind_pow = wx[:, 11:12]  # wind_power
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


def _n_base_features(n_features):
    """Number of non-interaction features (temporal+horizon+origin+weather)."""
    # 22 temporal + 4 horizon + 13 origin = 39 base (no weather)
    # 22 temporal + 4 horizon + 13 origin + 16 weather = 55 base (with weather)
    if n_features > 55:
        return 55  # has weather
    return 39  # no weather


def train_ensemble(X_train, y_train):
    """Train Ridge(full) + Ridge(base) + MLP(wide) + LGBM ensemble.

    4 diverse models like James: 2 linear (different features) + 1 neural + 1 tree.
    """
    models = {}
    n_base = _n_base_features(X_train.shape[1])
    rng = np.random.RandomState(42)
    n = len(X_train)

    # Scale features
    scaler_full = StandardScaler()
    X_full_sc = scaler_full.fit_transform(X_train)
    models['scaler_full'] = scaler_full

    scaler_base = StandardScaler()
    X_base_sc = scaler_base.fit_transform(X_train[:, :n_base])
    models['scaler_base'] = scaler_base

    # Ridge 1: full features (interactions help linear models)
    ridge_full = RidgeCV(alphas=[0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0])
    ridge_full.fit(X_full_sc, y_train)
    models['ridge_full'] = ridge_full

    # Ridge 2: base features only (more robust on volatile regions)
    ridge_base = RidgeCV(alphas=[0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0])
    ridge_base.fit(X_base_sc, y_train)
    models['ridge_base'] = ridge_base

    # PyTorch MLP: wide arch with dropout + batch norm + cosine LR
    mlp = TorchMLPWrapper(
        hidden_dims=(2048, 1024, 512),
        dropout=0.2,
        lr=1e-3,
        batch_size=4096,
        max_epochs=100,
        patience=10,
        max_samples=150_000,
    )
    mlp.fit(X_full_sc, y_train)
    models['mlp'] = mlp

    # LGBM: all features (unscaled — trees don't need scaling)
    lgb_size = min(150_000, n)
    lgb_idx = rng.choice(n, size=lgb_size, replace=False)
    X_lgb_sub = X_train[lgb_idx]
    y_lgb_sub = y_train[lgb_idx]

    split = int(lgb_size * 0.85)
    perm = rng.permutation(lgb_size)
    tr_i, va_i = perm[:split], perm[split:]

    lgb_params = dict(
        objective='regression',
        metric='l2',
        num_leaves=255,
        max_depth=-1,
        learning_rate=0.03,
        feature_fraction=0.7,
        bagging_fraction=0.7,
        bagging_freq=5,
        min_child_samples=30,
        n_estimators=3000,
        verbose=-1,
        n_jobs=1,
        reg_alpha=0.5,
        reg_lambda=2.0,
    )
    lgb_model = lgb.LGBMRegressor(**lgb_params)
    lgb_model.fit(
        X_lgb_sub[tr_i], y_lgb_sub[tr_i],
        eval_set=[(X_lgb_sub[va_i], y_lgb_sub[va_i])],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    models['lgbm'] = lgb_model
    models['n_base'] = n_base

    return models


def predict_ensemble(models, X):
    """Trimmed mean ensemble — drop the most extreme prediction per timestep."""
    n_base = models['n_base']
    X_full_sc = models['scaler_full'].transform(X)
    X_base_sc = models['scaler_base'].transform(X[:, :n_base])

    preds_list = [
        models['ridge_full'].predict(X_full_sc),
        models['ridge_base'].predict(X_base_sc),
        models['mlp'].predict(X_full_sc),
        models['lgbm'].predict(X),
    ]

    # Add conditioned MLP if available
    if 'cond_mlp' in models and 'cond_scaler' in models and 'region_id' in models:
        rid_onehot = _region_onehot(models['region_id'], len(X))
        X_cond = np.column_stack([X, rid_onehot])
        X_cond_sc = models['cond_scaler'].transform(X_cond)
        preds_list.append(models['cond_mlp'].predict(X_cond_sc))

    preds = np.column_stack(preds_list)

    # Trimmed mean: for each timestep, drop the prediction furthest from median
    median = np.median(preds, axis=1, keepdims=True)
    dist = np.abs(preds - median)
    worst = np.argmax(dist, axis=1)
    mask = np.ones_like(preds, dtype=bool)
    mask[np.arange(len(preds)), worst] = False
    p = np.where(mask, preds, np.nan)
    p = np.nanmean(p, axis=1)
    return np.clip(p, 0, 500)


# Region one-hot encoding for conditioned MLP
REGION_IDS = sorted(REGIONS.keys())  # [3, 4, 5, 13, 14]
REGION_ID_TO_IDX = {rid: i for i, rid in enumerate(REGION_IDS)}


def _region_onehot(region_id, n_rows):
    """Create one-hot encoding for a region."""
    oh = np.zeros((n_rows, len(REGION_IDS)), dtype=np.float32)
    idx = REGION_ID_TO_IDX[region_id]
    oh[:, idx] = 1.0
    return oh


def train_conditioned_mlp(region_data):
    """Train a single MLP across all regions with region conditioning.

    Args:
        region_data: dict of region_id -> (X_train_scaled, y_train)
    Returns:
        (model, scaler) for the conditioned features
    """
    # Combine all regions with one-hot region encoding
    X_parts, y_parts = [], []
    for rid, (X_sc, y) in region_data.items():
        oh = _region_onehot(rid, len(X_sc))
        X_cond = np.column_stack([X_sc, oh])
        X_parts.append(X_cond)
        y_parts.append(y)

    X_all = np.vstack(X_parts)
    y_all = np.concatenate(y_parts)
    print(f'  Conditioned MLP: {X_all.shape[0]} samples, {X_all.shape[1]} features')

    # Scale the combined features (region one-hot stays ~0/1)
    scaler = StandardScaler()
    X_all_sc = scaler.fit_transform(X_all)

    mlp = TorchMLPWrapper(
        hidden_dims=(4096, 2048, 1024),
        dropout=0.15,
        lr=1e-3,
        batch_size=4096,
        max_epochs=200,
        patience=15,
        max_samples=500_000,
    )
    mlp.fit(X_all_sc, y_all)
    return mlp, scaler


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
    if dc_name and dc_name in DC_TO_REGION:
        rid, _, lat, lon = DC_TO_REGION[dc_name]
        s_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')
        e_date = df['timestamp'].iloc[-1].strftime('%Y-%m-%d')
        archive = get_weather(lat, lon, s_date, e_date, cache_key=f'{rid}_archive')
        forecast = _fetch_forecast_weather(lat, lon)
        if not forecast.empty:
            forecast = _engineer_weather_features(forecast)
            forecast = _resample_30min(forecast)
        if not archive.empty:
            train_wx = _align_weather(archive, train_ts)
        if not forecast.empty:
            test_wx = _align_weather(forecast, fc_30)

    X_train, y_train, X_test = build_direct_features(
        train_ts, train_y, fc_30,
        train_wx=train_wx, test_wx=test_wx,
        subsample=10,
    )

    models = train_ensemble(X_train, y_train)
    preds = predict_ensemble(models, X_test)

    fc_series = pd.Series(preds, index=fc_30)
    fc_5 = fc_series.resample('5min').interpolate('linear').bfill()
    fc_5 = fc_5.iloc[:2016]
    return pd.DataFrame({'ds': fc_5.index, 'yhat': np.clip(fc_5.values, 0, 500)})


def get_next_week_carbon_intensity(historical_df, now=None):
    dc_name = None
    if 'location' in historical_df.columns:
        locs = historical_df['location'].dropna().unique()
        if len(locs) == 1 and locs[0] in DC_TO_REGION:
            dc_name = locs[0]
    return _predict_ci(historical_df, dc_name=dc_name, now=now)


def get_next_week_greenness(historical_greenness_df):
    dc_name = None
    if 'location' in historical_greenness_df.columns:
        locs = historical_greenness_df['location'].dropna().unique()
        if len(locs) == 1 and locs[0] in DC_TO_REGION:
            dc_name = locs[0]
    ci_df = _predict_ci(historical_greenness_df, dc_name=dc_name)
    ci = ci_df['yhat'].values
    greenness = np.clip(100.0 * (1.0 - ci / 350.0), 0, 100)
    return pd.DataFrame({'ds': ci_df['ds'], 'yhat': greenness, 'ci': ci})


# ── Benchmark ────────────────────────────────────────────────────────────


def _evaluate_region(rid, dc_name, region_name, lat, lon, rdf, use_weather):
    """Evaluate a single region. Returns dict of results."""
    log = []
    log.append(f'\n{"─" * 60}')
    log.append(f'Region {rid}: {region_name} ({dc_name})')
    log.append(f'{"─" * 60}')
    log.append(f'  {len(rdf)} readings')

    t_max = rdf['timestamp'].max()
    t_test = t_max - pd.Timedelta(days=7)
    t_val = t_max - pd.Timedelta(days=14)

    train = rdf[rdf['timestamp'] <= t_val].reset_index(drop=True)
    val = rdf[(rdf['timestamp'] > t_val) & (rdf['timestamp'] <= t_test)].reset_index(drop=True)
    test = rdf[rdf['timestamp'] > t_test].reset_index(drop=True)

    log.append(f'  Train: {len(train)}  Val: {len(val)}  Test: {len(test)}')
    if len(test) == 0 or len(val) == 0:
        log.append('  Not enough data, skipping')
        return {'log': log, 'dc_name': dc_name}

    train_ts = train['timestamp'].values
    train_y = train['carbon_intensity'].values.astype(float)

    train_wx = val_wx = test_wx = None
    if use_weather:
        s_date = train['timestamp'].iloc[0].strftime('%Y-%m-%d')
        e_date = rdf['timestamp'].iloc[-1].strftime('%Y-%m-%d')
        t0 = time.time()
        wx = get_weather(lat, lon, s_date, e_date, cache_key=f'bench_{rid}')
        log.append(f'  Weather fetched ({time.time()-t0:.1f}s)')

        if not wx.empty:
            full_ts = rdf['timestamp'].values
            full_wx = _align_weather(wx, full_ts)
            if full_wx is not None:
                train_wx = full_wx[:len(train)]
                val_wx = full_wx[len(train):len(train) + len(val)]
                test_wx = full_wx[len(train) + len(val):]

    # Build train features (subsample=3 for denser training)
    t0 = time.time()
    X_tr, y_tr, _ = build_direct_features(
        train_ts, train_y, val['timestamp'].values,
        train_wx=train_wx, test_wx=val_wx,
        subsample=3,
    )
    log.append(f'  Features built ({time.time()-t0:.1f}s)  X_train={X_tr.shape}')

    # Train
    t0 = time.time()
    models = train_ensemble(X_tr, y_tr)
    log.append(f'  Trained ({time.time()-t0:.1f}s)')

    # Test features use combined (train+val) origin stats for recency
    combined_ts = np.concatenate([train_ts, val['timestamp'].values])
    combined_y = np.concatenate([train_y, val['carbon_intensity'].values.astype(float)])
    combined_wx = None
    if train_wx is not None and val_wx is not None:
        combined_wx = np.vstack([train_wx, val_wx])

    _, _, X_te = build_direct_features(
        combined_ts, combined_y, test['timestamp'].values,
        train_wx=combined_wx, test_wx=test_wx,
        test_only=True,
    )

    # --- Evaluate on VALIDATION set first (for model selection) ---
    _, _, X_val = build_direct_features(
        train_ts, train_y, val['timestamp'].values,
        train_wx=train_wx, test_wx=val_wx,
        test_only=True,
    )
    y_val = val['carbon_intensity'].values
    n_base = models['n_base']

    X_val_full_sc = models['scaler_full'].transform(X_val)
    X_val_base_sc = models['scaler_base'].transform(X_val[:, :n_base])

    val_maes = {
        'ridge_full': np.mean(np.abs(np.clip(models['ridge_full'].predict(X_val_full_sc), 0, 500) - y_val)),
        'ridge_base': np.mean(np.abs(np.clip(models['ridge_base'].predict(X_val_base_sc), 0, 500) - y_val)),
        'mlp': np.mean(np.abs(np.clip(models['mlp'].predict(X_val_full_sc), 0, 500) - y_val)),
        'lgbm': np.mean(np.abs(np.clip(models['lgbm'].predict(X_val), 0, 500) - y_val)),
    }
    best_val_model = min(val_maes, key=val_maes.get)
    log.append(f'  Val MAEs: RF={val_maes["ridge_full"]:.1f} RB={val_maes["ridge_base"]:.1f} MLP={val_maes["mlp"]:.1f} LGB={val_maes["lgbm"]:.1f} → best={best_val_model}')

    # --- Evaluate on TEST set ---
    y_test = test['carbon_intensity'].values
    X_full_sc = models['scaler_full'].transform(X_te)
    X_base_sc = models['scaler_base'].transform(X_te[:, :n_base])

    p_rf = np.clip(models['ridge_full'].predict(X_full_sc), 0, 500)
    p_rb = np.clip(models['ridge_base'].predict(X_base_sc), 0, 500)
    p_mlp = np.clip(models['mlp'].predict(X_full_sc), 0, 500)
    p_lgbm = np.clip(models['lgbm'].predict(X_te), 0, 500)
    p_ens = predict_ensemble(models, X_te)

    # Val-selected model
    model_preds = {'ridge_full': p_rf, 'ridge_base': p_rb, 'mlp': p_mlp, 'lgbm': p_lgbm}
    p_valsel = model_preds[best_val_model]

    # Weighted by inverse val MAE
    val_weights = np.array([1.0 / val_maes[k] for k in ['ridge_full', 'ridge_base', 'mlp', 'lgbm']])
    val_weights /= val_weights.sum()
    all_preds = np.column_stack([p_rf, p_rb, p_mlp, p_lgbm])
    p_wt = np.clip((all_preds * val_weights).sum(axis=1), 0, 500)

    p_median = np.clip(np.median(all_preds, axis=1), 0, 500)

    # Drop worst val model, average the rest
    worst_val_model = max(val_maes, key=val_maes.get)
    model_names = ['ridge_full', 'ridge_base', 'mlp', 'lgbm']
    keep_idx = [i for i, name in enumerate(model_names) if name != worst_val_model]
    p_valdrop = np.clip(np.mean(all_preds[:, keep_idx], axis=1), 0, 500)

    mae_rf = np.mean(np.abs(p_rf - y_test))
    mae_rb = np.mean(np.abs(p_rb - y_test))
    mae_mlp = np.mean(np.abs(p_mlp - y_test))
    mae_lgbm = np.mean(np.abs(p_lgbm - y_test))
    mae_ens = np.mean(np.abs(p_ens - y_test))
    mae_valsel = np.mean(np.abs(p_valsel - y_test))
    mae_wt = np.mean(np.abs(p_wt - y_test))
    mae_median = np.mean(np.abs(p_median - y_test))
    mae_valdrop = np.mean(np.abs(p_valdrop - y_test))

    log.append(f'  RidgeF: {mae_rf:.2f}  RidgeB: {mae_rb:.2f}  MLP: {mae_mlp:.2f}  LGBM: {mae_lgbm:.2f}')
    log.append(f'  Trim: {mae_ens:.2f}  Med: {mae_median:.2f}  ValWt: {mae_wt:.2f}  ValDrop({worst_val_model[:4]}): {mae_valdrop:.2f}')

    return {
        'dc_name': dc_name,
        'mae_ridge': mae_rf,
        'mae_ridge_base': mae_rb,
        'mae_mlp': mae_mlp,
        'mae_lgbm': mae_lgbm,
        'mae_ens': mae_ens,
        'mae_valsel': mae_valsel,
        'mae_wt': mae_wt,
        'mae_median': mae_median,
        'mae_valdrop': mae_valdrop,
        'log': log,
    }


def benchmark(use_weather=True):
    """Evaluate on last 7 days, all regions in parallel."""
    print('=' * 70)
    print('ENSEMBLE BENCHMARK — Ridge + LightGBM (parallel)')
    print('=' * 70)

    all_data = load_carbon_from_db()
    print(f'Loaded {len(all_data)} readings from {CARBON_DB.name}')

    # Pre-fetch all weather (sequential to avoid API rate limits)
    if use_weather:
        print('Pre-fetching weather for all regions...')
        for rid, (dc_name, region_name, lat, lon) in REGIONS.items():
            rdf = all_data[all_data['region_id'] == rid].sort_values('timestamp')
            s_date = rdf['timestamp'].iloc[0].strftime('%Y-%m-%d')
            e_date = rdf['timestamp'].iloc[-1].strftime('%Y-%m-%d')
            wx = get_weather(lat, lon, s_date, e_date, cache_key=f'bench_{rid}')
            status = f'{len(wx)} rows' if not wx.empty else 'FAILED'
            print(f'  Region {rid} ({region_name}): {status}')

    # Run regions sequentially (PyTorch + OpenMP conflicts with threads)
    print('\nTraining per-region models...')
    t0_total = time.time()

    results = {}
    for rid, (dc_name, region_name, lat, lon) in REGIONS.items():
        rdf = all_data[all_data['region_id'] == rid].sort_values('timestamp').reset_index(drop=True)
        result = _evaluate_region(rid, dc_name, region_name, lat, lon, rdf, use_weather)
        results[dc_name] = result
        for line in result['log']:
            print(line)

    print(f'\nTotal wall-clock time: {time.time()-t0_total:.1f}s')

    # Summary
    print(f'\n{"=" * 70}')
    print('SUMMARY')
    print(f'{"=" * 70}')
    hdr = f'{"Region":<16} {"RidgeF":>7} {"RidgeB":>7} {"MLP":>7} {"LGBM":>7} {"Trim":>7} {"ValWt":>7} {"ValDrp":>7} {"Med":>7}'
    print(hdr)
    print('-' * len(hdr))

    rf_v, rb_v, mlp_v, lgbm_v, ens_v, wt_v, vd_v, med_v = [], [], [], [], [], [], [], []
    for dc_name in ['Data-Center-1', 'Data-Center-2', 'Data-Center-3', 'Data-Center-4', 'Data-Center-5']:
        r = results.get(dc_name, {})
        if 'mae_ridge' in r:
            rf_v.append(r['mae_ridge'])
            rb_v.append(r.get('mae_ridge_base', 0))
            mlp_v.append(r.get('mae_mlp', 0))
            lgbm_v.append(r.get('mae_lgbm', 0))
            ens_v.append(r['mae_ens'])
            wt_v.append(r.get('mae_wt', 0))
            vd_v.append(r.get('mae_valdrop', 0))
            med_v.append(r.get('mae_median', 0))
            print(f'{dc_name:<16} {r["mae_ridge"]:7.2f} {r.get("mae_ridge_base",0):7.2f} {r.get("mae_mlp",0):7.2f} {r.get("mae_lgbm",0):7.2f} {r["mae_ens"]:7.2f} {r.get("mae_wt",0):7.2f} {r.get("mae_valdrop",0):7.2f} {r.get("mae_median",0):7.2f}')

    print('-' * len(hdr))
    avgs = [np.mean(v) if v else 0 for v in [rf_v, rb_v, mlp_v, lgbm_v, ens_v, wt_v, vd_v, med_v]]
    print(f'{"AVG MAE":<16} {avgs[0]:7.2f} {avgs[1]:7.2f} {avgs[2]:7.2f} {avgs[3]:7.2f} {avgs[4]:7.2f} {avgs[5]:7.2f} {avgs[6]:7.2f} {avgs[7]:7.2f}')

    all_avgs = {'RidgeF': avgs[0], 'RidgeB': avgs[1], 'MLP': avgs[2], 'LGBM': avgs[3],
                'Trim': avgs[4], 'ValWt': avgs[5], 'ValDrop': avgs[6], 'Median': avgs[7]}
    best_name = min(all_avgs, key=all_avgs.get)
    best_avg = all_avgs[best_name]

    print(f'\nJames baseline: 22.02 (ensemble avg MAE)')
    print(f'Our old Ridge:  32.99')
    print(f'Our best:       {best_avg:.2f} ({best_name})')
    print(f'Gap to James:   {best_avg - 22.02:.2f}')

    if best_avg < 22.02:
        print('\n>>> WE MOGGED JAMES <<<')
    elif best_avg < 32.99:
        print(f'\n>>> Better than old Ridge ({32.99:.2f}) <<<')

    return results


if __name__ == '__main__':
    use_wx = '--no-weather' not in sys.argv
    benchmark(use_weather=use_wx)
