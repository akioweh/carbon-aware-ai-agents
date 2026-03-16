#!/usr/bin/env python3
"""
Enhanced Tree Features Experiment.

Tests improved feature engineering for tree-based models:
  1. Sparse lag structure (19 lags vs 48) with weekly periodicity
  2. Enhanced rolling stats (mean + std at 12, 48, 336 windows)
  3. Week-of-year cyclical features (replacing minute-of-day)
  4. Extended Direct-XGBoost origin summary (lag_48, lag_336, rolling_mean/std_336)

Compares against baseline tree results from tree_results.json.

Usage:
    python3 benchmark_enhanced_features.py
"""

import json
import sys
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

from benchmark import (
    DB_PATH, TEST_DAYS, WEATHER_FEATURES,
    load_data, fetch_weather_data,
    compute_metrics,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
TREE_RESULTS_PATH = Path(__file__).parent / 'tree_results.json'

ENHANCED_MODELS = ['Random Forest', 'XGBoost', 'CatBoost', 'LightGBM', 'Direct-XGBoost']

# Feature counts
ENHANCED_N_FEATURES = {
    'Random Forest': 33,   # 6 cyclical + 19 lags + 5 rolling + 3 weather
    'XGBoost': 33,
    'CatBoost': 33,
    'LightGBM': 33,
    'Direct-XGBoost': 18,  # 6 cyclical + 2 horizon + 3 existing origin + 4 new origin + 3 weather
}

# Sparse lag indices: 1-12 + key multiples for daily/weekly periodicity
SPARSE_LAGS = list(range(1, 13)) + [24, 48, 72, 96, 144, 336]

# Rolling window configs: (window_size, stat_type)
ROLLING_CONFIGS = [
    (12, 'mean'),    # 6 hours
    (48, 'mean'),    # 24 hours
    (336, 'mean'),   # 1 week
    (48, 'std'),     # 24 hours std
    (336, 'std'),    # 1 week std
]


# ── Enhanced Feature Engineering ─────────────────────────────────────────

def build_enhanced_cyclical(timestamps: pd.Series) -> pd.DataFrame:
    """Build sin/cos features for hour, day-of-week, and week-of-year."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    week_of_year = ts.dt.isocalendar().week.astype(float).values
    return pd.DataFrame({
        'hour_sin': np.sin(2 * np.pi * hour / 24),
        'hour_cos': np.cos(2 * np.pi * hour / 24),
        'dow_sin':  np.sin(2 * np.pi * dow / 7),
        'dow_cos':  np.cos(2 * np.pi * dow / 7),
        'week_sin': np.sin(2 * np.pi * week_of_year / 52),
        'week_cos': np.cos(2 * np.pi * week_of_year / 52),
    })


def build_enhanced_lag_features(series: np.ndarray) -> pd.DataFrame:
    """Build sparse lags + rolling mean/std features."""
    s = pd.Series(series)
    features = {}
    for lag in SPARSE_LAGS:
        features[f'lag_{lag}'] = s.shift(lag)
    for window, stat in ROLLING_CONFIGS:
        shifted = s.shift(1)
        if stat == 'mean':
            features[f'rolling_mean_{window}'] = shifted.rolling(window, min_periods=1).mean()
        else:
            features[f'rolling_std_{window}'] = shifted.rolling(window, min_periods=1).std().fillna(0)
    return pd.DataFrame(features)


def build_enhanced_ml_features(timestamps: pd.Series, values: np.ndarray) -> pd.DataFrame:
    """Combine enhanced cyclical + enhanced lag features."""
    cyclical = build_enhanced_cyclical(timestamps).reset_index(drop=True)
    lags = build_enhanced_lag_features(values).reset_index(drop=True)
    return pd.concat([cyclical, lags], axis=1)


def recursive_forecast_enhanced(model, train_ts, train_y, test_ts, test_y_actual,
                                train_exog=None, test_exog=None):
    """Recursive multi-step forecast with enhanced features."""
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)
    known_values = list(train_y)

    # Build training features
    train_features = build_enhanced_ml_features(train_ts, train_y)
    valid_mask = train_features.notna().all(axis=1)
    X_train = train_features[valid_mask].values
    if has_exog:
        X_train = np.column_stack([X_train, train_exog[valid_mask.values]])
    y_train = train_y[valid_mask.values]

    model.fit(X_train, y_train)

    # Predict each test step
    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_enhanced_cyclical(ts_point)

        # Sparse lag features
        lag_feats = {}
        for lag in SPARSE_LAGS:
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = known_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan

        # Rolling stats
        for window, stat in ROLLING_CONFIGS:
            start = max(0, idx - 1 - window + 1)
            end = idx  # exclusive
            if end > start:
                segment = known_values[start:end]
                if stat == 'mean':
                    lag_feats[f'rolling_mean_{window}'] = np.mean(segment)
                else:
                    lag_feats[f'rolling_std_{window}'] = np.std(segment) if len(segment) > 1 else 0.0
            else:
                key = f'rolling_mean_{window}' if stat == 'mean' else f'rolling_std_{window}'
                lag_feats[key] = np.nan

        lag_df = pd.DataFrame([lag_feats])
        x_step = pd.concat([cyclical.reset_index(drop=True), lag_df.reset_index(drop=True)], axis=1)
        if has_exog:
            x_step = np.column_stack([x_step.values, test_exog[t:t+1]])
        else:
            x_step = x_step.values
        pred = model.predict(x_step)[0]
        preds[t] = pred
        known_values.append(pred)

    return np.clip(preds, 0, 500)


def build_direct_features_enhanced(train_ts, train_y, test_ts,
                                   train_exog=None, test_exog=None):
    """Direct features with enhanced cyclical + extended origin summary."""
    n_test = len(test_ts)
    n_train = len(train_y)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 336  # need at least 1 week for lag_336
    max_h = min(n_test, 336)

    all_cyc = build_enhanced_cyclical(train_ts).values

    # Origin features: last, mean_48, std_48, lag_48, lag_336, mean_336, std_336
    origin_last = np.zeros(n_train)
    origin_mean_48 = np.zeros(n_train)
    origin_std_48 = np.zeros(n_train)
    origin_lag_48 = np.zeros(n_train)
    origin_lag_336 = np.zeros(n_train)
    origin_mean_336 = np.zeros(n_train)
    origin_std_336 = np.zeros(n_train)

    for t in range(min_history, n_train):
        recent_48 = train_y[max(0, t - 47):t + 1]
        recent_336 = train_y[max(0, t - 335):t + 1]
        origin_last[t] = train_y[t]
        origin_mean_48[t] = np.mean(recent_48)
        origin_std_48[t] = np.std(recent_48) if len(recent_48) > 1 else 0
        origin_lag_48[t] = train_y[t - 48] if t >= 48 else train_y[0]
        origin_lag_336[t] = train_y[t - 336] if t >= 336 else train_y[0]
        origin_mean_336[t] = np.mean(recent_336)
        origin_std_336[t] = np.std(recent_336) if len(recent_336) > 1 else 0

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
        of = np.column_stack([
            origin_last[origins], origin_mean_48[origins], origin_std_48[origins],
            origin_lag_48[origins], origin_lag_336[origins],
            origin_mean_336[origins], origin_std_336[origins],
        ])
        x = np.column_stack([cyc, h_col, h2_col, of])
        if has_exog:
            x = np.column_stack([x, train_exog[targets]])
        X_parts.append(x)
        y_parts.append(train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    # Test features
    test_cyc = build_enhanced_cyclical(test_ts).values
    recent_48 = train_y[-48:]
    recent_336 = train_y[-336:] if len(train_y) >= 336 else train_y
    of_test = np.array([[
        train_y[-1],
        np.mean(recent_48), np.std(recent_48),
        train_y[-48] if len(train_y) >= 48 else train_y[0],
        train_y[-336] if len(train_y) >= 336 else train_y[0],
        np.mean(recent_336), np.std(recent_336),
    ]])
    of_test = np.tile(of_test, (n_test, 1))
    h_vals = np.arange(1, n_test + 1).reshape(-1, 1) / 336.0
    X_test = np.column_stack([test_cyc, h_vals, h_vals ** 2, of_test])
    if has_exog:
        X_test = np.column_stack([X_test, test_exog])

    return X_train, y_train, X_test


# ── Model Runners ────────────────────────────────────────────────────────

def train_predict_rf_enhanced(train_ts, train_y, test_ts, test_y=None, **kw):
    from sklearn.ensemble import RandomForestRegressor
    t0 = time.time()
    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_enhanced(model, train_ts, train_y, test_ts, test_y,
                                        train_exog=kw.get('train_exog'),
                                        test_exog=kw.get('test_exog'))
    return preds, time.time() - t0


def train_predict_xgb_enhanced(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor
    t0 = time.time()
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1,
                         random_state=42, verbosity=0, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_enhanced(model, train_ts, train_y, test_ts, test_y,
                                        train_exog=kw.get('train_exog'),
                                        test_exog=kw.get('test_exog'))
    return preds, time.time() - t0


def train_predict_catboost_enhanced(train_ts, train_y, test_ts, test_y=None, **kw):
    from catboost import CatBoostRegressor
    t0 = time.time()
    model = CatBoostRegressor(iterations=200, depth=6, learning_rate=0.1,
                              random_seed=42, verbose=0)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_enhanced(model, train_ts, train_y, test_ts, test_y,
                                        train_exog=kw.get('train_exog'),
                                        test_exog=kw.get('test_exog'))
    return preds, time.time() - t0


def train_predict_lgbm_enhanced(train_ts, train_y, test_ts, test_y=None, **kw):
    import lightgbm as lgb
    t0 = time.time()
    model = lgb.LGBMRegressor(n_estimators=200, max_depth=6, learning_rate=0.1,
                              random_state=42, verbose=-1, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_enhanced(model, train_ts, train_y, test_ts, test_y,
                                        train_exog=kw.get('train_exog'),
                                        test_exog=kw.get('test_exog'))
    return preds, time.time() - t0


def train_predict_direct_xgb_enhanced(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor
    t0 = time.time()
    X, y, X_test = build_direct_features_enhanced(
        train_ts, train_y, test_ts,
        train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog'),
    )
    max_samples = 500_000
    if len(X) > max_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), max_samples, replace=False)
        X = X[idx]
        y = y[idx]
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1,
                         random_state=42, verbosity=0, n_jobs=-1)
    model.fit(X, y)
    preds = model.predict(X_test)
    return np.clip(preds, 0, 500), time.time() - t0


ENHANCED_FUNCS = {
    'Random Forest': train_predict_rf_enhanced,
    'XGBoost': train_predict_xgb_enhanced,
    'CatBoost': train_predict_catboost_enhanced,
    'LightGBM': train_predict_lgbm_enhanced,
    'Direct-XGBoost': train_predict_direct_xgb_enhanced,
}


# ── Visualization ────────────────────────────────────────────────────────

def generate_comparison_chart(baseline_maes, enhanced_maes, output_path):
    """Bar chart comparing baseline vs enhanced MAE per model."""
    models = list(baseline_maes.keys())
    x = np.arange(len(models))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width/2, [baseline_maes[m] for m in models], width, label='Baseline', color='#4a90d9')
    bars2 = ax.bar(x + width/2, [enhanced_maes[m] for m in models], width, label='Enhanced', color='#e74c3c')

    ax.set_xlabel('Model')
    ax.set_ylabel('MAE (gCO₂/kWh)')
    ax.set_title('Enhanced Tree Features: Baseline vs Enhanced MAE')
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=15, ha='right')
    ax.legend()

    # Add value labels on bars
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_predictions_chart(test_ts, test_y, all_preds, output_path):
    """Predictions vs actual for all enhanced models."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(test_ts, test_y, 'k-', linewidth=1.5, label='Actual', alpha=0.8)

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
    for (name, preds), color in zip(all_preds.items(), colors):
        ax.plot(test_ts[:len(preds)], preds, '-', color=color, linewidth=1, label=name, alpha=0.7)

    ax.set_xlabel('Time')
    ax.set_ylabel('Carbon Intensity (gCO₂/kWh)')
    ax.set_title('Enhanced Tree Features: Predictions vs Actual')
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


from matplotlib.dates import DateFormatter


# ── Report Generation ────────────────────────────────────────────────────

def generate_report(baseline_results, enhanced_results, output_path):
    """Generate markdown comparison report."""
    lines = [
        '# Enhanced Tree Features Experiment',
        '',
        '## Experiment Design',
        '',
        '### Changes from Baseline',
        '',
        '1. **Sparse lag structure**: lag_1..12 + 24,48,72,96,144,336 (19 lags vs 48)',
        '2. **Enhanced rolling stats**: mean at 12,48,336 + std at 48,336 (5 vs 3)',
        '3. **Week-of-year cyclical**: Replaced minute-of-day with week_of_year sin/cos',
        '4. **Extended Direct-XGBoost origin**: Added lag_48, lag_336, '
        'rolling_mean_336, rolling_std_336',
        '',
        '### Feature Counts',
        '',
        '| Model | Baseline | Enhanced |',
        '|-------|----------|----------|',
        '| Recursive trees | 63 (6 cyc + 48 lag + 3 roll + 3 weather + 3 roll) | '
        '33 (6 cyc + 19 lag + 5 roll + 3 weather) |',
        '| Direct-XGBoost | 14 (6 cyc + 2 h + 3 origin + 3 weather) | '
        '18 (6 cyc + 2 h + 7 origin + 3 weather) |',
        '',
        '## Results',
        '',
    ]

    # Build comparison table
    for window_name in ['Full backfill', '7-day']:
        has_data = False
        for region in enhanced_results:
            if window_name in enhanced_results[region]:
                has_data = True
                break
        if not has_data:
            continue

        lines.append(f'### {window_name} Training Window')
        lines.append('')

        # Per-region tables
        for region in sorted(enhanced_results.keys()):
            if window_name not in enhanced_results[region]:
                continue

            lines.append(f'#### {region}')
            lines.append('')
            lines.append('| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |')
            lines.append('|-------|-------------|-------------|-------|-----|')

            enh_data = enhanced_results[region][window_name]
            base_data = baseline_results.get(region, {}).get(window_name, {})

            for model_name in ENHANCED_MODELS:
                enh = enh_data.get(model_name)
                base = base_data.get(model_name)
                if enh is None:
                    continue
                enh_mae = enh['metrics']['MAE']
                if base is not None:
                    base_mae = base['metrics']['MAE']
                    delta = enh_mae - base_mae
                    pct = (delta / base_mae * 100) if base_mae > 0 else 0
                    sign = '+' if delta > 0 else ''
                    lines.append(
                        f'| {model_name} | {base_mae:.2f} | {enh_mae:.2f} | '
                        f'{sign}{delta:.2f} | {sign}{pct:.1f}% |'
                    )
                else:
                    lines.append(f'| {model_name} | N/A | {enh_mae:.2f} | — | — |')

            lines.append('')

        # Cross-region average
        lines.append(f'#### Cross-Region Average ({window_name})')
        lines.append('')
        lines.append('| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |')
        lines.append('|-------|-------------|-------------|-------|-----|')

        for model_name in ENHANCED_MODELS:
            base_maes = []
            enh_maes = []
            for region in enhanced_results:
                if window_name not in enhanced_results[region]:
                    continue
                enh = enhanced_results[region][window_name].get(model_name)
                base = baseline_results.get(region, {}).get(window_name, {}).get(model_name)
                if enh is not None:
                    enh_maes.append(enh['metrics']['MAE'])
                if base is not None:
                    base_maes.append(base['metrics']['MAE'])
            if enh_maes:
                avg_enh = np.mean(enh_maes)
                if base_maes:
                    avg_base = np.mean(base_maes)
                    delta = avg_enh - avg_base
                    pct = (delta / avg_base * 100) if avg_base > 0 else 0
                    sign = '+' if delta > 0 else ''
                    lines.append(
                        f'| {model_name} | {avg_base:.2f} | {avg_enh:.2f} | '
                        f'{sign}{delta:.2f} | {sign}{pct:.1f}% |'
                    )
                else:
                    lines.append(f'| {model_name} | N/A | {avg_enh:.2f} | — | — |')

        lines.append('')

    lines.append('## Analysis')
    lines.append('')
    lines.append('*Results above. Negative Δ MAE = improvement (enhanced is better).*')
    lines.append('')

    output_path.write_text('\n'.join(lines))
    print(f"Saved: {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    # Load baseline results
    baseline_results = {}
    if TREE_RESULTS_PATH.exists():
        baseline_results = json.loads(TREE_RESULTS_PATH.read_text())
        print(f"Loaded baseline results from {TREE_RESULTS_PATH}")
    else:
        print("WARNING: No baseline tree_results.json found — will only show enhanced results")

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f"Regions: {regions}")
    print(f"Date range: {df['ts'].min()} -> {df['ts'].max()}")

    total_days = (df['ts'].max() - df['ts'].min()).days

    # Fetch weather data
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print("\nFetching weather data...")
    weather_df = fetch_weather_data(regions, date_min, date_max)
    has_weather = len(weather_df) > 0
    if has_weather:
        print(f"Weather data: {len(weather_df)} points")
    else:
        print("WARNING: No weather data — running without exogenous features")

    # Full backfill only — enhanced features need lag_336 (1 week of history)
    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)

    windows = [('Full backfill', None)]

    # Run enhanced models
    all_results = {}
    all_preds_for_plot = {}  # last region's preds for visualization
    last_test_ts = None
    last_test_y = None

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f"\n{region}: no test data, skipping")
            continue

        all_results[region] = {}
        test_y = test['actual'].values

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

            if len(train) < 400:
                print(f"\n{region} [{window_name}]: insufficient training data ({len(train)} < 400), skipping")
                continue

            train_days = (train['ts'].max() - train['ts'].min()).days
            print(f"\n{'='*60}")
            print(f"  {region} [{window_name}]: train={len(train)} ({train_days}d), test={len(test)}")
            print(f"{'='*60}")

            # Build weather exogenous features
            train_exog = None
            test_exog = None
            if has_weather:
                rwx = weather_df[weather_df['region'] == region].sort_values('ts')
                if len(rwx) > 0:
                    combined = pd.concat([train, test]).reset_index(drop=True)
                    merged = combined.merge(rwx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
                    merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].interpolate(method='linear')
                    for feat in WEATHER_FEATURES:
                        merged[feat] = merged[feat].shift(1)
                    merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].fillna(0)
                    n_train = len(train)
                    train_exog = merged[WEATHER_FEATURES].iloc[:n_train].values
                    test_exog = merged[WEATHER_FEATURES].iloc[n_train:].values

            train_ts = train['ts'].reset_index(drop=True)
            train_y = train['actual'].values
            test_ts = test['ts'].reset_index(drop=True)

            results = {}
            for model_name in ENHANCED_MODELS:
                print(f"    {model_name}...", end=' ', flush=True)
                func = ENHANCED_FUNCS[model_name]
                try:
                    preds, elapsed = func(
                        train_ts=train_ts, train_y=train_y,
                        test_ts=test_ts, test_y=test_y,
                        train_exog=train_exog, test_exog=test_exog,
                    )
                    if len(preds) != len(test_y):
                        min_len = min(len(preds), len(test_y))
                        preds = preds[:min_len]
                        test_y_eval = test_y[:min_len]
                    else:
                        test_y_eval = test_y

                    metrics = compute_metrics(test_y_eval, preds,
                                              n_features=ENHANCED_N_FEATURES[model_name])
                    print(f"MAE={metrics['MAE']:.2f}  ({elapsed:.2f}s)")
                    results[model_name] = {
                        'preds': preds.tolist(),
                        'metrics': metrics,
                        'time': elapsed,
                    }

                    # Save for plotting (use Full backfill if available)
                    if window_name == 'Full backfill' or (window_name == '7-day' and model_name not in all_preds_for_plot):
                        all_preds_for_plot[model_name] = preds
                        last_test_ts = test_ts
                        last_test_y = test_y

                except Exception as e:
                    print(f"FAILED: {e}")
                    import traceback
                    traceback.print_exc()
                    results[model_name] = None

            all_results[region][window_name] = results

    # Save results
    results_path = Path(__file__).parent / 'enhanced_features_results.json'
    results_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nResults saved to {results_path}")

    # Generate visualizations
    print("\nGenerating visualizations...")

    # Comparison chart (cross-region average, prefer Full backfill)
    baseline_avg_maes = {}
    enhanced_avg_maes = {}
    preferred_window = 'Full backfill' if any(
        'Full backfill' in all_results.get(r, {}) for r in all_results
    ) else '7-day'

    for model_name in ENHANCED_MODELS:
        base_maes = []
        enh_maes = []
        for region in all_results:
            if preferred_window not in all_results[region]:
                continue
            enh = all_results[region][preferred_window].get(model_name)
            base = baseline_results.get(region, {}).get(preferred_window, {}).get(model_name)
            if enh is not None:
                enh_maes.append(enh['metrics']['MAE'])
            if base is not None:
                base_maes.append(base['metrics']['MAE'])
        if enh_maes:
            enhanced_avg_maes[model_name] = np.mean(enh_maes)
        if base_maes:
            baseline_avg_maes[model_name] = np.mean(base_maes)

    if baseline_avg_maes and enhanced_avg_maes:
        # Only plot models that have both baseline and enhanced
        common_models = set(baseline_avg_maes.keys()) & set(enhanced_avg_maes.keys())
        if common_models:
            b_maes = {m: baseline_avg_maes[m] for m in ENHANCED_MODELS if m in common_models}
            e_maes = {m: enhanced_avg_maes[m] for m in ENHANCED_MODELS if m in common_models}
            generate_comparison_chart(b_maes, e_maes,
                                     DOCS_DIR / 'benchmark_enhanced_features_comparison.png')

    if last_test_ts is not None and all_preds_for_plot:
        generate_predictions_chart(last_test_ts, last_test_y, all_preds_for_plot,
                                   DOCS_DIR / 'benchmark_enhanced_features_predictions.png')

    # Generate report
    generate_report(baseline_results, all_results,
                    DOCS_DIR / 'benchmark_enhanced_features.md')

    # Print summary
    print("\n" + "=" * 70)
    print("ENHANCED FEATURES EXPERIMENT COMPLETE")
    print("=" * 70)
    for window_name, _ in windows:
        print(f"\n--- {window_name} ---")
        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
        for model_name in ENHANCED_MODELS:
            enh_maes = []
            base_maes = []
            for region in active_regions:
                enh = all_results[region][window_name].get(model_name)
                base = baseline_results.get(region, {}).get(window_name, {}).get(model_name)
                if enh is not None:
                    enh_maes.append(enh['metrics']['MAE'])
                if base is not None:
                    base_maes.append(base['metrics']['MAE'])
            if enh_maes:
                avg_enh = np.mean(enh_maes)
                if base_maes:
                    avg_base = np.mean(base_maes)
                    delta = avg_enh - avg_base
                    sign = '+' if delta > 0 else ''
                    better = "✓ improved" if delta < 0 else "✗ worse"
                    print(f"   {model_name:20s} Enhanced={avg_enh:6.2f}  Baseline={avg_base:6.2f}  Δ={sign}{delta:.2f}  {better}")
                else:
                    print(f"   {model_name:20s} Enhanced={avg_enh:6.2f}  (no baseline)")


if __name__ == '__main__':
    main()
