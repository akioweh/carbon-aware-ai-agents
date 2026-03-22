#!/usr/bin/env python3
"""
Feature importance + ACF analysis for enhanced XGBoost and LightGBM.

Trains both models on full backfill, extracts feature importances,
and computes max ACF difference between actuals and predictions.
"""

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf

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
    ENHANCED_N_FEATURES,
    ROLLING_CONFIGS,
    SPARSE_LAGS,
    build_enhanced_cyclical,
    build_enhanced_ml_features,
    recursive_forecast_enhanced,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'

# Feature names for recursive models (must match build_enhanced_ml_features + exog order)
RECURSIVE_FEATURE_NAMES = (
    ['hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'week_sin', 'week_cos']
    + [f'lag_{l}' for l in SPARSE_LAGS]
    + [f'rolling_mean_{w}' if s == 'mean' else f'rolling_std_{w}' for w, s in ROLLING_CONFIGS]
    + WEATHER_FEATURES
)


def train_and_get_importance(model, train_ts, train_y, test_ts, test_y, train_exog=None, test_exog=None):
    """Train via recursive forecast and return (preds, fitted_model)."""
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)
    known_values = list(train_y)

    train_features = build_enhanced_ml_features(train_ts, train_y)
    valid_mask = train_features.notna().all(axis=1)
    X_train = train_features[valid_mask].values
    if has_exog:
        X_train = np.column_stack([X_train, train_exog[valid_mask.values]])
    y_train = train_y[valid_mask.values]

    model.fit(X_train, y_train)

    # Predict
    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_enhanced_cyclical(ts_point)

        lag_feats = {}
        for lag in SPARSE_LAGS:
            lookback_idx = idx - lag
            lag_feats[f'lag_{lag}'] = known_values[lookback_idx] if lookback_idx >= 0 else np.nan

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
        pred = model.predict(x_step)[0]
        preds[t] = pred
        known_values.append(pred)

    return np.clip(preds, 0, 500), model


def compute_acf_diff(actual, predicted, nlags=48):
    """Compute max absolute ACF difference between actual and predicted residuals."""
    acf_actual = acf(actual, nlags=nlags, fft=True)
    acf_pred = acf(predicted, nlags=nlags, fft=True)
    diffs = np.abs(acf_actual - acf_pred)
    return diffs, acf_actual, acf_pred


def plot_feature_importance(importances, feature_names, model_name, ax):
    """Plot horizontal bar chart of feature importances."""
    sorted_idx = np.argsort(importances)
    ax.barh(range(len(sorted_idx)), importances[sorted_idx], color='#3498db')
    ax.set_yticks(range(len(sorted_idx)))
    ax.set_yticklabels([feature_names[i] for i in sorted_idx], fontsize=7)
    ax.set_xlabel('Importance')
    ax.set_title(f'{model_name} Feature Importance')


def main():
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f'Regions: {regions}')

    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    weather_df = fetch_weather_data(regions, date_min, date_max)
    has_weather = len(weather_df) > 0

    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)

    # Aggregate importances across regions
    xgb_importances = []
    lgbm_importances = []
    all_acf_diffs = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(train) < 400 or len(test) == 0:
            continue

        train_ts = train['ts'].reset_index(drop=True)
        train_y = train['actual'].values
        test_ts = test['ts'].reset_index(drop=True)
        test_y = test['actual'].values

        # Weather exog
        train_exog = test_exog = None
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

        print(f'\n{"=" * 50}')
        print(f'  {region}')
        print(f'{"=" * 50}')

        # XGBoost
        from xgboost import XGBRegressor

        print('  XGBoost...', end=' ', flush=True)
        xgb_model = XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbosity=0, n_jobs=-1
        )
        xgb_preds, xgb_fitted = train_and_get_importance(
            xgb_model, train_ts, train_y, test_ts, test_y, train_exog=train_exog, test_exog=test_exog
        )
        xgb_mae = np.mean(np.abs(test_y - xgb_preds))
        print(f'MAE={xgb_mae:.2f}')
        xgb_importances.append(xgb_fitted.feature_importances_)

        # LightGBM
        import lightgbm as lgb

        print('  LightGBM...', end=' ', flush=True)
        lgbm_model = lgb.LGBMRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42, verbose=-1, n_jobs=-1
        )
        lgbm_preds, lgbm_fitted = train_and_get_importance(
            lgbm_model, train_ts, train_y, test_ts, test_y, train_exog=train_exog, test_exog=test_exog
        )
        lgbm_mae = np.mean(np.abs(test_y - lgbm_preds))
        print(f'MAE={lgbm_mae:.2f}')
        lgbm_importances.append(lgbm_fitted.feature_importances_)

        # ACF diffs
        acf_diffs_xgb, acf_act, acf_xgb = compute_acf_diff(test_y, xgb_preds)
        acf_diffs_lgbm, _, acf_lgbm = compute_acf_diff(test_y, lgbm_preds)
        max_acf_xgb = np.max(acf_diffs_xgb[1:])  # skip lag 0 (always 0)
        max_acf_lgbm = np.max(acf_diffs_lgbm[1:])
        argmax_xgb = np.argmax(acf_diffs_xgb[1:]) + 1
        argmax_lgbm = np.argmax(acf_diffs_lgbm[1:]) + 1
        print(
            f'  Max ACF diff — XGBoost: {max_acf_xgb:.4f} (lag {argmax_xgb})  '
            f'LightGBM: {max_acf_lgbm:.4f} (lag {argmax_lgbm})'
        )
        all_acf_diffs[region] = {
            'xgb': {
                'max_diff': max_acf_xgb,
                'at_lag': int(argmax_xgb),
                'acf_actual': acf_act.tolist(),
                'acf_pred': acf_xgb.tolist(),
            },
            'lgbm': {
                'max_diff': max_acf_lgbm,
                'at_lag': int(argmax_lgbm),
                'acf_actual': acf_act.tolist(),
                'acf_pred': acf_lgbm.tolist(),
            },
        }

    # Average importances across regions
    avg_xgb_imp = np.mean(xgb_importances, axis=0)
    avg_lgbm_imp = np.mean(lgbm_importances, axis=0)

    # Normalize LightGBM importances to [0,1] range (uses split counts by default)
    if avg_lgbm_imp.max() > 0:
        avg_lgbm_imp = avg_lgbm_imp / avg_lgbm_imp.max()

    n_features = len(RECURSIVE_FEATURE_NAMES)
    feature_names = RECURSIVE_FEATURE_NAMES[:n_features]
    # Trim if model has fewer features (no exog)
    if len(avg_xgb_imp) < n_features:
        feature_names = feature_names[: len(avg_xgb_imp)]

    # ── Plot feature importances ──
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    plot_feature_importance(avg_xgb_imp, feature_names, 'XGBoost (Enhanced)', axes[0])
    plot_feature_importance(avg_lgbm_imp, feature_names, 'LightGBM (Enhanced)', axes[1])
    plt.tight_layout()
    imp_path = DOCS_DIR / 'benchmark_enhanced_features_importance.png'
    plt.savefig(imp_path, dpi=150)
    plt.close()
    print(f'\nSaved: {imp_path}')

    # ── Plot ACF comparison ──
    fig, axes = plt.subplots(len(all_acf_diffs), 2, figsize=(14, 4 * len(all_acf_diffs)))
    if len(all_acf_diffs) == 1:
        axes = axes.reshape(1, -1)
    for i, (region, acf_data) in enumerate(sorted(all_acf_diffs.items())):
        nlags = len(acf_data['xgb']['acf_actual'])
        lags = np.arange(nlags)

        ax = axes[i, 0]
        ax.bar(lags - 0.15, acf_data['xgb']['acf_actual'], width=0.3, label='Actual', alpha=0.7)
        ax.bar(lags + 0.15, acf_data['xgb']['acf_pred'], width=0.3, label='XGBoost pred', alpha=0.7)
        ax.set_title(f'{region} — XGBoost ACF')
        ax.set_xlabel('Lag')
        ax.set_ylabel('ACF')
        ax.legend(fontsize=7)

        ax = axes[i, 1]
        ax.bar(lags - 0.15, acf_data['lgbm']['acf_actual'], width=0.3, label='Actual', alpha=0.7)
        ax.bar(lags + 0.15, acf_data['lgbm']['acf_pred'], width=0.3, label='LightGBM pred', alpha=0.7)
        ax.set_title(f'{region} — LightGBM ACF')
        ax.set_xlabel('Lag')
        ax.legend(fontsize=7)

    plt.tight_layout()
    acf_path = DOCS_DIR / 'benchmark_enhanced_features_acf.png'
    plt.savefig(acf_path, dpi=150)
    plt.close()
    print(f'Saved: {acf_path}')

    # ── Print summary tables ──
    print('\n' + '=' * 70)
    print('FEATURE IMPORTANCE (cross-region average, top 10)')
    print('=' * 70)

    for name, imp in [('XGBoost', avg_xgb_imp), ('LightGBM', avg_lgbm_imp)]:
        print(f'\n  {name}:')
        sorted_idx = np.argsort(imp)[::-1]
        for rank, idx in enumerate(sorted_idx[:10], 1):
            print(f'    {rank:2d}. {feature_names[idx]:25s} {imp[idx]:.4f}')

    print('\n' + '=' * 70)
    print('MAX ACF DIFF (lag 1-48)')
    print('=' * 70)
    print(f'\n  {"Region":30s} {"XGBoost":>15s} {"LightGBM":>15s}')
    print(f'  {"-" * 30} {"-" * 15} {"-" * 15}')
    for region in sorted(all_acf_diffs.keys()):
        d = all_acf_diffs[region]
        print(
            f'  {region:30s} {d["xgb"]["max_diff"]:.4f} (lag {d["xgb"]["at_lag"]:2d})'
            f'  {d["lgbm"]["max_diff"]:.4f} (lag {d["lgbm"]["at_lag"]:2d})'
        )


if __name__ == '__main__':
    main()
