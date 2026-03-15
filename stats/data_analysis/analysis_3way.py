"""
3-way comparison: Ridge vs SARIMAX vs Prophet on carbon intensity (gCO2/kWh).

Tests on 7-day and full backfill training windows.
"""

import sqlite3
import time
import warnings
import logging

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from sklearn.linear_model import Ridge
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet

warnings.filterwarnings('ignore')
logging.getLogger('prophet').setLevel(logging.WARNING)
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

DB_PATH = 'carbon_intensity.db'

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

regions = sorted(df['region'].unique())
print(f"Regions: {regions}")
print(f"Date range: {df['ts'].min()} → {df['ts'].max()}")
print(f"Rows: {len(df)}")


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


def run_ridge(train_ts, train_y, test_ts):
    t0 = time.time()
    X_train = build_ridge_features(train_ts)
    model = Ridge(alpha=1.0)
    model.fit(X_train, train_y)
    X_test = build_ridge_features(test_ts)
    preds = np.clip(model.predict(X_test), 0, 500)
    return preds, time.time() - t0


def run_sarimax(train_series, n_test):
    max_train = 48 * 14  # cap at 14 days
    if len(train_series) > max_train:
        train_series = train_series.iloc[-max_train:]

    t0 = time.time()
    model = SARIMAX(
        train_series,
        order=(1, 0, 1),
        seasonal_order=(1, 0, 1, 48),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)
    preds = fit.forecast(steps=n_test)
    elapsed = time.time() - t0
    return np.clip(preds.values, 0, 500), elapsed


def run_prophet(train_ts, train_y, test_ts):
    t0 = time.time()
    prophet_df = pd.DataFrame({
        'ds': pd.to_datetime(train_ts).dt.tz_localize(None),
        'y': train_y,
    })
    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,
    )
    model.fit(prophet_df)

    future_df = pd.DataFrame({
        'ds': pd.to_datetime(test_ts).dt.tz_localize(None),
    })
    forecast = model.predict(future_df)
    preds = np.clip(forecast['yhat'].values, 0, 500)
    elapsed = time.time() - t0
    return preds, elapsed


# ── 3. Run experiments ───────────────────────────────────────────────────

test_days = 7
split_date = df['ts'].max() - pd.Timedelta(days=test_days)
short_train_start = split_date - pd.Timedelta(days=7)

experiments = [
    ('7-day train', short_train_start),
    ('Full backfill', None),
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

        train_days = (train['ts'].max() - train['ts'].min()).days
        print(f"\n{region} [{exp_name}]: train={len(train)} ({train_days}d), test={len(test)}")

        y_test = test['actual'].values

        # Ridge
        ridge_preds, ridge_time = run_ridge(train['ts'], train['actual'].values, test['ts'])
        ridge_mae = np.mean(np.abs(y_test - ridge_preds))
        ridge_rmse = np.sqrt(np.mean((y_test - ridge_preds) ** 2))

        # SARIMAX
        train_series = train.set_index('ts')['actual'].copy()
        full_idx = pd.date_range(train_series.index.min(), train_series.index.max(), freq='30min')
        train_series = train_series.reindex(full_idx).interpolate(method='time').asfreq('30min')
        sarimax_preds, sarimax_time = run_sarimax(train_series, len(test))
        sarimax_mae = np.mean(np.abs(y_test - sarimax_preds))
        sarimax_rmse = np.sqrt(np.mean((y_test - sarimax_preds) ** 2))

        # Prophet
        prophet_preds, prophet_time = run_prophet(train['ts'], train['actual'].values, test['ts'])
        prophet_mae = np.mean(np.abs(y_test - prophet_preds))
        prophet_rmse = np.sqrt(np.mean((y_test - prophet_preds) ** 2))

        print(f"  Ridge:   MAE={ridge_mae:6.2f}  RMSE={ridge_rmse:6.2f}  ({ridge_time:.2f}s)")
        print(f"  SARIMAX: MAE={sarimax_mae:6.2f}  RMSE={sarimax_rmse:6.2f}  ({sarimax_time:.2f}s)")
        print(f"  Prophet: MAE={prophet_mae:6.2f}  RMSE={prophet_rmse:6.2f}  ({prophet_time:.2f}s)")

        all_results[region][exp_name] = {
            'train': train, 'test': test, 'y_test': y_test,
            'ridge_preds': ridge_preds, 'ridge_mae': ridge_mae, 'ridge_rmse': ridge_rmse, 'ridge_time': ridge_time,
            'sarimax_preds': sarimax_preds, 'sarimax_mae': sarimax_mae, 'sarimax_rmse': sarimax_rmse, 'sarimax_time': sarimax_time,
            'prophet_preds': prophet_preds, 'prophet_mae': prophet_mae, 'prophet_rmse': prophet_rmse, 'prophet_time': prophet_time,
        }


# ── 4. Summary table ─────────────────────────────────────────────────────

print("\n" + "=" * 110)
print("CARBON INTENSITY (gCO₂/kWh) — MAE comparison")
print("=" * 110)
header = f"{'Region':<20} {'Window':<14} {'Ridge':>10} {'SARIMAX':>10} {'Prophet':>10} {'Winner':>10} {'Time(R/S/P)':>16}"
print(header)
print("-" * 110)

for region in regions:
    if region not in all_results:
        continue
    for exp_name in ['7-day train', 'Full backfill']:
        r = all_results[region][exp_name]
        maes = {'Ridge': r['ridge_mae'], 'SARIMAX': r['sarimax_mae'], 'Prophet': r['prophet_mae']}
        winner = min(maes, key=maes.get)
        times = f"{r['ridge_time']:.1f}/{r['sarimax_time']:.1f}/{r['prophet_time']:.1f}"
        print(f"  {region:<18} {exp_name:<14} {r['ridge_mae']:>10.2f} {r['sarimax_mae']:>10.2f} {r['prophet_mae']:>10.2f} {winner:>10} {times:>16}s")


# ── 5. Graph: 3-way comparison, full backfill ────────────────────────────

fig, axes = plt.subplots(len(regions), 1, figsize=(18, 4.5 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = [axes]

for ax, region in zip(axes, regions):
    if region not in all_results:
        continue

    r = all_results[region]['Full backfill']
    train = r['train']
    test = r['test']

    ax.plot(train['ts'], train['actual'],
            linewidth=0.5, color='#90CAF9', alpha=0.4, label='Train')
    ax.axvline(split_date, color='gray', linestyle='--', linewidth=1, label='Split')
    ax.plot(test['ts'], test['actual'],
            linewidth=1.2, color='#2196F3', label='Actual')
    ax.plot(test['ts'], r['ridge_preds'],
            linewidth=1.1, color='#F44336', linestyle='--',
            label=f"Ridge MAE={r['ridge_mae']:.1f}")
    ax.plot(test['ts'], r['sarimax_preds'],
            linewidth=1.1, color='#4CAF50', linestyle='-.',
            label=f"SARIMAX MAE={r['sarimax_mae']:.1f}")
    ax.plot(test['ts'], r['prophet_preds'],
            linewidth=1.1, color='#FF9800', linestyle=':',
            label=f"Prophet MAE={r['prophet_mae']:.1f}")

    ax.set_ylabel('gCO₂/kWh')
    ax.set_title(region)
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)

axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
fig.suptitle('Ridge vs SARIMAX vs Prophet: Carbon Intensity (Full Backfill)', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('3way_carbon_intensity_fullbackfill.png', dpi=150, bbox_inches='tight')
print("\nSaved: 3way_carbon_intensity_fullbackfill.png")
plt.close(fig)


# ── 6. Graph: 7-day vs Full backfill side by side ───────────────────────

fig, axes = plt.subplots(len(regions), 2, figsize=(22, 4 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = axes.reshape(1, -1)

for row, region in enumerate(regions):
    if region not in all_results:
        continue

    for col, exp_name in enumerate(['7-day train', 'Full backfill']):
        ax = axes[row, col]
        r = all_results[region][exp_name]
        test = r['test']

        ax.plot(test['ts'], test['actual'],
                linewidth=1.2, color='#2196F3', label='Actual')
        ax.plot(test['ts'], r['ridge_preds'],
                linewidth=1.0, color='#F44336', linestyle='--',
                label=f"Ridge {r['ridge_mae']:.1f}")
        ax.plot(test['ts'], r['sarimax_preds'],
                linewidth=1.0, color='#4CAF50', linestyle='-.',
                label=f"SARIMAX {r['sarimax_mae']:.1f}")
        ax.plot(test['ts'], r['prophet_preds'],
                linewidth=1.0, color='#FF9800', linestyle=':',
                label=f"Prophet {r['prophet_mae']:.1f}")

        ax.set_ylabel('gCO₂/kWh')
        ax.set_title(f"{region} — {exp_name}")
        ax.legend(loc='upper right', fontsize=7)
        ax.grid(True, alpha=0.3)

for ax in axes[-1]:
    ax.xaxis.set_major_formatter(DateFormatter('%b %d'))

fig.suptitle('3-Way Comparison: Carbon Intensity — 7-day vs Full Backfill', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('3way_carbon_intensity_comparison.png', dpi=150, bbox_inches='tight')
print("Saved: 3way_carbon_intensity_comparison.png")
plt.close(fig)
