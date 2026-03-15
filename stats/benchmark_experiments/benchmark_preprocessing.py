#!/usr/bin/env python3
"""
Preprocessing experiment: can smarter feature engineering beat Direct-Ridge MAE 32.99?

Tests 7 variants of feature engineering and target preprocessing against the
baseline Direct-Ridge model. All variants use Ridge regression with the same
train/test split (full backfill only).

    python3 benchmark_preprocessing.py

Outputs:
    docs/benchmark_preprocessing_comparison.png  — grouped bar chart of MAE
    docs/benchmark_preprocessing_predictions.png — predictions vs actual
    Appends results to docs/comparison_report.md
"""

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from statsmodels.tsa.seasonal import STL

warnings.filterwarnings('ignore')

# Reuse infrastructure from benchmark.py
from benchmark import (
    DB_PATH, TEST_DAYS, WEATHER_FEATURES, DOCS_DIR,
    load_data, fetch_weather_data,
    build_cyclical_features, _build_direct_features,
    compute_metrics,
)

# ── Feature builders ─────────────────────────────────────────────────────

def build_onehot_features(timestamps: pd.Series) -> pd.DataFrame:
    """48 half-hour-of-day + 7 day-of-week binary columns."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hh = ts.dt.hour * 2 + ts.dt.minute // 30  # 0..47
    dow = ts.dt.dayofweek  # 0..6

    hh_dummies = pd.get_dummies(hh, prefix='hh')
    dow_dummies = pd.get_dummies(dow, prefix='dow')

    # Ensure all columns present
    for i in range(48):
        col = f'hh_{i}'
        if col not in hh_dummies.columns:
            hh_dummies[col] = 0
    for i in range(7):
        col = f'dow_{i}'
        if col not in dow_dummies.columns:
            dow_dummies[col] = 0

    hh_dummies = hh_dummies[[f'hh_{i}' for i in range(48)]]
    dow_dummies = dow_dummies[[f'dow_{i}' for i in range(7)]]

    return pd.concat([hh_dummies.reset_index(drop=True),
                      dow_dummies.reset_index(drop=True)], axis=1)


def build_fourier_features(timestamps: pd.Series, n_harmonics: int = 3) -> pd.DataFrame:
    """Sin/cos features at 1st through nth harmonics for hour, DOW, minute."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute

    features = {}
    for k in range(1, n_harmonics + 1):
        features[f'hour_sin_{k}'] = np.sin(2 * np.pi * k * hour / 24)
        features[f'hour_cos_{k}'] = np.cos(2 * np.pi * k * hour / 24)
        features[f'dow_sin_{k}'] = np.sin(2 * np.pi * k * dow / 7)
        features[f'dow_cos_{k}'] = np.cos(2 * np.pi * k * dow / 7)
        features[f'min_sin_{k}'] = np.sin(2 * np.pi * k * minute_of_day / 1440)
        features[f'min_cos_{k}'] = np.cos(2 * np.pi * k * minute_of_day / 1440)
    return pd.DataFrame(features)


def smooth_ma(y: np.ndarray, window: int = 6) -> np.ndarray:
    """Trailing moving average (no lookahead). First `window-1` values use expanding mean."""
    s = pd.Series(y)
    return s.rolling(window, min_periods=1).mean().values


def diff_48(y: np.ndarray):
    """Day-over-day difference (48 half-hour periods). Returns (diffed, last_48)."""
    last_48 = y[:48].copy()
    d = y.copy()
    d[48:] = y[48:] - y[:-48]
    return d, last_48


def inverse_diff_48(y_diff_hat: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """Invert day-over-day differencing. anchor = last 48 values before test set."""
    out = np.zeros_like(y_diff_hat)
    for i in range(len(y_diff_hat)):
        if i < 48:
            out[i] = y_diff_hat[i] + anchor[i]
        else:
            out[i] = y_diff_hat[i] + out[i - 48]
    return out


def stl_decompose(ts: pd.Series, y: np.ndarray, period: int = 48):
    """STL decomposition. Returns (trend, seasonal, residual) arrays."""
    idx = pd.DatetimeIndex(ts)
    series = pd.Series(y, index=idx)
    # Interpolate any gaps for STL
    full_idx = pd.date_range(idx.min(), idx.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time')
    stl = STL(series, period=period, robust=True)
    result = stl.fit()
    # Re-align to original timestamps
    trend = result.trend.reindex(idx).interpolate(method='linear').values
    seasonal = result.seasonal.reindex(idx).interpolate(method='linear').values
    residual = y - trend - seasonal
    return trend, seasonal, residual


def stl_extrapolate(trend: np.ndarray, seasonal: np.ndarray, n_test: int, period: int = 48):
    """Extrapolate STL trend+seasonal for test period.
    Trend: last value carried forward. Seasonal: repeat last cycle."""
    trend_ext = np.full(n_test, trend[-1])
    last_cycle = seasonal[-period:]
    seasonal_ext = np.tile(last_cycle, n_test // period + 1)[:n_test]
    return trend_ext, seasonal_ext


# ── Variant dispatcher ───────────────────────────────────────────────────

VARIANTS = {
    'Baseline':       {'n_features': 14, 'alpha': 1.0},
    'One-Hot Time':   {'n_features': 63, 'alpha': 10.0},
    'Fourier-3':      {'n_features': 26, 'alpha': 1.0},
    'One-Hot+Fourier':{'n_features': 71, 'alpha': 10.0},
    'MA-3h Target':   {'n_features': 14, 'alpha': 1.0},
    'diff(48)':       {'n_features': 14, 'alpha': 1.0},
    'STL Residual':   {'n_features': 14, 'alpha': 1.0},
    'Hour×Weather':   {'n_features': 20, 'alpha': 1.0},
}


def _build_horizon_origin(train_y, n_train, n_test, min_history=48, max_h=336):
    """Build horizon and origin-summary arrays, shared across variants."""
    origin_last = np.zeros(n_train)
    origin_mean = np.zeros(n_train)
    origin_std = np.zeros(n_train)
    for t in range(min_history, n_train):
        recent = train_y[max(0, t - 47):t + 1]
        origin_last[t] = train_y[t]
        origin_mean[t] = np.mean(recent)
        origin_std[t] = np.std(recent) if len(recent) > 1 else 0

    X_parts, y_parts = [], []
    for h in range(1, min(max_h, n_test) + 1):
        origins = np.arange(min_history, n_train - h)
        if len(origins) == 0:
            continue
        targets = origins + h
        h_col = np.full((len(origins), 1), h / 336.0)
        h2_col = h_col ** 2
        of = np.column_stack([origin_last[origins], origin_mean[origins], origin_std[origins]])
        yield h, origins, targets, h_col, h2_col, of

    return


def _test_horizon_origin(train_y, n_test):
    """Build horizon and origin-summary for test rows."""
    recent = train_y[-48:]
    of_test = np.array([[train_y[-1], np.mean(recent), np.std(recent)]])
    of_test = np.tile(of_test, (n_test, 1))
    h_vals = np.arange(1, n_test + 1).reshape(-1, 1) / 336.0
    return h_vals, h_vals ** 2, of_test


def run_variant(name, train_ts, train_y, test_ts, test_y,
                train_exog=None, test_exog=None):
    """Run a single variant end-to-end. Returns (preds, elapsed, n_features)."""
    cfg = VARIANTS[name]
    alpha = cfg['alpha']
    n_features = cfg['n_features']
    t0 = time.time()
    n_train = len(train_y)
    n_test = len(test_ts)
    has_exog = train_exog is not None and test_exog is not None
    min_history = 48
    max_h = min(n_test, 336)

    # Determine effective y for training (preprocessing)
    eff_train_y = train_y.copy()
    train_trend = train_seasonal = None

    if name == 'MA-3h Target':
        eff_train_y = smooth_ma(train_y, window=6)
    elif name == 'diff(48)':
        eff_train_y, _ = diff_48(train_y)
    elif name == 'STL Residual':
        train_trend, train_seasonal, eff_train_y = stl_decompose(train_ts, train_y)

    # Build time features for train
    if name == 'One-Hot Time':
        time_feat_train = build_onehot_features(train_ts).values  # 55 cols
    elif name == 'Fourier-3':
        time_feat_train = build_fourier_features(train_ts, n_harmonics=3).values  # 18 cols
    elif name == 'One-Hot+Fourier':
        oh = build_onehot_features(train_ts).values
        fo = build_fourier_features(train_ts, n_harmonics=3).values
        time_feat_train = np.column_stack([oh, fo])  # 73 cols
    else:
        time_feat_train = build_cyclical_features(train_ts).values  # 6 cols

    # Build time features for test
    if name == 'One-Hot Time':
        time_feat_test = build_onehot_features(test_ts).values
    elif name == 'Fourier-3':
        time_feat_test = build_fourier_features(test_ts, n_harmonics=3).values
    elif name == 'One-Hot+Fourier':
        oh = build_onehot_features(test_ts).values
        fo = build_fourier_features(test_ts, n_harmonics=3).values
        time_feat_test = np.column_stack([oh, fo])
    else:
        time_feat_test = build_cyclical_features(test_ts).values

    # Build origin summaries
    origin_last = np.zeros(n_train)
    origin_mean = np.zeros(n_train)
    origin_std = np.zeros(n_train)
    for t in range(min_history, n_train):
        recent = eff_train_y[max(0, t - 47):t + 1]
        origin_last[t] = eff_train_y[t]
        origin_mean[t] = np.mean(recent)
        origin_std[t] = np.std(recent) if len(recent) > 1 else 0

    # Build training X, y
    X_parts, y_parts = [], []
    for h in range(1, max_h + 1):
        origins = np.arange(min_history, n_train - h)
        if len(origins) == 0:
            continue
        targets = origins + h
        cyc = time_feat_train[targets]
        h_col = np.full((len(origins), 1), h / 336.0)
        h2_col = h_col ** 2
        of = np.column_stack([origin_last[origins], origin_mean[origins], origin_std[origins]])
        x = np.column_stack([cyc, h_col, h2_col, of])

        if has_exog:
            x = np.column_stack([x, train_exog[targets]])

        # Hour×Weather interactions
        if name == 'Hour×Weather' and has_exog:
            base_cyc = build_cyclical_features(train_ts).values
            hour_sin = base_cyc[targets, 0:1]  # hour_sin
            hour_cos = base_cyc[targets, 1:2]  # hour_cos
            wx = train_exog[targets]
            interactions = np.column_stack([hour_sin * wx, hour_cos * wx])
            x = np.column_stack([x, interactions])

        X_parts.append(x)
        y_parts.append(eff_train_y[targets])

    X_train = np.vstack(X_parts)
    y_train = np.concatenate(y_parts)

    # Build test X
    recent = eff_train_y[-48:]
    of_test = np.array([[eff_train_y[-1], np.mean(recent), np.std(recent)]])
    of_test = np.tile(of_test, (n_test, 1))
    h_vals = np.arange(1, n_test + 1).reshape(-1, 1) / 336.0
    X_test = np.column_stack([time_feat_test, h_vals, h_vals ** 2, of_test])

    if has_exog:
        X_test = np.column_stack([X_test, test_exog])

    if name == 'Hour×Weather' and has_exog:
        base_cyc_test = build_cyclical_features(test_ts).values
        hour_sin_t = base_cyc_test[:, 0:1]
        hour_cos_t = base_cyc_test[:, 1:2]
        interactions_t = np.column_stack([hour_sin_t * test_exog, hour_cos_t * test_exog])
        X_test = np.column_stack([X_test, interactions_t])

    # Subsample if too large
    max_samples = 500_000
    if len(X_train) > max_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_train), max_samples, replace=False)
        X_train = X_train[idx]
        y_train = y_train[idx]

    # Train
    model = Ridge(alpha=alpha)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    # Post-process predictions
    if name == 'diff(48)':
        anchor = train_y[-48:]
        preds = inverse_diff_48(preds, anchor)
    elif name == 'STL Residual':
        trend_ext, seasonal_ext = stl_extrapolate(train_trend, train_seasonal, n_test)
        preds = preds + trend_ext + seasonal_ext

    preds = np.clip(preds, 0, 500)
    elapsed = time.time() - t0
    actual_n_features = X_train.shape[1]
    return preds, elapsed, actual_n_features


# ── Plotting ─────────────────────────────────────────────────────────────

def plot_comparison(results_df):
    """Grouped bar chart of MAE per variant, averaged across regions."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    avg = results_df.groupby('variant')['MAE'].mean().sort_values()

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.Set2(np.linspace(0, 1, len(avg)))
    bars = ax.bar(range(len(avg)), avg.values, color=colors, edgecolor='black', linewidth=0.5)

    ax.set_xticks(range(len(avg)))
    ax.set_xticklabels(avg.index, rotation=30, ha='right')
    ax.set_ylabel('MAE (gCO₂/kWh)')
    ax.set_title('Preprocessing Experiment: MAE by Variant (avg across regions)')
    ax.axhline(y=avg.get('Baseline', 33), color='red', linestyle='--', alpha=0.5, label='Baseline')

    for bar, val in zip(bars, avg.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f'{val:.2f}', ha='center', va='bottom', fontsize=9)

    ax.legend()
    plt.tight_layout()
    path = DOCS_DIR / 'benchmark_preprocessing_comparison.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")


def plot_predictions(results_df, test_dfs, all_preds):
    """Predictions vs actual for best region, top 4 variants."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    avg = results_df.groupby('variant')['MAE'].mean().sort_values()
    top_variants = avg.index[:4].tolist()

    # Pick best region (lowest baseline MAE)
    baseline_by_region = results_df[results_df['variant'] == 'Baseline'].set_index('region')['MAE']
    if len(baseline_by_region) == 0:
        return
    best_region = baseline_by_region.idxmin()

    test_df = test_dfs[best_region]
    test_ts = test_df['ts']
    test_y = test_df['actual'].values

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    axes = axes.flatten()

    for i, vname in enumerate(top_variants):
        ax = axes[i]
        preds = all_preds.get((best_region, vname))
        if preds is None:
            continue
        min_len = min(len(test_y), len(preds))
        ax.plot(test_ts.iloc[:min_len], test_y[:min_len], alpha=0.6, label='Actual', linewidth=0.8)
        ax.plot(test_ts.iloc[:min_len], preds[:min_len], alpha=0.8, label=vname, linewidth=0.8)
        mae = np.mean(np.abs(test_y[:min_len] - preds[:min_len]))
        ax.set_title(f'{vname} (MAE={mae:.2f}) — {best_region}')
        ax.legend(fontsize=8)
        ax.set_ylabel('gCO₂/kWh')

    plt.tight_layout()
    path = DOCS_DIR / 'benchmark_preprocessing_predictions.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  PREPROCESSING EXPERIMENT")
    print("  Can we beat Direct-Ridge MAE 32.99?")
    print("=" * 70)

    # Load data
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f"\nRegions: {regions}")
    print(f"Date range: {df['ts'].min()} -> {df['ts'].max()}")

    total_days = (df['ts'].max() - df['ts'].min()).days
    if total_days < 14:
        print("ERROR: Need at least 14 days of data for full backfill experiment")
        sys.exit(1)

    # Weather data
    date_min = df['ts'].min().strftime('%Y-%m-%d')
    date_max = df['ts'].max().strftime('%Y-%m-%d')
    print("\nFetching weather data...")
    weather_df = fetch_weather_data(regions, date_min, date_max)
    has_weather = len(weather_df) > 0
    if has_weather:
        print(f"Weather data: {len(weather_df)} points")
    else:
        print("WARNING: No weather data — running without exogenous features")

    # Train/test split (full backfill only)
    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = []
    all_preds = {}
    test_dfs = {}

    for region in regions:
        rdf = df[df['region'] == region].copy().reset_index(drop=True)
        test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

        if len(test) == 0:
            print(f"\n{region}: no test data, skipping")
            continue

        train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
        if len(train) < 48:
            print(f"\n{region}: insufficient training data ({len(train)} points), skipping")
            continue

        test_dfs[region] = test
        test_y = test['actual'].values
        train_days = (train['ts'].max() - train['ts'].min()).days

        print(f"\n{'='*60}")
        print(f"  {region}: train={len(train)} ({train_days}d), test={len(test)}")
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
        train_y_vals = train['actual'].values
        test_ts = test['ts'].reset_index(drop=True)

        for vname in VARIANTS:
            print(f"    {vname}...", end=' ', flush=True)
            try:
                preds, elapsed, actual_nf = run_variant(
                    vname, train_ts, train_y_vals, test_ts, test_y,
                    train_exog=train_exog, test_exog=test_exog,
                )
                min_len = min(len(preds), len(test_y))
                metrics = compute_metrics(test_y[:min_len], preds[:min_len],
                                          n_features=actual_nf)
                print(f"MAE={metrics['MAE']:.2f}  ({elapsed:.2f}s)")
                all_rows.append({
                    'region': region,
                    'variant': vname,
                    **metrics,
                    'time': elapsed,
                    'n_features': actual_nf,
                })
                all_preds[(region, vname)] = preds
            except Exception as e:
                print(f"FAILED: {e}")
                import traceback
                traceback.print_exc()

    if not all_rows:
        print("\nERROR: No results collected")
        sys.exit(1)

    results_df = pd.DataFrame(all_rows)

    # ── Results table ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RESULTS (averaged across regions)")
    print("=" * 70)

    avg = results_df.groupby('variant')[['MAE', 'RMSE', 'R2', 'n_features']].mean()
    avg = avg.sort_values('MAE')
    print(f"\n{'Variant':<20} {'MAE':>8} {'RMSE':>8} {'R²':>8} {'#Feat':>6}")
    print("-" * 54)
    for vname, row in avg.iterrows():
        print(f"{vname:<20} {row['MAE']:>8.2f} {row['RMSE']:>8.2f} {row['R2']:>8.4f} {int(row['n_features']):>6}")

    baseline_mae = avg.loc['Baseline', 'MAE'] if 'Baseline' in avg.index else 33.0
    print(f"\nBaseline MAE: {baseline_mae:.2f}")
    best_name = avg.index[0]
    best_mae = avg.iloc[0]['MAE']
    if best_mae < baseline_mae:
        print(f"BEST: {best_name} with MAE {best_mae:.2f} (Δ = {best_mae - baseline_mae:+.2f})")
    else:
        print(f"No variant beat the baseline.")

    # ── Plots ────────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    plot_comparison(results_df)
    plot_predictions(results_df, test_dfs, all_preds)

    # ── Append to comparison_report.md ───────────────────────────────────
    report_path = DOCS_DIR / 'comparison_report.md'
    section = "\n\n## Preprocessing Experiment\n\n"
    section += "Can smarter feature engineering or target preprocessing beat Direct-Ridge MAE 32.99?\n\n"
    section += "All variants use Ridge regression with full-backfill training, same train/test split.\n\n"
    section += f"| Variant | MAE | RMSE | R² | #Features |\n"
    section += f"|---------|-----|------|----|-----------|\n"
    for vname, row in avg.iterrows():
        delta = row['MAE'] - baseline_mae
        section += f"| {vname} | {row['MAE']:.2f} | {row['RMSE']:.2f} | {row['R2']:.4f} | {int(row['n_features'])} |\n"

    section += f"\nBaseline Direct-Ridge MAE: {baseline_mae:.2f}\n"
    if best_mae < baseline_mae:
        section += f"Best variant: **{best_name}** with MAE {best_mae:.2f} (Δ = {best_mae - baseline_mae:+.2f})\n"
    else:
        section += "No variant beat the baseline.\n"

    section += "\n![Preprocessing Comparison](benchmark_preprocessing_comparison.png)\n"
    section += "![Preprocessing Predictions](benchmark_preprocessing_predictions.png)\n"

    if report_path.exists():
        existing = report_path.read_text()
        # Remove existing section if re-running
        marker = "## Preprocessing Experiment"
        if marker in existing:
            existing = existing[:existing.index(marker)].rstrip()
        report_path.write_text(existing + section)
    else:
        report_path.write_text("# Comparison Report\n" + section)

    print(f"\nAppended results to {report_path}")
    print("\nDone!")


if __name__ == '__main__':
    main()
