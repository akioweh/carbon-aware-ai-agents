#!/usr/bin/env python3
"""
Weather-Enriched Features Experiment (Stage 5).

Tests whether richer weather features and engineered transformations improve
forecast accuracy, especially at longer horizons where lag features are stale.

Carbon intensity is driven by generation mix, which is driven by weather:
  - Wind → wind generation (25-40% UK electricity). Power ∝ wind_speed³.
  - Solar → affected by cloud cover, radiation type.
  - Temperature → demand (heating/cooling). Pressure systems affect wind.

Variants:
  A: Extended raw weather (11 features)
  B: Extended + engineered (15 features)
  C: Engineered only (3 original + 4 engineered = 7 features)

All variants keep the same seasonal feature set (11 cyclical + 20 lags + 8 rolling)
from Stage 4, only changing weather features.

Usage:
    python3 benchmark_weather.py
"""

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
    load_data, REGION_COORDS,
    compute_metrics,
)
from benchmark_seasonal import (
    MODELS, BEST_VARIANTS,
    build_seasonal_cyclical, build_seasonal_lag_features,
    build_seasonal_ml_features, SEASONAL_LAGS, SEASONAL_ROLLING_CONFIGS,
    _get_model_params, _create_model,
    build_direct_features_seasonal,
)
from benchmark_residual import build_residual_training_data

DOCS_DIR = Path(__file__).resolve().parent.parent / 'docs'
RESULTS_PATH = Path(__file__).parent / 'weather_results.json'
WEATHER_CACHE_PATH = Path(__file__).parent / 'weather_extended_cache.json'

# ── Weather Feature Definitions ──────────────────────────────────────────

# Original 3 weather features (from Open-Meteo)
ORIGINAL_WEATHER = ['wind_speed', 'temperature', 'solar_radiation']

# Extended raw weather features (8 new + 3 original = 11)
EXTENDED_RAW_FIELDS = [
    'wind_speed_10m', 'temperature_2m', 'shortwave_radiation',       # original 3
    'wind_speed_100m', 'wind_gusts_10m', 'wind_direction_10m',       # wind extras
    'cloud_cover', 'relative_humidity_2m', 'pressure_msl',           # atmosphere
    'diffuse_radiation', 'direct_normal_irradiance',                  # solar extras
]

# Mapping from API field names to our column names
FIELD_TO_COL = {
    'wind_speed_10m': 'wind_speed',
    'temperature_2m': 'temperature',
    'shortwave_radiation': 'solar_radiation',
    'wind_speed_100m': 'wind_speed_100m',
    'wind_gusts_10m': 'wind_gusts_10m',
    'wind_direction_10m': 'wind_direction_10m',
    'cloud_cover': 'cloud_cover',
    'relative_humidity_2m': 'relative_humidity_2m',
    'pressure_msl': 'pressure_msl',
    'diffuse_radiation': 'diffuse_radiation',
    'direct_normal_irradiance': 'direct_normal_irradiance',
}

ALL_RAW_COLS = list(FIELD_TO_COL.values())  # 11 columns

ENGINEERED_COLS = [
    'wind_power_proxy',        # wind_speed_100m³
    'wind_power_proxy_10m',    # wind_speed_10m³
    'solar_effective',         # shortwave_radiation × (1 - cloud_cover/100)
    'temp_demand_proxy',       # |temperature - 18|
]

# Variant definitions
VARIANT_A_COLS = ALL_RAW_COLS                          # 11 raw
VARIANT_B_COLS = ALL_RAW_COLS + ENGINEERED_COLS        # 11 raw + 4 engineered = 15
VARIANT_C_COLS = ORIGINAL_WEATHER + ENGINEERED_COLS    # 3 original + 4 engineered = 7

VARIANTS = {
    'A_extended_raw': VARIANT_A_COLS,
    'B_extended_engineered': VARIANT_B_COLS,
    'C_engineered_only': VARIANT_C_COLS,
}


# ── Extended Weather Data Fetching ───────────────────────────────────────

def fetch_extended_weather(regions, date_min, date_max):
    """Fetch extended weather data from Open-Meteo archive API with caching."""
    import requests

    # Check cache
    if WEATHER_CACHE_PATH.exists():
        try:
            cache = json.loads(WEATHER_CACHE_PATH.read_text())
            if cache.get('date_min') == date_min and cache.get('date_max') == date_max:
                cached_regions = set(cache.get('regions', []))
                if set(regions).issubset(cached_regions):
                    print(f"  Using cached extended weather from {WEATHER_CACHE_PATH.name}")
                    wdf = pd.DataFrame(cache['data'])
                    wdf['ts'] = pd.to_datetime(wdf['ts'], utc=True)
                    return wdf[wdf['region'].isin(regions)].reset_index(drop=True)
        except (json.JSONDecodeError, KeyError):
            pass

    fields = ','.join(EXTENDED_RAW_FIELDS)
    all_rows = []

    # Chunk requests if range > 90 days
    date_range_days = (pd.Timestamp(date_max) - pd.Timestamp(date_min)).days

    for region in regions:
        if region not in REGION_COORDS:
            print(f"  WARNING: No coordinates for {region}, skipping")
            continue
        lat, lon = REGION_COORDS[region]
        print(f"  Fetching extended weather for {region} ({lat}, {lon})...")

        region_chunks = []
        chunk_start = pd.Timestamp(date_min)
        chunk_end_final = pd.Timestamp(date_max)

        while chunk_start < chunk_end_final:
            chunk_end = min(chunk_start + pd.Timedelta(days=89), chunk_end_final)
            url = (
                f"https://archive-api.open-meteo.com/v1/archive"
                f"?latitude={lat}&longitude={lon}"
                f"&start_date={chunk_start.strftime('%Y-%m-%d')}"
                f"&end_date={chunk_end.strftime('%Y-%m-%d')}"
                f"&hourly={fields}"
            )
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                hourly = data.get('hourly', {})
                times = hourly.get('time', [])
                if times:
                    hdf = pd.DataFrame({'ts': pd.to_datetime(times, utc=True)})
                    for api_field, col_name in FIELD_TO_COL.items():
                        hdf[col_name] = hourly.get(api_field, [np.nan] * len(times))
                    region_chunks.append(hdf)
            except Exception as e:
                print(f"    WARNING: Chunk {chunk_start.date()} to {chunk_end.date()} failed: {e}")
            chunk_start = chunk_end + pd.Timedelta(days=1)

        if region_chunks:
            rdf = pd.concat(region_chunks, ignore_index=True)
            rdf = rdf.drop_duplicates(subset=['ts']).sort_values('ts').reset_index(drop=True)
            rdf = rdf.set_index('ts').sort_index()
            # Interpolate to 30-min
            full_idx = pd.date_range(rdf.index.min(), rdf.index.max(), freq='30min', tz='UTC')
            rdf = rdf.reindex(full_idx).interpolate(method='time').reset_index()
            rdf.columns = ['ts'] + ALL_RAW_COLS
            rdf['region'] = region
            all_rows.append(rdf)
            print(f"    Got {len(rdf)} points")

    if not all_rows:
        return pd.DataFrame()

    weather_df = pd.concat(all_rows, ignore_index=True)

    # Cache
    cache_data = {
        'date_min': date_min,
        'date_max': date_max,
        'regions': list(set(weather_df['region'])),
        'data': weather_df.to_dict(orient='list'),
    }
    cache_data['data']['ts'] = [str(t) for t in cache_data['data']['ts']]
    WEATHER_CACHE_PATH.write_text(json.dumps(cache_data))
    print(f"  Cached to {WEATHER_CACHE_PATH.name}")

    return weather_df


def engineer_weather_features(df):
    """Add engineered weather columns to a DataFrame that has raw weather cols."""
    ws100 = df.get('wind_speed_100m', df.get('wind_speed', pd.Series(0, index=df.index)))
    ws10 = df.get('wind_speed', pd.Series(0, index=df.index))
    sr = df.get('solar_radiation', pd.Series(0, index=df.index))
    cc = df.get('cloud_cover', pd.Series(50, index=df.index))
    temp = df.get('temperature', pd.Series(15, index=df.index))

    df = df.copy()
    df['wind_power_proxy'] = np.clip(ws100 ** 3, 0, 50000)
    df['wind_power_proxy_10m'] = np.clip(ws10 ** 3, 0, 50000)
    df['solar_effective'] = sr * (1 - cc / 100.0)
    df['temp_demand_proxy'] = np.abs(temp - 18.0)
    return df


# ── Recursive Forecast (Weather Variant) ─────────────────────────────────

def recursive_forecast_weather(model, train_ts, train_y, test_ts, test_y_actual,
                               train_exog=None, test_exog=None,
                               use_residual_target=False):
    """Recursive multi-step forecast with seasonal features + weather exog."""
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None

    all_ts = pd.concat([train_ts, test_ts]).reset_index(drop=True)
    known_values = list(train_y)

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

    preds = np.zeros(n_test)
    for t in range(n_test):
        idx = n_train + t
        ts_point = pd.Series([all_ts.iloc[idx]])
        cyclical = build_seasonal_cyclical(ts_point)

        lag_feats = {}
        for lag in SEASONAL_LAGS:
            lookback_idx = idx - lag
            if lookback_idx >= 0:
                lag_feats[f'lag_{lag}'] = known_values[lookback_idx]
            else:
                lag_feats[f'lag_{lag}'] = np.nan

        for window, stat in SEASONAL_ROLLING_CONFIGS:
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


# ── Direct Forecast (Weather Variant) ────────────────────────────────────

def build_direct_features_weather(train_ts, train_y, test_ts,
                                  train_exog=None, test_exog=None,
                                  use_residual_target=False):
    """Direct features with seasonal cyclical + extended origin summary + weather exog."""
    return build_direct_features_seasonal(
        train_ts, train_y, test_ts,
        train_exog=train_exog, test_exog=test_exog,
        use_residual_target=use_residual_target,
    )


# ── Train/Predict ────────────────────────────────────────────────────────

def train_predict_weather(model_name, train_ts, train_y, test_ts, test_y=None,
                          train_exog=None, test_exog=None):
    """Train/predict using seasonal features + weather exog variant."""
    t0 = time.time()
    variant = BEST_VARIANTS[model_name]
    params = _get_model_params(model_name)

    if model_name == 'Direct-XGBoost':
        use_residual = (variant == 'residual')
        X, y, X_test = build_direct_features_weather(
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
        use_residual = (variant == 'residual')
        model = _create_model(model_name, params)
        if test_y is None:
            test_y = np.zeros(len(test_ts))
        preds = recursive_forecast_weather(
            model, train_ts, train_y, test_ts, test_y,
            train_exog=train_exog, test_exog=test_exog,
            use_residual_target=use_residual,
        )
        return preds, time.time() - t0


# ── Prepare Exogenous Features for a Variant ─────────────────────────────

def prepare_exog(weather_df, region, train_df, test_df, variant_cols):
    """Merge weather data, engineer features, lag-1 shift, return train/test exog arrays."""
    rwx = weather_df[weather_df['region'] == region].sort_values('ts')
    if len(rwx) == 0:
        return None, None

    combined = pd.concat([train_df, test_df]).reset_index(drop=True)

    # Merge raw weather columns
    merge_cols = [c for c in ALL_RAW_COLS if c in rwx.columns]
    merged = combined.merge(rwx[['ts'] + merge_cols], on='ts', how='left')

    # Interpolate missing weather
    for col in merge_cols:
        merged[col] = merged[col].interpolate(method='linear')

    # Engineer features
    merged = engineer_weather_features(merged)

    # Select variant columns (only those that exist)
    cols = [c for c in variant_cols if c in merged.columns]
    if not cols:
        return None, None

    # Lag-1 shift all weather features
    for col in cols:
        merged[col] = merged[col].shift(1)
    merged[cols] = merged[cols].fillna(0)

    n_train = len(train_df)
    train_exog = merged[cols].iloc[:n_train].values
    test_exog = merged[cols].iloc[n_train:].values
    return train_exog, test_exog


# ── Per-Horizon MAE ──────────────────────────────────────────────────────

def compute_horizon_mae(test_y, preds, interval_minutes=30):
    """Compute MAE at day 1, 3, 5, 7 horizons."""
    points_per_day = int(24 * 60 / interval_minutes)
    horizon_days = [1, 3, 5, 7]
    result = {}
    for day in horizon_days:
        start = (day - 1) * points_per_day
        end = day * points_per_day
        if start < len(test_y) and start < len(preds):
            actual_end = min(end, len(test_y), len(preds))
            mae = float(np.mean(np.abs(test_y[start:actual_end] - preds[start:actual_end])))
            result[f'day_{day}'] = mae
    return result


# ── Feature Importance ───────────────────────────────────────────────────

def extract_feature_importance(model_name, train_ts, train_y, train_exog, weather_col_names):
    """Train model and return feature importances dict."""
    variant = BEST_VARIANTS[model_name]
    use_residual = (variant == 'residual')
    params = _get_model_params(model_name)

    train_features = build_seasonal_ml_features(train_ts, train_y)
    feature_names = list(train_features.columns) + list(weather_col_names)

    if use_residual:
        X_train, y_train, _ = build_residual_training_data(train_features, train_y)
        valid_mask = train_features.notna().all(axis=1).values
        X_train = np.column_stack([X_train, train_exog[valid_mask]])
    else:
        valid_mask = train_features.notna().all(axis=1)
        X_train = train_features[valid_mask].values
        X_train = np.column_stack([X_train, train_exog[valid_mask.values]])
        y_train = train_y[valid_mask.values]

    model = _create_model(model_name, params)
    model.fit(X_train, y_train)
    importances = model.feature_importances_
    return dict(zip(feature_names, importances))


# ── Visualization ────────────────────────────────────────────────────────

def generate_comparison_chart(results_by_variant, baseline_maes, output_path):
    """Bar chart comparing variants + baseline."""
    variant_names = ['Baseline'] + list(results_by_variant.keys())
    n_variants = len(variant_names)

    x = np.arange(len(MODELS))
    width = 0.8 / n_variants
    colors = ['#95a5a6', '#4a90d9', '#e74c3c', '#2ecc71', '#f39c12']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, vname in enumerate(variant_names):
        if vname == 'Baseline':
            maes = [baseline_maes.get(m, 0) for m in MODELS]
        else:
            maes = [results_by_variant[vname].get(m, 0) for m in MODELS]
        offset = (i - n_variants / 2 + 0.5) * width
        bars = ax.bar(x + offset, maes, width, label=vname, color=colors[i % len(colors)])
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3,
                        f'{h:.1f}', ha='center', va='bottom', fontsize=6)

    ax.set_xlabel('Model')
    ax.set_ylabel('MAE (gCO2/kWh)')
    ax.set_title('Weather-Enriched Features: MAE by Variant')
    ax.set_xticks(x)
    ax.set_xticklabels(MODELS, rotation=15, ha='right')
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_predictions_chart(test_ts, test_y, all_preds, output_path):
    """Predictions vs actual for best variant."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(test_ts, test_y, 'k-', linewidth=1.5, label='Actual', alpha=0.8)

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
    for (name, preds), color in zip(all_preds.items(), colors):
        ax.plot(test_ts[:len(preds)], preds, '-', color=color, linewidth=1,
                label=name, alpha=0.7)

    ax.set_xlabel('Time')
    ax.set_ylabel('Carbon Intensity (gCO2/kWh)')
    ax.set_title('Weather-Enriched: Predictions vs Actual (Best Variant)')
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_importance_chart(importance_dicts, output_path):
    """Feature importance comparison."""
    n_models = len(importance_dicts)
    if n_models == 0:
        return

    fig, axes = plt.subplots(1, n_models, figsize=(7 * n_models, 6))
    if n_models == 1:
        axes = [axes]

    for ax, (model_name, imp) in zip(axes, importance_dicts.items()):
        sorted_imp = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:20]
        names = [n for n, _ in sorted_imp]
        vals = [v for _, v in sorted_imp]
        # Color weather features differently
        weather_set = set(ALL_RAW_COLS + ENGINEERED_COLS)
        bar_colors = ['#e74c3c' if n in weather_set else '#3498db' for n in names]
        ax.barh(range(len(names)), vals, color=bar_colors)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=7)
        ax.set_xlabel('Importance')
        ax.set_title(f'{model_name} (Weather-Enriched)')
        ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


def generate_horizon_chart(horizon_data, baseline_horizon, output_path):
    """MAE by forecast horizon for each variant vs baseline."""
    days = [1, 3, 5, 7]
    day_labels = ['Day 1', 'Day 3', 'Day 5', 'Day 7']

    # Average across models for each variant
    fig, axes = plt.subplots(1, len(MODELS), figsize=(4 * len(MODELS), 5), sharey=True)

    variant_names = ['Baseline'] + list(horizon_data.keys())
    colors = ['#95a5a6', '#4a90d9', '#e74c3c', '#2ecc71']
    linestyles = ['-', '-', '--', '-.']

    for ax_idx, model_name in enumerate(MODELS):
        ax = axes[ax_idx]

        # Baseline
        if model_name in baseline_horizon:
            bh = baseline_horizon[model_name]
            vals = [bh.get(f'day_{d}', np.nan) for d in days]
            ax.plot(days, vals, color=colors[0], linestyle=linestyles[0],
                    marker='o', markersize=4, label='Baseline', linewidth=1.5)

        for vi, (vname, vdata) in enumerate(horizon_data.items()):
            if model_name in vdata:
                vh = vdata[model_name]
                vals = [vh.get(f'day_{d}', np.nan) for d in days]
                ax.plot(days, vals, color=colors[vi + 1], linestyle=linestyles[(vi + 1) % len(linestyles)],
                        marker='s', markersize=4, label=vname, linewidth=1.5)

        ax.set_xlabel('Forecast Day')
        if ax_idx == 0:
            ax.set_ylabel('MAE (gCO2/kWh)')
        ax.set_title(model_name, fontsize=9)
        ax.set_xticks(days)
        ax.set_xticklabels(day_labels, fontsize=7)
        if ax_idx == 0:
            ax.legend(fontsize=6)

    plt.suptitle('MAE by Forecast Horizon: Weather Variants vs Baseline', fontsize=12)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved: {output_path}")


# ── Report Generation ────────────────────────────────────────────────────

def generate_report(all_results, baseline_maes, horizon_data, baseline_horizon, output_path):
    """Generate markdown report."""
    lines = [
        '# Weather-Enriched Features Experiment (Stage 5)',
        '',
        '## Experiment Design',
        '',
        '### Hypothesis',
        '',
        'Richer weather features and engineered transformations improve forecast',
        'accuracy, especially at longer horizons (day 3-7) where lag features',
        'are stale but weather forecasts remain fresh exogenous signals.',
        '',
        '### Weather Features',
        '',
        '**Original (3):** wind_speed_10m, temperature_2m, shortwave_radiation',
        '',
        '**New raw (8):** wind_speed_100m, wind_gusts_10m, wind_direction_10m,',
        'cloud_cover, relative_humidity_2m, pressure_msl, diffuse_radiation,',
        'direct_normal_irradiance',
        '',
        '**Engineered (4):**',
        '- wind_power_proxy = wind_speed_100m³ (cubic power law)',
        '- wind_power_proxy_10m = wind_speed_10m³',
        '- solar_effective = shortwave_radiation × (1 - cloud_cover/100)',
        '- temp_demand_proxy = |temperature - 18|',
        '',
        '### Variants',
        '',
        '| Variant | Weather Features | Count |',
        '|---------|-----------------|-------|',
        '| Baseline (Stage 4) | 3 original raw | 3 |',
        '| A: Extended raw | 11 raw | 11 |',
        '| B: Extended + engineered | 11 raw + 4 engineered | 15 |',
        '| C: Engineered only | 3 original + 4 engineered | 7 |',
        '',
        '## Results',
        '',
    ]

    # Per-variant results table
    for vname in sorted(all_results.keys()):
        vdata = all_results[vname]
        lines.append(f'### Variant {vname}')
        lines.append('')

        regions = sorted({r for r in vdata})
        lines.append('| Model | ' + ' | '.join(regions) + ' | Cross-Region Avg |')
        lines.append('|-------|' + '|'.join(['-------'] * len(regions)) + '|----------------|')

        for model_name in MODELS:
            row = [f'| {model_name}']
            maes = []
            for region in regions:
                r = vdata.get(region, {}).get(model_name)
                if r is not None:
                    mae = r['metrics']['MAE']
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

    # Comparison with baseline
    lines.append('## Comparison with Stage 4 Baseline')
    lines.append('')
    lines.append('| Model | Baseline | Variant A | Variant B | Variant C | Best Delta |')
    lines.append('|-------|----------|-----------|-----------|-----------|------------|')

    for model_name in MODELS:
        bl = baseline_maes.get(model_name, float('nan'))
        variant_avgs = {}
        for vname in sorted(all_results.keys()):
            vdata = all_results[vname]
            maes = []
            for region in vdata:
                r = vdata[region].get(model_name)
                if r is not None:
                    maes.append(r['metrics']['MAE'])
            if maes:
                variant_avgs[vname] = np.mean(maes)

        va = variant_avgs.get('A_extended_raw', float('nan'))
        vb = variant_avgs.get('B_extended_engineered', float('nan'))
        vc = variant_avgs.get('C_engineered_only', float('nan'))
        best_val = min(va, vb, vc) if not all(np.isnan([va, vb, vc])) else float('nan')
        delta = best_val - bl if not np.isnan(best_val) and not np.isnan(bl) else float('nan')
        sign = '+' if delta > 0 else ''
        lines.append(f'| {model_name} | {bl:.2f} | {va:.2f} | {vb:.2f} | {vc:.2f} | {sign}{delta:.2f} |')

    lines.append('')
    lines.append('*Negative delta = weather variant improved over baseline.*')
    lines.append('')

    # Horizon analysis
    lines.append('## Per-Horizon MAE Analysis')
    lines.append('')
    lines.append('MAE at different forecast horizons (cross-region average):')
    lines.append('')

    for model_name in MODELS:
        lines.append(f'### {model_name}')
        lines.append('')
        lines.append('| Horizon | Baseline | Variant A | Variant B | Variant C |')
        lines.append('|---------|----------|-----------|-----------|-----------|')
        for day in [1, 3, 5, 7]:
            key = f'day_{day}'
            bl_val = baseline_horizon.get(model_name, {}).get(key, float('nan'))
            vals = []
            for vname in ['A_extended_raw', 'B_extended_engineered', 'C_engineered_only']:
                v = horizon_data.get(vname, {}).get(model_name, {}).get(key, float('nan'))
                vals.append(v)
            lines.append(f'| Day {day} | {bl_val:.2f} | {vals[0]:.2f} | {vals[1]:.2f} | {vals[2]:.2f} |')
        lines.append('')

    output_path.write_text('\n'.join(lines))
    print(f"Saved: {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    total_days = (df['ts'].max() - df['ts'].min()).days
    print(f"Regions: {regions}")
    print(f"Date range: {df['ts'].min()} -> {df['ts'].max()} ({total_days} days)")

    if total_days < 30:
        print("ERROR: Not enough data. Run: python3 carbon_collector.py backfill 365")
        sys.exit(1)

    # Fetch extended weather data
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print("\nFetching extended weather data...")
    weather_df = fetch_extended_weather(regions, date_min, date_max)

    if len(weather_df) == 0:
        print("ERROR: No weather data fetched. Cannot run weather experiment.")
        sys.exit(1)
    print(f"Extended weather data: {len(weather_df)} points, "
          f"columns: {[c for c in weather_df.columns if c not in ('ts', 'region')]}")

    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)

    # ── Run baseline (original 3 weather features) for comparison ────────
    print("\n" + "=" * 70)
    print("BASELINE (Stage 4 seasonal, 3 weather features)")
    print("=" * 70)

    baseline_results = {}
    baseline_preds = {}
    baseline_horizon_all = {}  # model -> list of per-region horizon dicts
    last_test_ts = None
    last_test_y = None

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)
        if len(test) == 0 or len(train) < 400:
            continue

        train_exog, test_exog = prepare_exog(weather_df, region, train, test, ORIGINAL_WEATHER)
        train_ts = train['ts'].reset_index(drop=True)
        train_y = train['actual'].values
        test_ts = test['ts'].reset_index(drop=True)
        test_y = test['actual'].values

        print(f"\n  {region}: train={len(train)}, test={len(test)}")
        for model_name in MODELS:
            print(f"    {model_name}...", end=' ', flush=True)
            try:
                preds, elapsed = train_predict_weather(
                    model_name, train_ts, train_y, test_ts, test_y,
                    train_exog=train_exog, test_exog=test_exog,
                )
                min_len = min(len(preds), len(test_y))
                metrics = compute_metrics(test_y[:min_len], preds[:min_len], n_features=40)
                print(f"MAE={metrics['MAE']:.2f} ({elapsed:.1f}s)")

                if region not in baseline_results:
                    baseline_results[region] = {}
                baseline_results[region][model_name] = {
                    'metrics': metrics, 'time': elapsed, 'preds': preds.tolist(),
                }
                baseline_preds[model_name] = preds
                last_test_ts = test_ts
                last_test_y = test_y

                # Horizon MAE
                hmae = compute_horizon_mae(test_y[:min_len], preds[:min_len])
                if model_name not in baseline_horizon_all:
                    baseline_horizon_all[model_name] = []
                baseline_horizon_all[model_name].append(hmae)

            except Exception as e:
                print(f"FAILED: {e}")

    # Average baseline MAEs and horizon MAEs
    baseline_maes = {}
    for model_name in MODELS:
        maes = [baseline_results[r][model_name]['metrics']['MAE']
                for r in baseline_results if model_name in baseline_results[r]]
        if maes:
            baseline_maes[model_name] = np.mean(maes)

    baseline_horizon_avg = {}
    for model_name, horizon_list in baseline_horizon_all.items():
        avg = {}
        for key in ['day_1', 'day_3', 'day_5', 'day_7']:
            vals = [h[key] for h in horizon_list if key in h]
            if vals:
                avg[key] = np.mean(vals)
        baseline_horizon_avg[model_name] = avg

    print("\nBaseline cross-region avg MAE:")
    for m, mae in baseline_maes.items():
        print(f"  {m:20s}: {mae:.2f}")

    # ── Run weather variants ─────────────────────────────────────────────
    all_variant_results = {}  # variant -> region -> model -> result
    all_variant_horizon = {}  # variant -> model -> horizon dict (averaged)
    best_variant_preds = {}   # model -> preds (from best variant)
    all_importances = {}      # model -> importance dict (from best variant)

    for vname, vcols in VARIANTS.items():
        print(f"\n{'=' * 70}")
        print(f"VARIANT {vname} ({len(vcols)} weather features)")
        print(f"  Features: {vcols}")
        print(f"{'=' * 70}")

        variant_results = {}
        variant_horizon_all = {}  # model -> list of per-region horizon dicts

        for region in regions:
            rdf = df[df['region'] == region].copy().reset_index(drop=True)
            train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
            test = rdf[rdf['ts'] > split_date].reset_index(drop=True)
            if len(test) == 0 or len(train) < 400:
                continue

            train_exog, test_exog = prepare_exog(weather_df, region, train, test, vcols)
            if train_exog is None:
                print(f"  {region}: no weather data, skipping")
                continue

            train_ts = train['ts'].reset_index(drop=True)
            train_y = train['actual'].values
            test_ts = test['ts'].reset_index(drop=True)
            test_y = test['actual'].values

            print(f"\n  {region}: train={len(train)}, test={len(test)}, "
                  f"exog_cols={train_exog.shape[1]}")

            region_results = {}
            for model_name in MODELS:
                print(f"    {model_name}...", end=' ', flush=True)
                try:
                    preds, elapsed = train_predict_weather(
                        model_name, train_ts, train_y, test_ts, test_y,
                        train_exog=train_exog, test_exog=test_exog,
                    )
                    min_len = min(len(preds), len(test_y))
                    metrics = compute_metrics(test_y[:min_len], preds[:min_len],
                                              n_features=40 + len(vcols))
                    print(f"MAE={metrics['MAE']:.2f} ({elapsed:.1f}s)")

                    region_results[model_name] = {
                        'metrics': metrics, 'time': elapsed, 'preds': preds.tolist(),
                    }

                    # Horizon MAE
                    hmae = compute_horizon_mae(test_y[:min_len], preds[:min_len])
                    if model_name not in variant_horizon_all:
                        variant_horizon_all[model_name] = []
                    variant_horizon_all[model_name].append(hmae)

                    # Save preds for best variant plotting
                    if model_name not in best_variant_preds:
                        best_variant_preds[model_name] = preds

                except Exception as e:
                    print(f"FAILED: {e}")
                    import traceback
                    traceback.print_exc()

            variant_results[region] = region_results

        all_variant_results[vname] = variant_results

        # Average horizon MAEs for this variant
        variant_horizon_avg = {}
        for model_name, horizon_list in variant_horizon_all.items():
            avg = {}
            for key in ['day_1', 'day_3', 'day_5', 'day_7']:
                vals = [h[key] for h in horizon_list if key in h]
                if vals:
                    avg[key] = np.mean(vals)
            variant_horizon_avg[model_name] = avg
        all_variant_horizon[vname] = variant_horizon_avg

    # Feature importance for best variant (B)
    print("\nExtracting feature importance (Variant B)...")
    best_v_cols = VARIANT_B_COLS
    for imp_model in ['XGBoost', 'LightGBM', 'CatBoost']:
        try:
            # Use first region with enough data
            for region in regions:
                rdf = df[df['region'] == region].copy().reset_index(drop=True)
                train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
                if len(train) >= 2000:
                    train_exog, _ = prepare_exog(weather_df, region, train,
                                                 train.iloc[:1], best_v_cols)
                    if train_exog is not None:
                        imp = extract_feature_importance(
                            imp_model,
                            train['ts'].reset_index(drop=True),
                            train['actual'].values,
                            train_exog,
                            best_v_cols,
                        )
                        all_importances[imp_model] = imp
                        print(f"  {imp_model}: top 5 = "
                              f"{sorted(imp.items(), key=lambda x: -x[1])[:5]}")
                        break
        except Exception as e:
            print(f"  {imp_model} importance failed: {e}")

    # ── Compute cross-region averages per variant ────────────────────────
    variant_avg_maes = {}
    for vname in all_variant_results:
        vdata = all_variant_results[vname]
        avg = {}
        for model_name in MODELS:
            maes = [vdata[r][model_name]['metrics']['MAE']
                    for r in vdata if model_name in vdata[r]]
            if maes:
                avg[model_name] = np.mean(maes)
        variant_avg_maes[vname] = avg

    # ── Save results ─────────────────────────────────────────────────────
    save_data = {
        'baseline_maes': baseline_maes,
        'baseline_horizon': baseline_horizon_avg,
        'variant_maes': variant_avg_maes,
        'variant_horizon': {v: {m: h for m, h in hdata.items()}
                            for v, hdata in all_variant_horizon.items()},
        'variant_results': {},
    }
    for vname in all_variant_results:
        save_data['variant_results'][vname] = {}
        for region in all_variant_results[vname]:
            save_data['variant_results'][vname][region] = {}
            for model in all_variant_results[vname][region]:
                r = all_variant_results[vname][region][model]
                save_data['variant_results'][vname][region][model] = {
                    'metrics': r['metrics'], 'time': r['time'],
                }
    RESULTS_PATH.write_text(json.dumps(save_data, indent=2))
    print(f"\nResults saved to {RESULTS_PATH}")

    # ── Generate visualizations ──────────────────────────────────────────
    print("\nGenerating visualizations...")

    generate_comparison_chart(variant_avg_maes, baseline_maes,
                              DOCS_DIR / 'benchmark_weather_comparison.png')

    if last_test_ts is not None and best_variant_preds:
        generate_predictions_chart(last_test_ts, last_test_y, best_variant_preds,
                                   DOCS_DIR / 'benchmark_weather_predictions.png')

    if all_importances:
        generate_importance_chart(all_importances,
                                  DOCS_DIR / 'benchmark_weather_importance.png')

    generate_horizon_chart(all_variant_horizon, baseline_horizon_avg,
                           DOCS_DIR / 'benchmark_weather_horizon.png')

    generate_report(all_variant_results, baseline_maes,
                    all_variant_horizon, baseline_horizon_avg,
                    DOCS_DIR / 'benchmark_weather.md')

    # ── Print summary ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WEATHER EXPERIMENT COMPLETE")
    print("=" * 70)
    print("\nCross-region average MAE:")
    header = f"{'Model':20s} {'Baseline':>10s}"
    for vname in sorted(variant_avg_maes.keys()):
        header += f" {vname:>25s}"
    print(header)
    print("-" * len(header))

    for model_name in MODELS:
        bl = baseline_maes.get(model_name, float('nan'))
        row = f"{model_name:20s} {bl:10.2f}"
        for vname in sorted(variant_avg_maes.keys()):
            v = variant_avg_maes[vname].get(model_name, float('nan'))
            delta = v - bl if not np.isnan(v) and not np.isnan(bl) else float('nan')
            sign = '+' if delta > 0 else ''
            row += f" {v:10.2f} ({sign}{delta:.2f})"
        print(row)

    print("\nBest model per variant:")
    for vname in ['Baseline'] + sorted(variant_avg_maes.keys()):
        if vname == 'Baseline':
            maes = baseline_maes
        else:
            maes = variant_avg_maes[vname]
        if maes:
            best = min(maes, key=maes.get)
            print(f"  {vname}: {best} = {maes[best]:.2f}")


if __name__ == '__main__':
    main()
