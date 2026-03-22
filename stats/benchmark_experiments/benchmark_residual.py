#!/usr/bin/env python3
"""
Persistence Residual Target Experiment.

Instead of predicting raw carbon intensity, models predict y - lag_1
(the deviation from persistence). Final prediction = lag_1 + model(features).
This makes the correction signal louder and lets trees focus on what changes.

Compares against baseline (tree_results.json) and enhanced features
(enhanced_features_results.json).

Usage:
    python3 benchmark_residual.py
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
from matplotlib.dates import DateFormatter

warnings.filterwarnings('ignore')

from benchmark import (
    DB_PATH,
    TEST_DAYS,
    WEATHER_FEATURES,
    compute_metrics,
    fetch_weather_data,
    load_data,
)
from benchmark_enhanced_features import (
    ROLLING_CONFIGS,
    SPARSE_LAGS,
    build_enhanced_cyclical,
    build_enhanced_lag_features,
    build_enhanced_ml_features,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
RESULTS_PATH = Path(__file__).parent / 'residual_results.json'
TREE_RESULTS_PATH = Path(__file__).parent / 'tree_results.json'
ENHANCED_RESULTS_PATH = Path(__file__).parent / 'enhanced_features_results.json'

MODELS = ['Random Forest', 'XGBoost', 'CatBoost', 'LightGBM', 'Direct-XGBoost']

N_FEATURES = {
    'Random Forest': 33,
    'XGBoost': 33,
    'CatBoost': 33,
    'LightGBM': 33,
    'Direct-XGBoost': 18,
}


# ── Residual Training Data ───────────────────────────────────────────────


def build_residual_training_data(train_features, train_y):
    """Extract lag_1, compute residual target, apply valid mask.

    Returns (X_train, y_residual, lag_1_values) with NaN rows removed.
    """
    lag_1_col = train_features['lag_1'].values
    valid_mask = train_features.notna().all(axis=1).values
    X_train = train_features[valid_mask].values
    lag_1_values = lag_1_col[valid_mask]
    y_residual = train_y[valid_mask] - lag_1_values
    return X_train, y_residual, lag_1_values


# ── Recursive Forecast (Residual Target) ─────────────────────────────────


def recursive_forecast_residual(model, train_ts, train_y, test_ts, test_y_actual, train_exog=None, test_exog=None):
    """Recursive multi-step forecast with residual target.

    Training target: y - lag_1 (deviation from persistence).
    Prediction: lag_1 + model.predict(features).
    known_values accumulates raw (reconstructed) predictions.
    """
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)
    known_values = list(train_y)

    # Build training features (on raw values)
    train_features = build_enhanced_ml_features(train_ts, train_y)
    X_train, y_residual, _ = build_residual_training_data(train_features, train_y)

    if has_exog:
        valid_mask = train_features.notna().all(axis=1).values
        X_train = np.column_stack([X_train, train_exog[valid_mask]])

    model.fit(X_train, y_residual)

    # Predict each test step
    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_enhanced_cyclical(ts_point)

        # Sparse lag features from known_values (raw)
        lag_feats = {}
        for lag in SPARSE_LAGS:
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = known_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan

        # Rolling stats from known_values (raw)
        for window, stat in ROLLING_CONFIGS:
            start = max(0, idx - 1 - window + 1)
            end = idx
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
            x_step = np.column_stack([x_step.values, test_exog[t : t + 1]])
        else:
            x_step = x_step.values

        # Predict residual, reconstruct raw
        residual = model.predict(x_step)[0]
        lag_1 = known_values[idx - 1]
        raw_pred = lag_1 + residual
        preds[t] = raw_pred
        known_values.append(raw_pred)  # raw, not residual

    return np.clip(preds, 0, 500)


# ── Direct Forecast (Residual Target) ────────────────────────────────────


def build_direct_features_residual(train_ts, train_y, test_ts, train_exog=None, test_exog=None):
    """Direct features with residual target: y[target] - y[origin]."""
    n_test = len(test_ts)
    n_train = len(train_y)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 336
    max_h = min(n_test, 336)

    all_cyc = build_enhanced_cyclical(train_ts).values

    # Origin features (same as enhanced, computed on raw values)
    origin_last = np.zeros(n_train)
    origin_mean_48 = np.zeros(n_train)
    origin_std_48 = np.zeros(n_train)
    origin_lag_48 = np.zeros(n_train)
    origin_lag_336 = np.zeros(n_train)
    origin_mean_336 = np.zeros(n_train)
    origin_std_336 = np.zeros(n_train)

    for t in range(min_history, n_train):
        recent_48 = train_y[max(0, t - 47) : t + 1]
        recent_336 = train_y[max(0, t - 335) : t + 1]
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
        h2_col = h_col**2
        of = np.column_stack(
            [
                origin_last[origins],
                origin_mean_48[origins],
                origin_std_48[origins],
                origin_lag_48[origins],
                origin_lag_336[origins],
                origin_mean_336[origins],
                origin_std_336[origins],
            ]
        )
        x = np.column_stack([cyc, h_col, h2_col, of])
        if has_exog:
            x = np.column_stack([x, train_exog[targets]])
        X_parts.append(x)
        # Residual target: actual - origin value
        y_parts.append(train_y[targets] - train_y[origins])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    # Test features
    test_cyc = build_enhanced_cyclical(test_ts).values
    recent_48 = train_y[-48:]
    recent_336 = train_y[-336:] if len(train_y) >= 336 else train_y
    of_test = np.array(
        [
            [
                train_y[-1],
                np.mean(recent_48),
                np.std(recent_48),
                train_y[-48] if len(train_y) >= 48 else train_y[0],
                train_y[-336] if len(train_y) >= 336 else train_y[0],
                np.mean(recent_336),
                np.std(recent_336),
            ]
        ]
    )
    of_test = np.tile(of_test, (n_test, 1))
    h_vals = np.arange(1, n_test + 1).reshape(-1, 1) / 336.0
    X_test = np.column_stack([test_cyc, h_vals, h_vals**2, of_test])
    if has_exog:
        X_test = np.column_stack([X_test, test_exog])

    return X_train, y_train, X_test


# ── Model Runners ────────────────────────────────────────────────────────


def train_predict_rf_residual(train_ts, train_y, test_ts, test_y=None, **kw):
    from sklearn.ensemble import RandomForestRegressor

    t0 = time.time()
    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_residual(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_xgb_residual(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor

    t0 = time.time()
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_residual(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_catboost_residual(train_ts, train_y, test_ts, test_y=None, **kw):
    from catboost import CatBoostRegressor

    t0 = time.time()
    model = CatBoostRegressor(iterations=200, depth=6, learning_rate=0.1, random_seed=42, verbose=0)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_residual(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_lgbm_residual(train_ts, train_y, test_ts, test_y=None, **kw):
    import lightgbm as lgb

    t0 = time.time()
    model = lgb.LGBMRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbose=-1, n_jobs=-1)
    if test_y is None:
        test_y = np.zeros(len(test_ts))
    preds = recursive_forecast_residual(
        model, train_ts, train_y, test_ts, test_y, train_exog=kw.get('train_exog'), test_exog=kw.get('test_exog')
    )
    return preds, time.time() - t0


def train_predict_direct_xgb_residual(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor

    t0 = time.time()
    X, y, X_test = build_direct_features_residual(
        train_ts,
        train_y,
        test_ts,
        train_exog=kw.get('train_exog'),
        test_exog=kw.get('test_exog'),
    )
    max_samples = 500_000
    if len(X) > max_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), max_samples, replace=False)
        X = X[idx]
        y = y[idx]
    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1)
    model.fit(X, y)
    residual_preds = model.predict(X_test)
    # Reconstruct raw: origin (last training value) + predicted residual
    raw_preds = train_y[-1] + residual_preds
    return np.clip(raw_preds, 0, 500), time.time() - t0


RESIDUAL_FUNCS = {
    'Random Forest': train_predict_rf_residual,
    'XGBoost': train_predict_xgb_residual,
    'CatBoost': train_predict_catboost_residual,
    'LightGBM': train_predict_lgbm_residual,
    'Direct-XGBoost': train_predict_direct_xgb_residual,
}


# ── Feature Importance ───────────────────────────────────────────────────


def extract_feature_importance(model, train_ts, train_y, train_exog=None):
    """Train model on residual target and return feature importances."""
    train_features = build_enhanced_ml_features(train_ts, train_y)
    feature_names = list(train_features.columns)
    X_train, y_residual, _ = build_residual_training_data(train_features, train_y)

    if train_exog is not None:
        valid_mask = train_features.notna().all(axis=1).values
        X_train = np.column_stack([X_train, train_exog[valid_mask]])
        feature_names += WEATHER_FEATURES

    model.fit(X_train, y_residual)
    importances = model.feature_importances_
    return dict(zip(feature_names, importances))


# ── Visualization ────────────────────────────────────────────────────────


def generate_comparison_chart(baseline_maes, enhanced_maes, residual_maes, output_path):
    """3-way bar chart: baseline vs enhanced vs residual."""
    models = [m for m in MODELS if m in baseline_maes or m in enhanced_maes or m in residual_maes]
    x = np.arange(len(models))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - width, [baseline_maes.get(m, 0) for m in models], width, label='Baseline', color='#4a90d9')
    ax.bar(x, [enhanced_maes.get(m, 0) for m in models], width, label='Enhanced', color='#e74c3c')
    ax.bar(x + width, [residual_maes.get(m, 0) for m in models], width, label='Residual', color='#2ecc71')

    ax.set_xlabel('Model')
    ax.set_ylabel('MAE (gCO2/kWh)')
    ax.set_title('Residual Target Experiment: 3-Way MAE Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=15, ha='right')
    ax.legend()

    for bars in ax.containers:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3, f'{h:.1f}', ha='center', va='bottom', fontsize=7)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f'Saved: {output_path}')


def generate_predictions_chart(test_ts, test_y, all_preds, output_path):
    """Predictions vs actual for all residual models."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(test_ts, test_y, 'k-', linewidth=1.5, label='Actual', alpha=0.8)

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
    for (name, preds), color in zip(all_preds.items(), colors):
        ax.plot(test_ts[: len(preds)], preds, '-', color=color, linewidth=1, label=name, alpha=0.7)

    ax.set_xlabel('Time')
    ax.set_ylabel('Carbon Intensity (gCO2/kWh)')
    ax.set_title('Residual Target: Predictions vs Actual')
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f'Saved: {output_path}')


def generate_importance_chart(importance_dicts, output_path):
    """Feature importance comparison for tree models (residual target)."""
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
        ax.barh(range(len(names)), vals, color='#2ecc71')
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel('Importance')
        ax.set_title(f'{model_name} (Residual Target)')
        ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f'Saved: {output_path}')


def generate_acf_chart(test_y, all_preds, output_path, nlags=50):
    """ACF of residuals comparison across models."""
    from statsmodels.tsa.stattools import acf

    n_models = len(all_preds)
    if n_models == 0:
        return

    fig, axes = plt.subplots(1, n_models, figsize=(5 * n_models, 4), squeeze=False)
    axes = axes[0]

    for ax, (model_name, preds) in zip(axes, all_preds.items()):
        min_len = min(len(preds), len(test_y))
        resid = test_y[:min_len] - preds[:min_len]
        acf_vals = acf(resid, nlags=nlags, fft=True)
        ax.bar(range(len(acf_vals)), acf_vals, width=0.8, color='#2ecc71', alpha=0.7)
        # Significance band
        n = min_len
        ax.axhline(1.96 / np.sqrt(n), color='r', linestyle='--', linewidth=0.5)
        ax.axhline(-1.96 / np.sqrt(n), color='r', linestyle='--', linewidth=0.5)
        ax.set_title(f'{model_name}', fontsize=9)
        ax.set_xlabel('Lag')
        ax.set_ylabel('ACF')

    plt.suptitle('ACF of Forecast Errors (Residual Target)', y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Saved: {output_path}')


# ── Report ───────────────────────────────────────────────────────────────


def generate_report(baseline_results, enhanced_results, residual_results, output_path):
    """Generate markdown comparison report (baseline vs enhanced vs residual)."""
    lines = [
        '# Persistence Residual Target Experiment',
        '',
        '## Approach',
        '',
        'Instead of predicting raw carbon intensity, models predict `y - lag_1`',
        '(deviation from persistence). Final prediction = `lag_1 + model(features)`.',
        'Features (lags, rolling stats) remain computed on raw values.',
        '',
        '## Results',
        '',
    ]

    window_name = 'Full backfill'

    lines.append(f'### {window_name} Training Window')
    lines.append('')
    lines.append('| Model | Baseline MAE | Enhanced MAE | Residual MAE | Δ vs Baseline | Δ vs Enhanced |')
    lines.append('|-------|-------------|-------------|-------------|--------------|--------------|')

    for model_name in MODELS:
        base_maes = []
        enh_maes = []
        res_maes = []
        for region in residual_results:
            res = residual_results.get(region, {}).get(window_name, {}).get(model_name)
            base = baseline_results.get(region, {}).get(window_name, {}).get(model_name)
            enh = enhanced_results.get(region, {}).get(window_name, {}).get(model_name)
            if res is not None:
                res_maes.append(res['metrics']['MAE'])
            if base is not None:
                base_maes.append(base['metrics']['MAE'])
            if enh is not None:
                enh_maes.append(enh['metrics']['MAE'])

        if not res_maes:
            continue
        avg_res = np.mean(res_maes)
        avg_base = np.mean(base_maes) if base_maes else None
        avg_enh = np.mean(enh_maes) if enh_maes else None

        base_str = f'{avg_base:.2f}' if avg_base is not None else 'N/A'
        enh_str = f'{avg_enh:.2f}' if avg_enh is not None else 'N/A'

        if avg_base is not None:
            d1 = avg_res - avg_base
            s1 = '+' if d1 > 0 else ''
            d1_str = f'{s1}{d1:.2f}'
        else:
            d1_str = 'N/A'

        if avg_enh is not None:
            d2 = avg_res - avg_enh
            s2 = '+' if d2 > 0 else ''
            d2_str = f'{s2}{d2:.2f}'
        else:
            d2_str = 'N/A'

        lines.append(f'| {model_name} | {base_str} | {enh_str} | {avg_res:.2f} | {d1_str} | {d2_str} |')

    lines.append('')
    lines.append('## Analysis')
    lines.append('')
    lines.append('Negative delta = improvement (residual is better).')
    lines.append('')

    output_path.write_text('\n'.join(lines))
    print(f'Saved: {output_path}')


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    # Load prior results for comparison
    baseline_results = {}
    if TREE_RESULTS_PATH.exists():
        baseline_results = json.loads(TREE_RESULTS_PATH.read_text())
        print(f'Loaded baseline results from {TREE_RESULTS_PATH}')

    enhanced_results = {}
    if ENHANCED_RESULTS_PATH.exists():
        enhanced_results = json.loads(ENHANCED_RESULTS_PATH.read_text())
        print(f'Loaded enhanced results from {ENHANCED_RESULTS_PATH}')

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f'Regions: {regions}')
    print(f'Date range: {df["ts"].min()} -> {df["ts"].max()}')

    # Fetch weather data
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print('\nFetching weather data...')
    weather_df = fetch_weather_data(regions, date_min, date_max)
    has_weather = len(weather_df) > 0
    if has_weather:
        print(f'Weather data: {len(weather_df)} points')
    else:
        print('WARNING: No weather data — running without exogenous features')

    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)

    # Run residual models
    all_results = {}
    all_preds_for_plot = {}
    all_importances = {}
    last_test_ts = None
    last_test_y = None

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f'\n{region}: no test data, skipping')
            continue

        all_results[region] = {}
        test_y = test['actual'].values
        train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

        if len(train) < 400:
            print(f'\n{region}: insufficient training data ({len(train)} < 400), skipping')
            continue

        train_days = (train['ts'].max() - train['ts'].min()).days
        print(f'\n{"=" * 60}')
        print(f'  {region} [Full backfill]: train={len(train)} ({train_days}d), test={len(test)}')
        print(f'{"=" * 60}')

        # Weather exogenous features
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
            print(f'    {model_name}...', end=' ', flush=True)
            func = RESIDUAL_FUNCS[model_name]
            try:
                preds, elapsed = func(
                    train_ts=train_ts,
                    train_y=train_y,
                    test_ts=test_ts,
                    test_y=test_y,
                    train_exog=train_exog,
                    test_exog=test_exog,
                )
                if len(preds) != len(test_y):
                    min_len = min(len(preds), len(test_y))
                    preds = preds[:min_len]
                    test_y_eval = test_y[:min_len]
                else:
                    test_y_eval = test_y

                metrics = compute_metrics(test_y_eval, preds, n_features=N_FEATURES[model_name])
                print(f'MAE={metrics["MAE"]:.2f}  ({elapsed:.2f}s)')
                results[model_name] = {
                    'preds': preds.tolist(),
                    'metrics': metrics,
                    'time': elapsed,
                }

                all_preds_for_plot[model_name] = preds
                last_test_ts = test_ts
                last_test_y = test_y

            except Exception as e:
                print(f'FAILED: {e}')
                import traceback

                traceback.print_exc()
                results[model_name] = None

        all_results[region]['Full backfill'] = results

        # Feature importance for XGBoost and LightGBM (on last region)
        for imp_name, imp_cls_path in [('XGBoost', 'xgboost.XGBRegressor'), ('LightGBM', 'lightgbm.LGBMRegressor')]:
            try:
                module, cls_name = imp_cls_path.rsplit('.', 1)
                mod = __import__(module)
                cls = getattr(mod, cls_name)
                if imp_name == 'XGBoost':
                    model = cls(
                        n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1
                    )
                else:
                    model = cls(
                        n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbose=-1, n_jobs=-1
                    )
                imp = extract_feature_importance(model, train_ts, train_y, train_exog)
                all_importances[imp_name] = imp
            except Exception as e:
                print(f'    Feature importance for {imp_name} failed: {e}')

    # Save results
    RESULTS_PATH.write_text(json.dumps(all_results, indent=2))
    print(f'\nResults saved to {RESULTS_PATH}')

    # Generate visualizations
    print('\nGenerating visualizations...')

    # 3-way comparison chart (cross-region average)
    baseline_avg = {}
    enhanced_avg = {}
    residual_avg = {}
    for model_name in MODELS:
        b, e, r = [], [], []
        for region in all_results:
            res = all_results.get(region, {}).get('Full backfill', {}).get(model_name)
            base = baseline_results.get(region, {}).get('Full backfill', {}).get(model_name)
            enh = enhanced_results.get(region, {}).get('Full backfill', {}).get(model_name)
            if res is not None:
                r.append(res['metrics']['MAE'])
            if base is not None:
                b.append(base['metrics']['MAE'])
            if enh is not None:
                e.append(enh['metrics']['MAE'])
        if b:
            baseline_avg[model_name] = np.mean(b)
        if e:
            enhanced_avg[model_name] = np.mean(e)
        if r:
            residual_avg[model_name] = np.mean(r)

    if residual_avg:
        generate_comparison_chart(
            baseline_avg, enhanced_avg, residual_avg, DOCS_DIR / 'benchmark_residual_comparison.png'
        )

    if last_test_ts is not None and all_preds_for_plot:
        generate_predictions_chart(
            last_test_ts, last_test_y, all_preds_for_plot, DOCS_DIR / 'benchmark_residual_predictions.png'
        )

    if all_importances:
        generate_importance_chart(all_importances, DOCS_DIR / 'benchmark_residual_importance.png')

    if last_test_y is not None and all_preds_for_plot:
        generate_acf_chart(last_test_y, all_preds_for_plot, DOCS_DIR / 'benchmark_residual_acf.png')

    # Generate report
    generate_report(baseline_results, enhanced_results, all_results, DOCS_DIR / 'benchmark_residual.md')

    # Print summary
    print('\n' + '=' * 70)
    print('RESIDUAL TARGET EXPERIMENT COMPLETE')
    print('=' * 70)
    for model_name in MODELS:
        r_maes = []
        b_maes = []
        e_maes = []
        for region in all_results:
            res = all_results.get(region, {}).get('Full backfill', {}).get(model_name)
            base = baseline_results.get(region, {}).get('Full backfill', {}).get(model_name)
            enh = enhanced_results.get(region, {}).get('Full backfill', {}).get(model_name)
            if res is not None:
                r_maes.append(res['metrics']['MAE'])
            if base is not None:
                b_maes.append(base['metrics']['MAE'])
            if enh is not None:
                e_maes.append(enh['metrics']['MAE'])
        if r_maes:
            avg_r = np.mean(r_maes)
            parts = [f'Residual={avg_r:6.2f}']
            if b_maes:
                avg_b = np.mean(b_maes)
                d = avg_r - avg_b
                s = '+' if d > 0 else ''
                tag = 'improved' if d < 0 else 'worse'
                parts.append(f'Baseline={avg_b:6.2f}  dB={s}{d:.2f} {tag}')
            if e_maes:
                avg_e = np.mean(e_maes)
                d = avg_r - avg_e
                s = '+' if d > 0 else ''
                tag = 'improved' if d < 0 else 'worse'
                parts.append(f'Enhanced={avg_e:6.2f}  dE={s}{d:.2f} {tag}')
            print(f'   {model_name:20s} {"  ".join(parts)}')


if __name__ == '__main__':
    main()
