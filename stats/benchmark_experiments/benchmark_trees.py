#!/usr/bin/env python3
"""
Tree-based model benchmark (separate process).

Runs Random Forest, XGBoost, CatBoost, and LightGBM on the same data splits
as benchmark.py. Results are saved to tree_results.json for benchmark.py to
merge into the final report and graphs.

Run this BEFORE benchmark.py (or benchmark.py will run without tree results).

    python benchmark_trees.py
    python benchmark.py           # auto-merges tree_results.json

Separate process avoids OpenMP/PyTorch thread pool deadlock — tree libraries
use n_jobs=-1 (OpenMP), which conflicts with PyTorch's thread pool when both
run in the same process.
"""

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Reuse infrastructure from benchmark.py
from benchmark import (
    DB_PATH,
    TEST_DAYS,
    WEATHER_FEATURES,
    _build_direct_features,
    _recursive_forecast_tree,
    build_cyclical_features,
    build_ml_features,
    compute_metrics,
    fetch_weather_data,
    load_data,
)

TREE_RESULTS_PATH = Path(__file__).parent / 'tree_results.json'

TREE_MODELS = ['Random Forest', 'XGBoost', 'CatBoost', 'LightGBM', 'Direct-XGBoost']

TREE_N_FEATURES = {
    'Random Forest': 63,
    'XGBoost': 63,
    'CatBoost': 63,
    'LightGBM': 63,
    'Direct-XGBoost': 14,
}


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


def train_predict_direct_xgboost(train_ts, train_y, test_ts, test_y=None, **kw):
    from xgboost import XGBRegressor

    t0 = time.time()
    X, y, X_test = _build_direct_features(
        train_ts,
        train_y,
        test_ts,
        train_exog=kw.get('train_exog'),
        test_exog=kw.get('test_exog'),
    )
    # Subsample for large datasets
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


TREE_FUNCS = {
    'Random Forest': train_predict_random_forest,
    'XGBoost': train_predict_xgboost,
    'CatBoost': train_predict_catboost,
    'LightGBM': train_predict_lightgbm,
    'Direct-XGBoost': train_predict_direct_xgboost,
}


def main():
    # Load data (same splits as benchmark.py)
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f'Regions: {regions}')
    print(f'Date range: {df["ts"].min()} -> {df["ts"].max()}')

    total_days = (df['ts'].max() - df['ts'].min()).days

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

    # Same splits as benchmark.py
    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)
    short_train_start = split_date - pd.Timedelta(days=7)

    windows = [('7-day', short_train_start)]
    if total_days > 14:
        windows.append(('Full backfill', None))

    # Run tree models
    all_results = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f'\n{region}: no test data, skipping')
            continue

        all_results[region] = {}
        test_y = test['actual'].values

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

            if len(train) < 48:
                print(f'\n{region} [{window_name}]: insufficient training data, skipping')
                continue

            train_days = (train['ts'].max() - train['ts'].min()).days
            print(f'\n{"=" * 60}')
            print(f'  {region} [{window_name}]: train={len(train)} ({train_days}d), test={len(test)}')
            print(f'{"=" * 60}')

            # Build lag-1 weather exogenous features (same as benchmark.py)
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
            for model_name in TREE_MODELS:
                print(f'    {model_name}...', end=' ', flush=True)
                func = TREE_FUNCS[model_name]
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

                    metrics = compute_metrics(test_y_eval, preds, n_features=TREE_N_FEATURES[model_name])
                    print(f'MAE={metrics["MAE"]:.2f}  ({elapsed:.2f}s)')
                    results[model_name] = {
                        'preds': preds.tolist(),
                        'metrics': metrics,
                        'time': elapsed,
                    }
                except Exception as e:
                    print(f'FAILED: {e}')
                    results[model_name] = None

            all_results[region][window_name] = results

    # Save results
    TREE_RESULTS_PATH.write_text(json.dumps(all_results, indent=2))
    print(f'\nResults saved to {TREE_RESULTS_PATH}')

    # ── Ablation: run without exogenous features ──
    print('\n' + '=' * 70)
    print('  ABLATION: Running tree models WITHOUT exogenous weather features')
    print('=' * 70)
    noexog_results = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)
        if len(test) == 0:
            continue
        noexog_results[region] = {}
        test_y = test['actual'].values

        for window_name, train_start in windows:
            if train_start is not None:
                train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
            else:
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
            if len(train) < 48:
                continue

            train_ts = train['ts'].reset_index(drop=True)
            train_y = train['actual'].values
            test_ts = test['ts'].reset_index(drop=True)

            print(f'\n  {region} [{window_name}] (no exog)')
            results = {}
            for model_name in TREE_MODELS:
                print(f'    {model_name}...', end=' ', flush=True)
                func = TREE_FUNCS[model_name]
                try:
                    preds, elapsed = func(
                        train_ts=train_ts,
                        train_y=train_y,
                        test_ts=test_ts,
                        test_y=test_y,
                        train_exog=None,
                        test_exog=None,
                    )
                    if len(preds) != len(test_y):
                        min_len = min(len(preds), len(test_y))
                        preds = preds[:min_len]
                        test_y_eval = test_y[:min_len]
                    else:
                        test_y_eval = test_y
                    metrics = compute_metrics(test_y_eval, preds, n_features=TREE_N_FEATURES[model_name])
                    print(f'MAE={metrics["MAE"]:.2f}  ({elapsed:.2f}s)')
                    results[model_name] = {
                        'preds': preds.tolist(),
                        'metrics': metrics,
                        'time': elapsed,
                    }
                except Exception as e:
                    print(f'FAILED: {e}')
                    results[model_name] = None
            noexog_results[region][window_name] = results

    noexog_path = Path(__file__).parent / 'tree_results_noexog.json'
    noexog_path.write_text(json.dumps(noexog_results, indent=2))
    print(f'\nNo-exog results saved to {noexog_path}')

    # Summary
    print('\n' + '=' * 70)
    print('TREE BENCHMARK COMPLETE')
    print('=' * 70)
    for window_name, _ in windows:
        print(f'\n--- {window_name} (with weather) ---')
        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
        model_maes = {}
        for model_name in TREE_MODELS:
            maes = []
            for region in active_regions:
                res = all_results[region][window_name].get(model_name)
                if res is not None:
                    maes.append(res['metrics']['MAE'])
            if maes:
                model_maes[model_name] = np.mean(maes)
        sorted_models = sorted(model_maes, key=model_maes.get)
        for i, m in enumerate(sorted_models):
            best = ' <-- best' if i == 0 else ''
            print(f'   {i + 1}. {m:20s} MAE={model_maes[m]:6.2f}{best}')

    print(f'\nNow run: python benchmark.py  (will auto-merge tree results)')


if __name__ == '__main__':
    main()
