"""
SARIMAX vs Ridge Regression comparison on carbon intensity data.

Tests both models on:
  1. 7-day training window (matching comparison_report.md setup)
  2. Full backfill (~90 days) training window

Evaluates on the last 30 days of data for both greenness and raw carbon intensity.
"""

import sqlite3
import time
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from sklearn.linear_model import Ridge
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings('ignore')

DB_PATH = 'carbon_intensity.db'


def carbon_intensity_to_greenness(intensity):
    intensity = np.clip(intensity, 0, 500)
    greenness = 100 - ((intensity - 50) / 3.5)
    return np.clip(greenness, 0, 100)


# ── 1. Load & deduplicate ────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("""
    SELECT r.name AS region, cr.timestamp_from AS ts, cr.actual
    FROM carbon_readings cr
    JOIN regions r ON cr.region_id = r.region_id
    WHERE cr.actual IS NOT NULL
""", conn)
conn.close()

df['ts'] = pd.to_datetime(df['ts'])
df = df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
df['greenness'] = carbon_intensity_to_greenness(df['actual'].values)

regions = sorted(df['region'].unique())
print(f"Regions: {regions}")
print(f"Date range: {df['ts'].min()} → {df['ts'].max()}")
print(f"Rows (deduplicated): {len(df)}")


# ── 2. Model definitions ─────────────────────────────────────────────────

def build_ridge_features(timestamps):
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


def train_predict_ridge(train_ts, train_y, test_ts, clip_min, clip_max):
    X_train = build_ridge_features(train_ts)
    model = Ridge(alpha=1.0)
    model.fit(X_train, train_y)
    X_test = build_ridge_features(test_ts)
    preds = np.clip(model.predict(X_test), clip_min, clip_max)
    return preds


def train_predict_sarimax(train_series, n_test, clip_min, clip_max):
    """Train SARIMAX and forecast n_test steps ahead.

    Uses order (1,0,1) x seasonal (1,0,1,48) for 30-min data (48 = daily cycle).
    For long training sets, subsample to last 14 days to keep runtime sane.
    """
    # Subsample if too long — SARIMAX is O(n^2) or worse
    max_train = 48 * 14  # 14 days of 30-min data = 672 points
    if len(train_series) > max_train:
        train_series = train_series.iloc[-max_train:]

    t0 = time.time()
    model = SARIMAX(
        train_series,
        order=(1, 0, 1),
        seasonal_order=(1, 0, 1, 48),
        trend='c',
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)
    preds = fit.forecast(steps=n_test)
    elapsed = time.time() - t0
    preds = np.clip(preds.values, clip_min, clip_max)
    return preds, elapsed


# ── 3. Run experiments ───────────────────────────────────────────────────

test_days = 30
split_date = df['ts'].max() - pd.Timedelta(days=test_days)
short_train_start = split_date - pd.Timedelta(days=7)   # 7-day window

experiments = [
    ('7-day train', short_train_start),
    ('Full backfill', None),  # None = use all data before split
]

all_results = {}

for region in regions:
    rdf = df[df['region'] == region].copy().reset_index(drop=True)
    test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

    if len(test) == 0:
        print(f"\n{region}: no test data, skipping")
        continue

    all_results[region] = {}

    for exp_name, train_start in experiments:
        if train_start is not None:
            train = rdf[(rdf['ts'] > train_start) & (rdf['ts'] <= split_date)].reset_index(drop=True)
        else:
            train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)

        train_days_actual = (train['ts'].max() - train['ts'].min()).days
        print(f"\n{region} [{exp_name}]: train={len(train)} pts ({train_days_actual}d), test={len(test)} pts")

        exp_results = {}

        for target, col, clip_min, clip_max in [
            ('greenness', 'greenness', 0, 100),
            ('carbon_intensity', 'actual', 0, 500),
        ]:
            y_test = test[col].values

            # Ridge (no trend)
            t0 = time.time()
            ridge_preds = train_predict_ridge(
                train['ts'], train[col].values, test['ts'], clip_min, clip_max
            )
            ridge_time = time.time() - t0
            ridge_mae = np.mean(np.abs(y_test - ridge_preds))
            ridge_rmse = np.sqrt(np.mean((y_test - ridge_preds) ** 2))

            # SARIMAX — needs a proper time-indexed series
            train_series = train.set_index('ts')[col].copy()
            # Ensure regular frequency (fill gaps with interpolation)
            freq = '30min'
            full_idx = pd.date_range(train_series.index.min(), train_series.index.max(), freq=freq)
            train_series = train_series.reindex(full_idx).interpolate(method='time')
            train_series = train_series.asfreq(freq)

            sarimax_preds, sarimax_time = train_predict_sarimax(
                train_series, len(test), clip_min, clip_max
            )
            sarimax_mae = np.mean(np.abs(y_test - sarimax_preds))
            sarimax_rmse = np.sqrt(np.mean((y_test - sarimax_preds) ** 2))

            print(f"  {target:20s}  Ridge: MAE={ridge_mae:6.2f} RMSE={ridge_rmse:6.2f} ({ridge_time:.2f}s)"
                  f"  |  SARIMAX: MAE={sarimax_mae:6.2f} RMSE={sarimax_rmse:6.2f} ({sarimax_time:.2f}s)")

            exp_results[target] = {
                'ridge_preds': ridge_preds,
                'ridge_mae': ridge_mae,
                'ridge_rmse': ridge_rmse,
                'ridge_time': ridge_time,
                'sarimax_preds': sarimax_preds,
                'sarimax_mae': sarimax_mae,
                'sarimax_rmse': sarimax_rmse,
                'sarimax_time': sarimax_time,
                'y_test': y_test,
                'test_ts': test['ts'].values,
                'train': train,
                'test': test,
            }

        all_results[region][exp_name] = exp_results


# ── 4. Summary table ─────────────────────────────────────────────────────

print("\n" + "=" * 100)
print("SUMMARY: MAE comparison (lower is better)")
print("=" * 100)

header = f"{'Region':<20} {'Experiment':<16} {'Target':<20} {'Ridge MAE':>10} {'SARIMAX MAE':>12} {'Winner':>10} {'Δ MAE':>8}"
print(header)
print("-" * len(header))

for region in regions:
    if region not in all_results:
        continue
    for exp_name in ['7-day train', 'Full backfill']:
        if exp_name not in all_results[region]:
            continue
        for target in ['greenness', 'carbon_intensity']:
            r = all_results[region][exp_name][target]
            winner = 'SARIMAX' if r['sarimax_mae'] < r['ridge_mae'] else 'Ridge'
            delta = r['ridge_mae'] - r['sarimax_mae']
            print(f"  {region:<18} {exp_name:<16} {target:<20} {r['ridge_mae']:>10.2f} {r['sarimax_mae']:>12.2f} {winner:>10} {delta:>+8.2f}")


# ── 5. Graph: SARIMAX vs Ridge for carbon intensity (full backfill) ──────

fig, axes = plt.subplots(len(regions), 1, figsize=(16, 4.5 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = [axes]

for ax, region in zip(axes, regions):
    if region not in all_results:
        continue

    r = all_results[region]['Full backfill']['carbon_intensity']
    train = r['train']
    test = r['test']

    # Training data (faded)
    ax.plot(train['ts'], train['actual'],
            linewidth=0.6, color='#90CAF9', alpha=0.4, label='Train (actual)')
    # Split line
    ax.axvline(split_date, color='gray', linestyle='--', linewidth=1, label='Split')
    # Test actual
    ax.plot(test['ts'], test['actual'],
            linewidth=1.2, color='#2196F3', label='Test (actual)')
    # Ridge predictions
    ax.plot(test['ts'], r['ridge_preds'],
            linewidth=1.2, color='#F44336', linestyle='--', label=f"Ridge MAE={r['ridge_mae']:.1f}")
    # SARIMAX predictions
    ax.plot(test['ts'], r['sarimax_preds'],
            linewidth=1.2, color='#4CAF50', linestyle='-.', label=f"SARIMAX MAE={r['sarimax_mae']:.1f}")

    ax.set_ylabel('gCO₂/kWh')
    ax.set_title(f"{region}")
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
fig.suptitle('SARIMAX vs Ridge: Carbon Intensity — 30-Day Forecast (Full Backfill Training)', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('sarimax_vs_ridge_carbon_intensity.png', dpi=150, bbox_inches='tight')
print("\nSaved: sarimax_vs_ridge_carbon_intensity.png")
plt.close(fig)


# ── 6. Graph: 7-day vs Full backfill comparison (carbon intensity) ──────

fig, axes = plt.subplots(len(regions), 2, figsize=(20, 4 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = axes.reshape(1, -1)

for row, region in enumerate(regions):
    if region not in all_results:
        continue

    for col, exp_name in enumerate(['7-day train', 'Full backfill']):
        ax = axes[row, col]
        r = all_results[region][exp_name]['carbon_intensity']
        test = r['test']

        ax.plot(test['ts'], test['actual'],
                linewidth=1.2, color='#2196F3', label='Actual')
        ax.plot(test['ts'], r['ridge_preds'],
                linewidth=1.1, color='#F44336', linestyle='--',
                label=f"Ridge MAE={r['ridge_mae']:.1f}")
        ax.plot(test['ts'], r['sarimax_preds'],
                linewidth=1.1, color='#4CAF50', linestyle='-.',
                label=f"SARIMAX MAE={r['sarimax_mae']:.1f}")

        ax.set_ylabel('gCO₂/kWh')
        ax.set_title(f"{region} — {exp_name}")
        ax.legend(loc='upper right', fontsize=7)
        ax.grid(True, alpha=0.3)

for ax in axes[-1]:
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))

fig.suptitle('Training Window Comparison: 7-day vs Full Backfill — 30-Day Forecast (Carbon Intensity gCO₂/kWh)', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('sarimax_training_window_ci_comparison.png', dpi=150, bbox_inches='tight')
print("Saved: sarimax_training_window_ci_comparison.png")
plt.close(fig)
