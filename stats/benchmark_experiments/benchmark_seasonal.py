#!/usr/bin/env python3
"""
Seasonal Data Expansion + Best-Variant Assembly Experiment.

Expands from 90-day winter-only data to 1 year, assembles the best variant
per model from prior experiments (baseline, enhanced features, residual),
and adds seasonal feature engineering.

Best variant per model (cross-region avg MAE from prior experiments):
  - Random Forest:  residual    (MAE 46.61)
  - XGBoost:        enhanced    (MAE 35.44)
  - CatBoost:       residual    (MAE 41.04)
  - LightGBM:       enhanced    (MAE 39.12)
  - Direct-XGBoost: baseline    (MAE 33.50)

Usage:
    python3 benchmark_seasonal.py                              # default: full_year, no tuning
    python3 benchmark_seasonal.py --tune                       # with hyperparameter tuning
    python3 benchmark_seasonal.py --windows full_year 6_months 3_months
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

from benchmark import (
    DB_PATH, TEST_DAYS, WEATHER_FEATURES,
    load_data, fetch_weather_data,
    compute_metrics,
)
from benchmark_enhanced_features import (
    SPARSE_LAGS, ROLLING_CONFIGS,
    build_enhanced_cyclical, build_enhanced_lag_features,
)
from benchmark_residual import build_residual_training_data

DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
RESULTS_PATH = Path(__file__).parent / 'seasonal_results.json'
TUNED_PARAMS_PATH = Path(__file__).parent / 'seasonal_tuned_params.json'

MODELS = ['Random Forest', 'XGBoost', 'CatBoost', 'LightGBM', 'Direct-XGBoost']

# Best variant per model from prior experiments
BEST_VARIANTS = {
    'Random Forest':  'residual',
    'XGBoost':        'enhanced',
    'CatBoost':       'residual',
    'LightGBM':       'enhanced',
    'Direct-XGBoost': 'baseline',  # uses enhanced features, no residual target
}

# Extended sparse lags: original + 2-week and 4-week
SEASONAL_LAGS = SPARSE_LAGS + [672, 1344]

# Extended rolling configs: original + 2-week and 4-week windows
SEASONAL_ROLLING_CONFIGS = ROLLING_CONFIGS + [
    (672, 'mean'),    # 2 weeks
    (672, 'std'),     # 2 weeks std
    (1344, 'mean'),   # 4 weeks
]


# ── Seasonal Feature Engineering ─────────────────────────────────────────

def build_seasonal_cyclical(timestamps: pd.Series) -> pd.DataFrame:
    """Build 11 cyclical features: hour, dow, week, month, day-of-year, daylight proxy."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    week_of_year = ts.dt.isocalendar().week.astype(float).values
    month = ts.dt.month.astype(float)
    doy = ts.dt.dayofyear.astype(float)

    return pd.DataFrame({
        'hour_sin': np.sin(2 * np.pi * hour / 24),
        'hour_cos': np.cos(2 * np.pi * hour / 24),
        'dow_sin':  np.sin(2 * np.pi * dow / 7),
        'dow_cos':  np.cos(2 * np.pi * dow / 7),
        'week_sin': np.sin(2 * np.pi * week_of_year / 52),
        'week_cos': np.cos(2 * np.pi * week_of_year / 52),
        'month_sin': np.sin(2 * np.pi * month / 12),
        'month_cos': np.cos(2 * np.pi * month / 12),
        'doy_sin': np.sin(2 * np.pi * doy / 365.25),
        'doy_cos': np.cos(2 * np.pi * doy / 365.25),
        'daylight_proxy': np.sin((doy - 80) * 2 * np.pi / 365.25),
    })


def build_seasonal_lag_features(series: np.ndarray) -> pd.DataFrame:
    """Build seasonal sparse lags + rolling mean/std features."""
    s = pd.Series(series)
    features = {}
    for lag in SEASONAL_LAGS:
        features[f'lag_{lag}'] = s.shift(lag)
    for window, stat in SEASONAL_ROLLING_CONFIGS:
        shifted = s.shift(1)
        if stat == 'mean':
            features[f'rolling_mean_{window}'] = shifted.rolling(window, min_periods=1).mean()
        else:
            features[f'rolling_std_{window}'] = shifted.rolling(window, min_periods=1).std().fillna(0)
    return pd.DataFrame(features)


def build_seasonal_ml_features(timestamps: pd.Series, values: np.ndarray) -> pd.DataFrame:
    """Combine seasonal cyclical + seasonal lag features."""
    cyclical = build_seasonal_cyclical(timestamps).reset_index(drop=True)
    lags = build_seasonal_lag_features(values).reset_index(drop=True)
    return pd.concat([cyclical, lags], axis=1)


# ── Recursive Forecast (Seasonal, unified) ───────────────────────────────

def recursive_forecast_seasonal(model, train_ts, train_y, test_ts, test_y_actual,
                                train_exog=None, test_exog=None,
                                use_residual_target=False):
    """Recursive multi-step forecast with seasonal features.

    If use_residual_target=True: trains on y - lag_1, reconstructs raw.
    If False: trains on raw y (enhanced variant).
    """
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)
    known_values = list(train_y)

    # Build training features
    train_features = build_seasonal_ml_features(train_ts, train_y)

    if use_residual_target:
        X_train, y_train, _ = build_residual_training_data(train_features, train_y)
        if has_exog:
            valid_mask = train_features.notna().all(axis=1).values
            X_train = np.column_stack([X_train, train_exog[valid_mask]])
    else:
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
        cyclical = build_seasonal_cyclical(ts_point)

        # Sparse lag features
        lag_feats = {}
        for lag in SEASONAL_LAGS:
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = known_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan

        # Rolling stats
        for window, stat in SEASONAL_ROLLING_CONFIGS:
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

        if use_residual_target:
            residual = model.predict(x_step)[0]
            lag_1 = known_values[idx - 1]
            raw_pred = lag_1 + residual
            preds[t] = raw_pred
            known_values.append(raw_pred)
        else:
            pred = model.predict(x_step)[0]
            preds[t] = pred
            known_values.append(pred)

    return np.clip(preds, 0, 500)


# ── Direct Forecast (Seasonal, unified) ──────────────────────────────────

def build_direct_features_seasonal(train_ts, train_y, test_ts,
                                   train_exog=None, test_exog=None,
                                   use_residual_target=False):
    """Direct features with seasonal cyclical + extended origin summary."""
    n_test = len(test_ts)
    n_train = len(train_y)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 1344  # need at least 4 weeks for lag_1344
    max_h = min(n_test, 336)

    all_cyc = build_seasonal_cyclical(train_ts).values

    # Origin features
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
        if use_residual_target:
            y_parts.append(train_y[targets] - train_y[origins])
        else:
            y_parts.append(train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    # Test features
    test_cyc = build_seasonal_cyclical(test_ts).values
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

def _get_model_params(model_name, tuned_params=None):
    """Get model hyperparameters, using tuned params if available."""
    if tuned_params and model_name in tuned_params:
        return tuned_params[model_name]
    # Defaults
    defaults = {
        'Random Forest': dict(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1),
        'XGBoost': dict(n_estimators=200, max_depth=6, learning_rate=0.1,
                        random_state=42, verbosity=0, n_jobs=-1),
        'CatBoost': dict(iterations=200, depth=6, learning_rate=0.1,
                         random_seed=42, verbose=0),
        'LightGBM': dict(n_estimators=200, max_depth=6, learning_rate=0.1,
                         random_state=42, verbose=-1, n_jobs=-1),
        'Direct-XGBoost': dict(n_estimators=200, max_depth=6, learning_rate=0.1,
                               random_state=42, verbosity=0, n_jobs=-1),
    }
    return defaults[model_name]


def _create_model(model_name, params):
    """Create a model instance from name and params."""
    if model_name == 'Random Forest':
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(**params)
    elif model_name in ('XGBoost', 'Direct-XGBoost'):
        from xgboost import XGBRegressor
        return XGBRegressor(**params)
    elif model_name == 'CatBoost':
        from catboost import CatBoostRegressor
        return CatBoostRegressor(**params)
    elif model_name == 'LightGBM':
        import lightgbm as lgb
        return lgb.LGBMRegressor(**params)
    else:
        raise ValueError(f"Unknown model: {model_name}")


def train_predict_seasonal(model_name, train_ts, train_y, test_ts, test_y=None,
                           train_exog=None, test_exog=None, tuned_params=None):
    """Unified train/predict using the best variant for each model."""
    t0 = time.time()
    variant = BEST_VARIANTS[model_name]
    params = _get_model_params(model_name, tuned_params)

    if model_name == 'Direct-XGBoost':
        # Direct variant (baseline uses enhanced features, no residual)
        use_residual = (variant == 'residual')
        X, y, X_test = build_direct_features_seasonal(
            train_ts, train_y, test_ts,
            train_exog=train_exog, test_exog=test_exog,
            use_residual_target=use_residual,
        )
        max_samples = 500_000
        if len(X) > max_samples:
            rng = np.random.RandomState(42)
            idx = rng.choice(len(X), max_samples, replace=False)
            X = X[idx]
            y = y[idx]
        model = _create_model(model_name, params)
        model.fit(X, y)
        preds = model.predict(X_test)
        if use_residual:
            preds = train_y[-1] + preds
        return np.clip(preds, 0, 500), time.time() - t0
    else:
        # Recursive variant
        use_residual = (variant == 'residual')
        model = _create_model(model_name, params)
        if test_y is None:
            test_y = np.zeros(len(test_ts))
        preds = recursive_forecast_seasonal(
            model, train_ts, train_y, test_ts, test_y,
            train_exog=train_exog, test_exog=test_exog,
            use_residual_target=use_residual,
        )
        return preds, time.time() - t0


# ── Feature count for compute_metrics ────────────────────────────────────

N_FEATURES = {
    'Random Forest': 43,   # 11 cyclical + 21 lags + 8 rolling + 3 weather
    'XGBoost': 43,
    'CatBoost': 43,
    'LightGBM': 43,
    'Direct-XGBoost': 23,  # 11 cyclical + 2 horizon + 7 origin + 3 weather
}


# ── Hyperparameter Tuning ────────────────────────────────────────────────

def tune_model(model_name, train_ts, train_y, train_exog=None):
    """TimeSeriesSplit CV tuning with small grid. Returns best params dict."""
    from sklearn.model_selection import TimeSeriesSplit

    variant = BEST_VARIANTS[model_name]
    use_residual = (variant == 'residual')

    # Build features once
    features = build_seasonal_ml_features(train_ts, train_y)

    if use_residual:
        X_all, y_all, _ = build_residual_training_data(features, train_y)
        if train_exog is not None:
            valid_mask = features.notna().all(axis=1).values
            X_all = np.column_stack([X_all, train_exog[valid_mask]])
    else:
        valid_mask = features.notna().all(axis=1)
        X_all = features[valid_mask].values
        if train_exog is not None:
            X_all = np.column_stack([X_all, train_exog[valid_mask.values]])
        y_all = train_y[valid_mask.values]

    # Define parameter grids
    if model_name == 'Random Forest':
        param_grid = [
            dict(n_estimators=n, max_depth=d, random_state=42, n_jobs=-1)
            for n in [100, 200, 300]
            for d in [10, 15, 20]
        ]
    elif model_name == 'CatBoost':
        param_grid = [
            dict(iterations=n, depth=d, learning_rate=lr, random_seed=42, verbose=0)
            for n in [100, 200, 300]
            for d in [4, 6, 8]
            for lr in [0.05, 0.1]
        ]
    else:
        # XGBoost, LightGBM, Direct-XGBoost
        if model_name == 'LightGBM':
            param_grid = [
                dict(n_estimators=n, max_depth=d, learning_rate=lr,
                     random_state=42, verbose=-1, n_jobs=-1)
                for n in [100, 200, 300]
                for d in [4, 6, 8]
                for lr in [0.05, 0.1]
            ]
        else:
            param_grid = [
                dict(n_estimators=n, max_depth=d, learning_rate=lr,
                     random_state=42, verbosity=0, n_jobs=-1)
                for n in [100, 200, 300]
                for d in [4, 6, 8]
                for lr in [0.05, 0.1]
            ]

    tscv = TimeSeriesSplit(n_splits=3)
    best_mae = float('inf')
    best_params = param_grid[0]

    print(f"      Tuning {model_name} ({len(param_grid)} configs)...", end=' ', flush=True)
    t0 = time.time()

    for params in param_grid:
        fold_maes = []
        for train_idx, val_idx in tscv.split(X_all):
            model = _create_model(model_name, params)
            model.fit(X_all[train_idx], y_all[train_idx])
            preds = model.predict(X_all[val_idx])
            fold_maes.append(np.mean(np.abs(y_all[val_idx] - preds)))
        avg_mae = np.mean(fold_maes)
        if avg_mae < best_mae:
            best_mae = avg_mae
            best_params = params

    elapsed = time.time() - t0
    print(f"best MAE={best_mae:.2f} ({elapsed:.1f}s)")
    return best_params


# ── Training Window Logic ────────────────────────────────────────────────

def get_training_windows(df_region, split_date, requested_windows):
    """Return list of (window_name, train_df) for the requested windows."""
    windows = []
    for w in requested_windows:
        if w == 'full_year':
            train = df_region[df_region['ts'] <= split_date].reset_index(drop=True)
            if len(train) >= 400:
                windows.append(('full_year', train))
        elif w == '6_months':
            cutoff = split_date - pd.Timedelta(days=180)
            train = df_region[(df_region['ts'] > cutoff) & (df_region['ts'] <= split_date)].reset_index(drop=True)
            if len(train) >= 400:
                windows.append(('6_months', train))
        elif w == '3_months':
            cutoff = split_date - pd.Timedelta(days=90)
            train = df_region[(df_region['ts'] > cutoff) & (df_region['ts'] <= split_date)].reset_index(drop=True)
            if len(train) >= 400:
                windows.append(('3_months', train))
    return windows


# ── Visualization ────────────────────────────────────────────────────────

def generate_comparison_chart(results_by_window, output_path):
    """MAE bar chart per training window."""
    window_names = list(results_by_window.keys())
    n_windows = len(window_names)
    if n_windows == 0:
        return

    x = np.arange(len(MODELS))
    width = 0.8 / n_windows
    colors = ['#4a90d9', '#e74c3c', '#2ecc71', '#f39c12']

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, wname in enumerate(window_names):
        maes = [results_by_window[wname].get(m, 0) for m in MODELS]
        offset = (i - n_windows / 2 + 0.5) * width
        bars = ax.bar(x + offset, maes, width, label=wname, color=colors[i % len(colors)])
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3,
                        f'{h:.1f}', ha='center', va='bottom', fontsize=7)

    ax.set_xlabel('Model')
    ax.set_ylabel('MAE (gCO2/kWh)')
    ax.set_title('Seasonal Experiment: MAE by Training Window')
    ax.set_xticks(x)
    ax.set_xticklabels(MODELS, rotation=15, ha='right')
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_predictions_chart(test_ts, test_y, all_preds, output_path):
    """Predictions vs actual for all seasonal models."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(test_ts, test_y, 'k-', linewidth=1.5, label='Actual', alpha=0.8)

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
    for (name, preds), color in zip(all_preds.items(), colors):
        ax.plot(test_ts[:len(preds)], preds, '-', color=color, linewidth=1,
                label=name, alpha=0.7)

    ax.set_xlabel('Time')
    ax.set_ylabel('Carbon Intensity (gCO2/kWh)')
    ax.set_title('Seasonal Experiment: Predictions vs Actual')
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_importance_chart(importance_dicts, output_path):
    """Feature importance comparison for tree models."""
    n_models = len(importance_dicts)
    if n_models == 0:
        return

    fig, axes = plt.subplots(1, n_models, figsize=(7 * n_models, 6))
    if n_models == 1:
        axes = [axes]

    for ax, (model_name, imp) in zip(axes, importance_dicts.items()):
        sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:15]
        names = [n for n, _ in sorted_imp]
        vals = [v for _, v in sorted_imp]
        ax.barh(range(len(names)), vals, color='#3498db')
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel('Importance')
        ax.set_title(f'{model_name} (Seasonal)')
        ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def extract_feature_importance(model_name, train_ts, train_y, train_exog=None,
                               tuned_params=None):
    """Train model and return feature importances."""
    variant = BEST_VARIANTS[model_name]
    use_residual = (variant == 'residual')
    params = _get_model_params(model_name, tuned_params)

    train_features = build_seasonal_ml_features(train_ts, train_y)
    feature_names = list(train_features.columns)

    if use_residual:
        X_train, y_train, _ = build_residual_training_data(train_features, train_y)
        if train_exog is not None:
            valid_mask = train_features.notna().all(axis=1).values
            X_train = np.column_stack([X_train, train_exog[valid_mask]])
            feature_names += WEATHER_FEATURES
    else:
        valid_mask = train_features.notna().all(axis=1)
        X_train = train_features[valid_mask].values
        if train_exog is not None:
            X_train = np.column_stack([X_train, train_exog[valid_mask.values]])
            feature_names += WEATHER_FEATURES
        y_train = train_y[valid_mask.values]

    model = _create_model(model_name, params)
    model.fit(X_train, y_train)
    importances = model.feature_importances_
    return dict(zip(feature_names, importances))


# ── Report Generation ────────────────────────────────────────────────────

def generate_report(all_results, output_path):
    """Generate markdown comparison report."""
    lines = [
        '# Seasonal Data Expansion Experiment',
        '',
        '## Experiment Design',
        '',
        '### Data',
        '',
        '- **Training**: Up to 1 year of UK carbon intensity data (expanded from 90-day winter)',
        '- **Test**: Last 7 days',
        '',
        '### Best Variant per Model',
        '',
        '| Model | Variant | Prior MAE (90d) |',
        '|-------|---------|----------------|',
        f'| Random Forest | residual | 46.61 |',
        f'| XGBoost | enhanced | 35.44 |',
        f'| CatBoost | residual | 41.04 |',
        f'| LightGBM | enhanced | 39.12 |',
        f'| Direct-XGBoost | baseline | 33.50 |',
        '',
        '### Seasonal Features',
        '',
        '- 11 cyclical: hour, dow, week, month, day-of-year sin/cos + daylight proxy',
        '- 21 lags: 1-12, 24, 48, 72, 96, 144, 336, 672 (2wk), 1344 (4wk)',
        '- 8 rolling: mean/std at 12, 48, 336, 672, 1344',
        '- 3 weather: wind speed, temperature, solar radiation',
        '',
        '## Results',
        '',
    ]

    # Collect all windows present
    all_windows = set()
    for region in all_results:
        for w in all_results[region]:
            all_windows.add(w)

    for window_name in sorted(all_windows):
        lines.append(f'### {window_name}')
        lines.append('')
        lines.append('| Model | Variant | ' +
                     ' | '.join(sorted(all_results.keys())) +
                     ' | Cross-Region Avg |')
        lines.append('|-------|---------|' +
                     '|'.join(['-------'] * len(all_results)) +
                     '|----------------|')

        for model_name in MODELS:
            variant = BEST_VARIANTS[model_name]
            row = [f'| {model_name} | {variant}']
            maes = []
            for region in sorted(all_results.keys()):
                result = all_results.get(region, {}).get(window_name, {}).get(model_name)
                if result is not None:
                    mae = result['metrics']['MAE']
                    maes.append(mae)
                    row.append(f' {mae:.2f}')
                else:
                    row.append(' N/A')
            if maes:
                row.append(f' **{np.mean(maes):.2f}**')
            else:
                row.append(' N/A')
            row.append('')
            lines.append(' |'.join(row))

        lines.append('')

    # Comparison with prior experiments
    lines.append('## Comparison with Prior Experiments (90-day)')
    lines.append('')
    lines.append('| Model | 90-day MAE | Seasonal MAE | Delta |')
    lines.append('|-------|-----------|-------------|-------|')

    prior_maes = {
        'Random Forest': 46.61,
        'XGBoost': 35.44,
        'CatBoost': 41.04,
        'LightGBM': 39.12,
        'Direct-XGBoost': 33.50,
    }

    # Use full_year window for comparison if available, otherwise first available
    compare_window = 'full_year'
    for model_name in MODELS:
        prior = prior_maes[model_name]
        seasonal_maes = []
        for region in all_results:
            result = all_results.get(region, {}).get(compare_window, {}).get(model_name)
            if result is not None:
                seasonal_maes.append(result['metrics']['MAE'])
        if seasonal_maes:
            avg = np.mean(seasonal_maes)
            delta = avg - prior
            sign = '+' if delta > 0 else ''
            lines.append(f'| {model_name} | {prior:.2f} | {avg:.2f} | {sign}{delta:.2f} |')
        else:
            lines.append(f'| {model_name} | {prior:.2f} | N/A | N/A |')

    lines.append('')
    lines.append('*Negative delta = seasonal is better (more data helped).*')
    lines.append('')

    output_path.write_text('\n'.join(lines))
    print(f"Saved: {output_path}")


# ── CLI ──────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description='Seasonal Data Expansion Benchmark')
    parser.add_argument('--tune', action='store_true',
                        help='Run hyperparameter tuning before benchmarking')
    parser.add_argument('--windows', nargs='+', default=['full_year'],
                        choices=['full_year', '6_months', '3_months'],
                        help='Training windows to compare')
    return parser.parse_args()


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    total_days = (df['ts'].max() - df['ts'].min()).days
    print(f"Regions: {regions}")
    print(f"Date range: {df['ts'].min()} -> {df['ts'].max()} ({total_days} days)")

    if total_days < 30:
        print("ERROR: Not enough data. Run: python3 carbon_collector.py backfill 365")
        sys.exit(1)

    # Fetch weather data (may need chunking for long ranges)
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print("\nFetching weather data...")

    # Chunk weather requests if range > 90 days to avoid Open-Meteo limits
    date_range_days = (pd.Timestamp(date_max) - pd.Timestamp(date_min)).days
    if date_range_days > 90:
        print(f"  Date range is {date_range_days} days, fetching weather in 90-day chunks...")
        weather_chunks = []
        chunk_start = pd.Timestamp(date_min)
        chunk_end_final = pd.Timestamp(date_max)
        while chunk_start < chunk_end_final:
            chunk_end = min(chunk_start + pd.Timedelta(days=89), chunk_end_final)
            try:
                wdf = fetch_weather_data(regions,
                                         chunk_start.strftime('%Y-%m-%d'),
                                         chunk_end.strftime('%Y-%m-%d'))
                if len(wdf) > 0:
                    weather_chunks.append(wdf)
            except Exception as e:
                print(f"  WARNING: Weather chunk {chunk_start} to {chunk_end} failed: {e}")
            chunk_start = chunk_end + pd.Timedelta(days=1)
        if weather_chunks:
            weather_df = pd.concat(weather_chunks, ignore_index=True)
            weather_df = weather_df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
        else:
            weather_df = pd.DataFrame()
    else:
        weather_df = fetch_weather_data(regions, date_min, date_max)

    has_weather = len(weather_df) > 0
    if has_weather:
        print(f"Weather data: {len(weather_df)} points")
    else:
        print("WARNING: No weather data -- running without exogenous features")

    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)

    # Optional tuning
    tuned_params = None
    if args.tune:
        print("\n" + "=" * 70)
        print("HYPERPARAMETER TUNING")
        print("=" * 70)

        # Load existing tuned params if available
        if TUNED_PARAMS_PATH.exists():
            tuned_params = json.loads(TUNED_PARAMS_PATH.read_text())
            print(f"Loaded existing tuned params from {TUNED_PARAMS_PATH}")
        else:
            tuned_params = {}

        # Use first region with enough data for tuning
        for region in regions:
            rdf = df[df['region'] == region].copy().reset_index(drop=True)
            train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
            if len(train) >= 2000:
                print(f"\nTuning on {region} (n={len(train)})...")

                # Build weather exog for tuning
                tune_exog = None
                if has_weather:
                    rwx = weather_df[weather_df['region'] == region].sort_values('ts')
                    if len(rwx) > 0:
                        merged = train.merge(rwx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
                        merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].interpolate(method='linear')
                        for feat in WEATHER_FEATURES:
                            merged[feat] = merged[feat].shift(1)
                        merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].fillna(0)
                        tune_exog = merged[WEATHER_FEATURES].values

                # Tune Direct-XGBoost first (fastest)
                tune_order = ['Direct-XGBoost', 'XGBoost', 'LightGBM', 'Random Forest', 'CatBoost']
                for model_name in tune_order:
                    if model_name not in tuned_params:
                        try:
                            best = tune_model(model_name,
                                              train['ts'].reset_index(drop=True),
                                              train['actual'].values,
                                              tune_exog)
                            tuned_params[model_name] = best
                        except Exception as e:
                            print(f"      Tuning {model_name} failed: {e}")

                break  # only tune on first suitable region

        # Save tuned params
        # Convert numpy types to Python types for JSON serialization
        serializable = {}
        for k, v in tuned_params.items():
            serializable[k] = {pk: (int(pv) if isinstance(pv, (np.integer,)) else
                                    float(pv) if isinstance(pv, (np.floating,)) else pv)
                               for pk, pv in v.items()}
        TUNED_PARAMS_PATH.write_text(json.dumps(serializable, indent=2))
        print(f"\nTuned params saved to {TUNED_PARAMS_PATH}")

    # Run models
    all_results = {}
    all_preds_for_plot = {}
    all_importances = {}
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

        windows = get_training_windows(rdf, split_date, args.windows)
        if not windows:
            print(f"\n{region}: no valid training windows, skipping")
            continue

        for window_name, train in windows:
            train_days = (train['ts'].max() - train['ts'].min()).days
            print(f"\n{'=' * 60}")
            print(f"  {region} [{window_name}]: train={len(train)} ({train_days}d), test={len(test)}")
            print(f"{'=' * 60}")

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
            for model_name in MODELS:
                variant = BEST_VARIANTS[model_name]
                print(f"    {model_name} ({variant})...", end=' ', flush=True)
                try:
                    preds, elapsed = train_predict_seasonal(
                        model_name,
                        train_ts=train_ts, train_y=train_y,
                        test_ts=test_ts, test_y=test_y,
                        train_exog=train_exog, test_exog=test_exog,
                        tuned_params=tuned_params,
                    )
                    if len(preds) != len(test_y):
                        min_len = min(len(preds), len(test_y))
                        preds = preds[:min_len]
                        test_y_eval = test_y[:min_len]
                    else:
                        test_y_eval = test_y

                    metrics = compute_metrics(test_y_eval, preds,
                                              n_features=N_FEATURES[model_name])
                    print(f"MAE={metrics['MAE']:.2f}  ({elapsed:.2f}s)")
                    results[model_name] = {
                        'preds': preds.tolist(),
                        'metrics': metrics,
                        'time': elapsed,
                        'variant': variant,
                    }

                    # Save for plotting (prefer full_year)
                    if window_name == 'full_year' or model_name not in all_preds_for_plot:
                        all_preds_for_plot[model_name] = preds
                        last_test_ts = test_ts
                        last_test_y = test_y

                except Exception as e:
                    print(f"FAILED: {e}")
                    import traceback
                    traceback.print_exc()
                    results[model_name] = None

            all_results[region][window_name] = results

        # Feature importance for XGBoost and LightGBM (on last region's full_year)
        if 'full_year' in all_results.get(region, {}):
            for imp_name in ['XGBoost', 'LightGBM']:
                try:
                    # Get full_year train for this region
                    train_full = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
                    imp_train_exog = None
                    if has_weather:
                        rwx = weather_df[weather_df['region'] == region].sort_values('ts')
                        if len(rwx) > 0:
                            merged = train_full.merge(rwx[['ts'] + WEATHER_FEATURES], on='ts', how='left')
                            merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].interpolate(method='linear')
                            for feat in WEATHER_FEATURES:
                                merged[feat] = merged[feat].shift(1)
                            merged[WEATHER_FEATURES] = merged[WEATHER_FEATURES].fillna(0)
                            imp_train_exog = merged[WEATHER_FEATURES].values

                    imp = extract_feature_importance(
                        imp_name,
                        train_full['ts'].reset_index(drop=True),
                        train_full['actual'].values,
                        imp_train_exog,
                        tuned_params,
                    )
                    all_importances[imp_name] = imp
                except Exception as e:
                    print(f"    Feature importance for {imp_name} failed: {e}")

    # Save results (strip preds for JSON size)
    save_results = {}
    for region in all_results:
        save_results[region] = {}
        for window in all_results[region]:
            save_results[region][window] = {}
            for model in all_results[region][window]:
                r = all_results[region][window][model]
                if r is not None:
                    save_results[region][window][model] = {
                        'metrics': r['metrics'],
                        'time': r['time'],
                        'variant': r['variant'],
                    }

    RESULTS_PATH.write_text(json.dumps(save_results, indent=2))
    print(f"\nResults saved to {RESULTS_PATH}")

    # Generate visualizations
    print("\nGenerating visualizations...")

    # Comparison chart (cross-region average per window)
    results_by_window = {}
    for window_name in args.windows:
        window_maes = {}
        for model_name in MODELS:
            maes = []
            for region in all_results:
                r = all_results.get(region, {}).get(window_name, {}).get(model_name)
                if r is not None:
                    maes.append(r['metrics']['MAE'])
            if maes:
                window_maes[model_name] = np.mean(maes)
        if window_maes:
            results_by_window[window_name] = window_maes

    if results_by_window:
        generate_comparison_chart(results_by_window,
                                  DOCS_DIR / 'benchmark_seasonal_comparison.png')

    if last_test_ts is not None and all_preds_for_plot:
        generate_predictions_chart(last_test_ts, last_test_y, all_preds_for_plot,
                                   DOCS_DIR / 'benchmark_seasonal_predictions.png')

    if all_importances:
        generate_importance_chart(all_importances,
                                  DOCS_DIR / 'benchmark_seasonal_importance.png')

    # Generate report
    generate_report(all_results, DOCS_DIR / 'benchmark_seasonal.md')

    # Print summary
    print("\n" + "=" * 70)
    print("SEASONAL EXPERIMENT COMPLETE")
    print("=" * 70)
    for window_name in args.windows:
        if window_name not in results_by_window:
            continue
        print(f"\n--- {window_name} ---")
        for model_name in MODELS:
            maes = []
            for region in all_results:
                r = all_results.get(region, {}).get(window_name, {}).get(model_name)
                if r is not None:
                    maes.append(r['metrics']['MAE'])
            if maes:
                avg = np.mean(maes)
                variant = BEST_VARIANTS[model_name]
                prior_maes = {
                    'Random Forest': 46.61, 'XGBoost': 35.44,
                    'CatBoost': 41.04, 'LightGBM': 39.12,
                    'Direct-XGBoost': 33.50,
                }
                prior = prior_maes[model_name]
                delta = avg - prior
                sign = '+' if delta > 0 else ''
                tag = "improved" if delta < 0 else "worse"
                print(f"   {model_name:20s} ({variant:8s})  MAE={avg:6.2f}  "
                      f"vs 90d={prior:.2f}  d={sign}{delta:.2f} {tag}")


if __name__ == '__main__':
    main()
