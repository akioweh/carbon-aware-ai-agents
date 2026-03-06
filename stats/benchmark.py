#!/usr/bin/env python3
"""
Carbon Intensity Prediction Benchmark

Compares 9 forecasting models (5 statistical + 4 ML tree-based) across
7 metrics on real UK carbon intensity data. Supports 7-day and full backfill
training windows. Generates graphs and an auto-generated comparison report.

Usage:
    python benchmark.py                  # run with existing data
    python benchmark.py --backfill 90    # backfill 90 days first, then run
"""

import argparse
import sqlite3
import sys
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.dates import DateFormatter
import numpy as np
import pandas as pd
from scipy.signal import periodogram
from sklearn.linear_model import Ridge
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import acf

warnings.filterwarnings('ignore')

# ── Section 0: Config & CLI ─────────────────────────────────────────────

DB_PATH = Path(__file__).parent / 'carbon_intensity.db'
DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
TEST_DAYS = 7

MODEL_NAMES = [
    'Ridge', 'SARIMAX', 'Seasonal Naive', 'Fourier', 'Holt-Winters',
    'Random Forest', 'XGBoost', 'CatBoost', 'LightGBM',
]

MODEL_COLORS = {
    'Ridge':          '#F44336',
    'SARIMAX':        '#4CAF50',
    'Seasonal Naive': '#9C27B0',
    'Fourier':        '#FF9800',
    'Holt-Winters':   '#00BCD4',
    'Random Forest':  '#795548',
    'XGBoost':        '#E91E63',
    'CatBoost':       '#3F51B5',
    'LightGBM':       '#8BC34A',
}

MODEL_LINESTYLES = {
    'Ridge':          '--',
    'SARIMAX':        '-.',
    'Seasonal Naive': ':',
    'Fourier':        '--',
    'Holt-Winters':   '-.',
    'Random Forest':  '-',
    'XGBoost':        '-',
    'CatBoost':       '-',
    'LightGBM':       '-',
}


def parse_args():
    parser = argparse.ArgumentParser(description='Carbon Intensity Prediction Benchmark')
    parser.add_argument('--backfill', type=int, default=0,
                        help='Backfill N days of data from UK Carbon Intensity API before running')
    return parser.parse_args()


# ── Section 1: Data Loading ─────────────────────────────────────────────

def load_data(db_path: Path) -> pd.DataFrame:
    """Load carbon intensity readings from SQLite, deduplicate, return DataFrame."""
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
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


# ── Section 2: Feature Engineering ───────────────────────────────────────

def build_cyclical_features(timestamps: pd.Series) -> pd.DataFrame:
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
    model = Ridge(alpha=1.0)
    model.fit(X_train, train_y)
    X_test = build_cyclical_features(test_ts)
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
    coeffs, _, _, _ = np.linalg.lstsq(X_train, train_y, rcond=None)
    X_test = _build_fourier_X(test_ts, ref_start)
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


def _walk_forward_tree(model, train_ts, train_y, test_ts, test_y_actual):
    """Walk-forward evaluation for tree models.

    Train once on training set. At each test step t, build lag features
    from actual values (train tail + test[:t]), predict step t.
    """
    n_train = len(train_y)
    n_test = len(test_ts)
    n_lags = 48

    # Combine train + test actuals for lag lookback
    all_values = np.concatenate([train_y, test_y_actual])
    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)

    # Build training features
    train_features = build_ml_features(train_ts, train_y)
    # Drop rows with NaN from lag features
    valid_mask = train_features.notna().all(axis=1)
    X_train = train_features[valid_mask].values
    y_train = train_y[valid_mask.values]

    model.fit(X_train, y_train)

    # Predict each test step using actual history for lags
    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        # Build features for this single step
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_cyclical_features(ts_point)

        # Lag features from actual history
        lag_feats = {}
        for lag in range(1, n_lags + 1):
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = all_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan
        # Rolling means
        for window, name in [(12, 'rolling_mean_6h'), (24, 'rolling_mean_12h'), (48, 'rolling_mean_24h')]:
            start = max(0, idx - 1 - window + 1)
            end = idx  # exclusive, so up to idx-1
            if end > start:
                lag_feats[name] = np.mean(all_values[start:end])
            else:
                lag_feats[name] = np.nan

        lag_df = pd.DataFrame([lag_feats])
        x_step = pd.concat([cyclical.reset_index(drop=True), lag_df.reset_index(drop=True)], axis=1)
        preds[t] = model.predict(x_step.values)[0]

    return np.clip(preds, 0, 500)


def train_predict_random_forest(train_ts, train_y, test_ts, test_y=None, **kw):
    from sklearn.ensemble import RandomForestRegressor
    t0 = time.time()
    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _walk_forward_tree(model, train_ts, train_y, test_ts, test_y)
    return preds, time.time() - t0


def train_predict_xgboost(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor
    t0 = time.time()
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1,
                         random_state=42, verbosity=0, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _walk_forward_tree(model, train_ts, train_y, test_ts, test_y)
    return preds, time.time() - t0


def train_predict_catboost(train_ts, train_y, test_ts, test_y=None, **kw):
    from catboost import CatBoostRegressor
    t0 = time.time()
    model = CatBoostRegressor(iterations=200, depth=6, learning_rate=0.1,
                              random_seed=42, verbose=0)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _walk_forward_tree(model, train_ts, train_y, test_ts, test_y)
    return preds, time.time() - t0


def train_predict_lightgbm(train_ts, train_y, test_ts, test_y=None, **kw):
    import lightgbm as lgb
    t0 = time.time()
    model = lgb.LGBMRegressor(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, verbose=-1, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = _walk_forward_tree(model, train_ts, train_y, test_ts, test_y)
    return preds, time.time() - t0


MODEL_FUNCS = {
    'Ridge':          train_predict_ridge,
    'SARIMAX':        train_predict_sarimax,
    'Seasonal Naive': train_predict_seasonal_naive,
    'Fourier':        train_predict_fourier,
    'Holt-Winters':   train_predict_holt_winters,
    'Random Forest':  train_predict_random_forest,
    'XGBoost':        train_predict_xgboost,
    'CatBoost':       train_predict_catboost,
    'LightGBM':       train_predict_lightgbm,
}


# ── Section 4: Metrics ──────────────────────────────────────────────────

def spectral_entropy(signal_values: np.ndarray) -> float:
    """Compute normalized spectral entropy of a signal.

    High entropy (close to 1) means residuals are like white noise (good).
    Low entropy means model missed periodic structure (bad).
    """
    if len(signal_values) < 4:
        return np.nan
    freqs, psd = periodogram(signal_values, detrend='constant')
    # Exclude DC component
    psd = psd[1:]
    if psd.sum() == 0:
        return 1.0
    psd_norm = psd / psd.sum()
    # Shannon entropy, normalized to [0, 1]
    entropy = -np.sum(psd_norm * np.log(psd_norm + 1e-12))
    max_entropy = np.log(len(psd_norm))
    if max_entropy == 0:
        return 1.0
    return float(entropy / max_entropy)


def kl_divergence_hist(p_values: np.ndarray, q_values: np.ndarray, n_bins: int = 50) -> float:
    """KL divergence between two distributions estimated via histograms.

    Uses Laplace smoothing to avoid infinities.
    Returns KL(p || q) where p = actual, q = predicted.
    """
    # Use common bin edges
    combined = np.concatenate([p_values, q_values])
    bins = np.linspace(combined.min() - 1, combined.max() + 1, n_bins + 1)

    p_hist, _ = np.histogram(p_values, bins=bins)
    q_hist, _ = np.histogram(q_values, bins=bins)

    # Laplace smoothing
    p_hist = (p_hist + 1).astype(float)
    q_hist = (q_hist + 1).astype(float)
    p_dist = p_hist / p_hist.sum()
    q_dist = q_hist / q_hist.sum()

    return float(np.sum(p_dist * np.log(p_dist / q_dist)))


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, n_features: int = 0) -> dict:
    """Compute all 7 benchmark metrics."""
    residuals = y_true - y_pred
    n = len(y_true)

    mae = float(np.mean(np.abs(residuals)))
    mse = float(np.mean(residuals ** 2))
    rmse = float(np.sqrt(mse))

    ss_res = np.sum(residuals ** 2)
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

    se = spectral_entropy(residuals)
    kl = kl_divergence_hist(y_true, y_pred)

    return {
        'MAE': mae,
        'MSE': mse,
        'RMSE': rmse,
        'R2': r2,
        'Adj_R2': adj_r2,
        'Spectral_Entropy': se,
        'KL_Divergence': kl,
    }


# Feature count approximations for adjusted R-squared
MODEL_N_FEATURES = {
    'Ridge': 6,
    'SARIMAX': 6,
    'Seasonal Naive': 0,
    'Fourier': 11,
    'Holt-Winters': 3,
    'Random Forest': 57,
    'XGBoost': 57,
    'CatBoost': 57,
    'LightGBM': 57,
}


# ── Section 5: Experiment Runner ─────────────────────────────────────────

def run_experiment(region: str, train_df: pd.DataFrame, test_df: pd.DataFrame,
                   exp_name: str) -> dict:
    """Run all 9 models on one region/training-window combo."""
    results = {}
    train_ts = train_df['ts'].reset_index(drop=True)
    train_y = train_df['actual'].values
    test_ts = test_df['ts'].reset_index(drop=True)
    test_y = test_df['actual'].values

    for model_name in MODEL_NAMES:
        print(f"    {model_name}...", end=' ', flush=True)
        func = MODEL_FUNCS[model_name]
        try:
            preds, elapsed = func(
                train_ts=train_ts,
                train_y=train_y,
                test_ts=test_ts,
                test_y=test_y,
            )
            # Ensure prediction length matches test
            if len(preds) != len(test_y):
                min_len = min(len(preds), len(test_y))
                preds = preds[:min_len]
                test_y_eval = test_y[:min_len]
            else:
                test_y_eval = test_y

            metrics = compute_metrics(test_y_eval, preds, n_features=MODEL_N_FEATURES[model_name])
            print(f"MAE={metrics['MAE']:.2f}  ({elapsed:.2f}s)")
            results[model_name] = {
                'preds': preds,
                'metrics': metrics,
                'time': elapsed,
            }
        except Exception as e:
            print(f"FAILED: {e}")
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
    print(f"  Saved: {path}")


def plot_predictions(all_results: dict, regions: list, window_name: str,
                     test_dfs: dict):
    """Overlay all model predictions on actual for each region."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return
    fig, axes = plt.subplots(len(active_regions), 1,
                             figsize=(18, 4.5 * len(active_regions)), sharex=True)
    if len(active_regions) == 1:
        axes = [axes]

    for ax, region in zip(axes, active_regions):
        res = all_results[region][window_name]
        test = test_dfs[region]
        ax.plot(test['ts'].values, test['actual'].values,
                linewidth=1.5, color='#2196F3', label='Actual', zorder=10)

        for model_name in MODEL_NAMES:
            if res.get(model_name) is None:
                continue
            r = res[model_name]
            preds = r['preds']
            ts = test['ts'].values[:len(preds)]
            mae = r['metrics']['MAE']
            ax.plot(ts, preds, linewidth=0.9,
                    color=MODEL_COLORS[model_name],
                    linestyle=MODEL_LINESTYLES[model_name],
                    label=f"{model_name} ({mae:.1f})", alpha=0.8)

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
    print(f"  Saved: {path}")


def plot_zoom_48h(all_results: dict, regions: list, window_name: str,
                  test_dfs: dict):
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

    fig, axes = plt.subplots(len(active_regions), 1,
                             figsize=(16, 4 * len(active_regions)), sharex=False)
    if len(active_regions) == 1:
        axes = [axes]

    for ax, region in zip(axes, active_regions):
        res = all_results[region][window_name]
        test = test_dfs[region]
        n_48h = min(96, len(test))  # 48h at 30min intervals

        ax.plot(test['ts'].values[:n_48h], test['actual'].values[:n_48h],
                linewidth=2, color='#2196F3', label='Actual', zorder=10)

        for model_name in top5:
            if res.get(model_name) is None:
                continue
            r = res[model_name]
            preds = r['preds'][:n_48h]
            ts = test['ts'].values[:len(preds)]
            mae = r['metrics']['MAE']
            ax.plot(ts, preds, linewidth=1.2,
                    color=MODEL_COLORS[model_name],
                    linestyle=MODEL_LINESTYLES[model_name],
                    label=f"{model_name} ({mae:.1f})")

        ax.set_ylabel('gCO2/kWh')
        ax.set_title(f"{region} — First 48 Hours")
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(DateFormatter('%b %d %H:%M'))

    wlabel = window_name.replace(' ', '_').lower()
    fig.suptitle(f'48-Hour Detail — {window_name} (Top 5 Models)', fontsize=14, y=1.01)
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_zoom_48h_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_heatmap(all_results: dict, regions: list, window_name: str):
    """Metrics heatmap: Models x Metrics, averaged across regions."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return

    metric_names = ['MAE', 'MSE', 'RMSE', 'R2', 'Adj_R2', 'Spectral_Entropy', 'KL_Divergence']
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

    fig, ax = plt.subplots(figsize=(12, max(4, len(active_models) * 0.7)))
    im = ax.imshow(data_arr, cmap='RdYlGn_r', aspect='auto')

    ax.set_xticks(range(len(metric_names)))
    ax.set_xticklabels(metric_names, rotation=45, ha='right', fontsize=9)
    ax.set_yticks(range(len(active_models)))
    ax.set_yticklabels(active_models, fontsize=9)

    # Annotate cells
    for i in range(len(active_models)):
        for j in range(len(metric_names)):
            val = data_arr[i, j]
            if np.isfinite(val):
                text = f"{val:.2f}" if abs(val) < 100 else f"{val:.0f}"
                ax.text(j, i, text, ha='center', va='center', fontsize=7,
                        color='white' if abs(val) > np.nanmedian(data_arr) else 'black')

    fig.colorbar(im, ax=ax, shrink=0.8)
    wlabel = window_name.replace(' ', '_').lower()
    ax.set_title(f'Metrics Heatmap — {window_name} (Averaged Across Regions)')
    fig.tight_layout()
    path = DOCS_DIR / f'benchmark_heatmap_{wlabel}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {path}")


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

    active_models = [m for m in MODEL_NAMES
                     if any(m in model_window_mae[w] for w in windows)]
    if not active_models:
        return

    x = np.arange(len(active_models))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, window_name in enumerate(windows):
        vals = [model_window_mae[window_name].get(m, 0) for m in active_models]
        offset = (i - (len(windows) - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=window_name,
                      color=f'C{i}', alpha=0.8)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                        f'{val:.1f}', ha='center', va='bottom', fontsize=7)

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
    print(f"  Saved: {path}")


def plot_residuals(all_results: dict, regions: list, window_name: str,
                   test_dfs: dict):
    """Spectral entropy bar chart + residual ACF for top models."""
    active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
    if not active_regions:
        return

    # Average spectral entropy per model
    model_se = {}
    for model_name in MODEL_NAMES:
        ses = []
        for region in active_regions:
            res = all_results[region][window_name]
            if res.get(model_name) is not None:
                v = res[model_name]['metrics']['Spectral_Entropy']
                if np.isfinite(v):
                    ses.append(v)
        if ses:
            model_se[model_name] = np.mean(ses)

    if not model_se:
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

    # Bar chart of spectral entropy
    sorted_models = sorted(model_se, key=model_se.get, reverse=True)
    colors = [MODEL_COLORS.get(m, 'gray') for m in sorted_models]
    ax1.barh(range(len(sorted_models)),
             [model_se[m] for m in sorted_models],
             color=colors, alpha=0.8)
    ax1.set_yticks(range(len(sorted_models)))
    ax1.set_yticklabels(sorted_models, fontsize=9)
    ax1.set_xlabel('Spectral Entropy (higher = better)')
    ax1.set_title('Residual Spectral Entropy')
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
            residuals = test_y[:len(preds)] - preds
            acf_vals = acf(residuals, nlags=n_lags_acf, fft=True)
            ax2.plot(range(n_lags_acf + 1), acf_vals,
                     color=MODEL_COLORS[model_name],
                     label=model_name, linewidth=1.2)
        ax2.axhline(0, color='gray', linewidth=0.5)
        ax2.axhline(1.96 / np.sqrt(len(test_y)), color='gray', linestyle='--',
                     linewidth=0.5, alpha=0.5)
        ax2.axhline(-1.96 / np.sqrt(len(test_y)), color='gray', linestyle='--',
                     linewidth=0.5, alpha=0.5)
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
    print(f"  Saved: {path}")


# ── Section 7: Report Generation ─────────────────────────────────────────

def generate_report(all_results: dict, regions: list, data_info: dict,
                    windows: list) -> str:
    """Generate markdown report from benchmark results."""
    lines = []
    lines.append("# Carbon Intensity Prediction Benchmark")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(
        "This report compares 9 forecasting models (5 statistical + 4 ML tree-based) "
        "on real UK carbon intensity data (gCO2/kWh). Models are evaluated on 7 metrics "
        "that measure both point accuracy and shape capture. The benchmark tests different "
        "training window sizes to assess the effect of data volume on prediction quality."
    )
    lines.append("")

    # Test setup
    lines.append("## Test Setup")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| **Data source** | `carbon_intensity.db` (UK Carbon Intensity API) |")
    lines.append(f"| **Regions** | {', '.join(regions)} |")
    lines.append(f"| **Date range** | {data_info['date_min']} to {data_info['date_max']} |")
    lines.append(f"| **Total readings** | {data_info['total_rows']} |")
    lines.append(f"| **Frequency** | 30-minute intervals |")
    lines.append(f"| **Test set** | Last {TEST_DAYS} days |")
    for w in windows:
        lines.append(f"| **Training ({w})** | {data_info.get(f'train_info_{w}', 'N/A')} |")
    lines.append("")

    # Raw data graph
    lines.append("## Raw Data")
    lines.append("")
    lines.append("![Raw Data](benchmark_raw_data.png)")
    lines.append("")

    # Metrics explanation
    lines.append("## Metrics Explained")
    lines.append("")
    lines.append("| Metric | Purpose |")
    lines.append("|--------|---------|")
    lines.append("| **MAE** | Mean Absolute Error — primary accuracy in gCO2/kWh |")
    lines.append("| **MSE** | Mean Squared Error — penalizes large errors quadratically |")
    lines.append("| **RMSE** | Root MSE — same scale as MAE, sensitive to outliers |")
    lines.append("| **R-squared** | Fraction of variance explained; negative = worse than predicting the mean |")
    lines.append("| **Adjusted R-squared** | R-squared penalized by number of model features |")
    lines.append(
        "| **Spectral Entropy** | Entropy of residual periodogram, scaled to [0,1]. "
        "High = residuals are white noise (good). Low = model missed periodic structure |"
    )
    lines.append(
        "| **KL Divergence** | KL divergence between actual and predicted distributions. "
        "Low = predictions distribution matches actual. High = model distorts the shape |"
    )
    lines.append("")

    # Results per window
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f"## Results: {window_name}")
        lines.append("")

        # Accuracy table
        lines.append("### Accuracy Table")
        lines.append("")
        metric_cols = ['MAE', 'RMSE', 'R2', 'Spectral_Entropy', 'KL_Divergence']
        header = "| Model | " + " | ".join(metric_cols) + " | Time (s) |"
        sep = "|-------|" + "|".join(["-------"] * len(metric_cols)) + "|----------|"
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
                    vals_str.append("N/A")
                elif abs(v) < 10:
                    vals_str.append(f"{v:.3f}")
                else:
                    vals_str.append(f"{v:.2f}")

            t_str = f"{np.mean(avg_time):.2f}" if avg_time else "N/A"
            row = f"| {model_name} | " + " | ".join(vals_str) + f" | {t_str} |"
            lines.append(row)

        lines.append("")
        lines.append(f"*Averaged across {len(active_regions)} regions. Lower MAE/RMSE/KL is better. Higher R2/Spectral Entropy is better.*")
        lines.append("")

        # Graphs
        lines.append("### Predictions vs Actual")
        lines.append("")
        lines.append(f"![Predictions {window_name}](benchmark_predictions_{wlabel}.png)")
        lines.append("")
        lines.append("### Zoomed 48-Hour Detail")
        lines.append("")
        lines.append(f"![48h Detail {window_name}](benchmark_zoom_48h_{wlabel}.png)")
        lines.append("")

    # Training comparison
    if len(windows) > 1:
        lines.append("## Training Data Volume Comparison")
        lines.append("")
        lines.append("![Training Comparison](benchmark_training_comparison.png)")
        lines.append("")
        lines.append(
            "This chart compares MAE across training windows. Models that improve "
            "significantly with more data have learned meaningful temporal patterns. "
            "Models that stay flat or get worse may be overfitting or are insensitive "
            "to training volume."
        )
        lines.append("")

    # Residual analysis
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f"## Residual Analysis — {window_name}")
        lines.append("")
        lines.append(f"![Residuals {window_name}](benchmark_residuals_{wlabel}.png)")
        lines.append("")
        lines.append(
            "**Spectral Entropy** near 1.0 means the model's residuals look like white noise — "
            "it captured all the periodic structure in the data. Values below 0.8 suggest the model "
            "missed recurring patterns. The **ACF plot** shows autocorrelation in residuals; "
            "significant spikes at lag 48 (1 day) or lag 336 (1 week) indicate unmodelled seasonality."
        )
        lines.append("")

    # Heatmaps
    for window_name in windows:
        wlabel = window_name.replace(' ', '_').lower()
        lines.append(f"## Metrics Heatmap — {window_name}")
        lines.append("")
        lines.append(f"![Heatmap {window_name}](benchmark_heatmap_{wlabel}.png)")
        lines.append("")

    # Model details
    lines.append("## Model Details")
    lines.append("")
    lines.append("### Statistical Models")
    lines.append("")
    lines.append(
        "- **Ridge Regression**: Ridge(alpha=1.0) with cyclical sin/cos features for hour, "
        "day-of-week, minute-of-day. Fast, interpretable, but limited to capturing smooth seasonality."
    )
    lines.append(
        "- **SARIMAX**: SARIMAX(1,0,1)(1,0,1,48) with training capped at 14 days. "
        "Captures autoregressive momentum and seasonal patterns. Slower to fit."
    )
    lines.append(
        "- **Seasonal Naive**: Repeats the last 7 days of training data. Zero parameters, "
        "instant. Strong baseline when weekly patterns dominate."
    )
    lines.append(
        "- **Fourier Regression**: 3 daily + 2 weekly harmonics solved via OLS (numpy.linalg.lstsq). "
        "Prophet's core math without the overhead."
    )
    lines.append(
        "- **Holt-Winters**: Triple exponential smoothing with additive trend and seasonality "
        "(seasonal_periods=48). Struggles with noisy, multi-seasonal data."
    )
    lines.append("")
    lines.append("### ML Tree-Based Models")
    lines.append("")
    lines.append(
        "- **Random Forest**: RF(n_estimators=200, max_depth=15) with lag + cyclical features. "
        "Walk-forward evaluation using actual history for lag computation."
    )
    lines.append(
        "- **XGBoost**: XGB(n_estimators=200, max_depth=6, lr=0.1). Gradient-boosted trees "
        "with the same feature set and walk-forward evaluation."
    )
    lines.append(
        "- **CatBoost**: CB(iterations=200, depth=6, lr=0.1). Ordered boosting with "
        "symmetric trees. Walk-forward evaluation."
    )
    lines.append(
        "- **LightGBM**: LGBM(n_estimators=200, max_depth=6, lr=0.1). Histogram-based "
        "gradient boosting. Walk-forward evaluation."
    )
    lines.append("")

    # Key findings
    lines.append("## Key Findings")
    lines.append("")

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
            lines.append(f"**{window_name}** — Top 3 by MAE:")
            for i, m in enumerate(sorted_models[:3]):
                lines.append(f"{i+1}. {m}: MAE = {best_mae[m]:.2f} gCO2/kWh")
            lines.append("")

    lines.append(
        "**Shape capture**: Models with high spectral entropy and low KL divergence "
        "capture the shape of carbon intensity better, not just minimizing mean error. "
        "Tree-based models with lag features tend to score well here because they can "
        "replicate recent patterns."
    )
    lines.append("")
    lines.append(
        "**Training volume effect**: More training data generally helps autoregressive "
        "models (SARIMAX, tree models) but has diminishing returns for models that only "
        "use time-of-day features (Ridge, Fourier)."
    )
    lines.append("")
    lines.append(
        "**Speed/accuracy tradeoffs**: Ridge and Fourier are near-instant. SARIMAX and "
        "tree models take seconds. For production use, the best model depends on whether "
        "you need sub-second predictions or can afford batch computation."
    )
    lines.append("")

    # Methodology
    lines.append("## Methodology Notes")
    lines.append("")
    lines.append(
        "- **Walk-forward evaluation** for tree models: trained once, then at each test step "
        "lag features are built from actual historical values (not predictions). This simulates "
        "production usage where recent actuals are available."
    )
    lines.append(
        "- **SARIMAX training cap**: Limited to 14 days to avoid excessive fit time. "
        "This is consistent with the production predictor."
    )
    lines.append(
        "- **No hyperparameter tuning**: All models use reasonable defaults. Results could "
        "improve with tuning, but the comparison is fair since no model was optimized."
    )
    lines.append(
        "- **Spectral entropy**: Computed from the periodogram of residuals, normalized to [0,1]. "
        "Shannon entropy of the normalized power spectral density."
    )
    lines.append(
        "- **KL divergence**: Histogram-based (50 bins) with Laplace smoothing. Measures "
        "distributional similarity between actual and predicted values."
    )
    lines.append("")

    return "\n".join(lines)


# ── Section 8: Main ─────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Optionally backfill
    if args.backfill > 0:
        print(f"Backfilling {args.backfill} days of data...")
        from carbon_collector import init_database, backfill
        conn = init_database(DB_PATH)
        backfill(conn, args.backfill)
        conn.close()
        print()

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f"Regions: {regions}")
    print(f"Date range: {df['ts'].min()} -> {df['ts'].max()}")
    print(f"Total rows: {len(df)}")

    total_days = (df['ts'].max() - df['ts'].min()).days
    print(f"Total span: {total_days} days")

    if total_days < 14:
        print(f"\nWARNING: Only {total_days} days of data. Need >= 14 days for meaningful "
              "full backfill experiment. Use --backfill N to collect more data.")

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
    print("\nGenerating raw data plot...")
    plot_raw_data(df, regions)

    # Run experiments
    all_results = {}
    test_dfs = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f"\n{region}: no test data, skipping")
            continue

        test_dfs[region] = test
        all_results[region] = {}

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

            if len(train) < 48:
                print(f"\n{region} [{window_name}]: insufficient training data ({len(train)} points), skipping")
                continue

            train_days = (train['ts'].max() - train['ts'].min()).days
            data_info[f'train_info_{window_name}'] = f"{len(train)} points ({train_days} days)"
            print(f"\n{'='*60}")
            print(f"  {region} [{window_name}]: train={len(train)} ({train_days}d), test={len(test)}")
            print(f"{'='*60}")

            all_results[region][window_name] = run_experiment(region, train, test, window_name)

    # Generate graphs
    window_names = [w[0] for w in windows]
    print("\nGenerating graphs...")

    for window_name in window_names:
        plot_predictions(all_results, regions, window_name, test_dfs)
        plot_zoom_48h(all_results, regions, window_name, test_dfs)
        plot_heatmap(all_results, regions, window_name)
        plot_residuals(all_results, regions, window_name, test_dfs)

    if len(window_names) > 1:
        plot_training_comparison(all_results, regions, window_names)

    # Generate report
    print("\nGenerating report...")
    report = generate_report(all_results, regions, data_info, window_names)
    report_path = DOCS_DIR / 'comparison_report.md'
    report_path.write_text(report)
    print(f"  Saved: {report_path}")

    # Summary
    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)

    for window_name in window_names:
        print(f"\n--- {window_name} ---")
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
                marker = " <-- best" if i == 0 else ""
                print(f"  {i+1:2d}. {m:<20s} MAE={model_maes[m]:6.2f}{marker}")

    print(f"\nReport: {DOCS_DIR / 'comparison_report.md'}")
    print(f"Graphs: {DOCS_DIR}/benchmark_*.png")


if __name__ == '__main__':
    main()
