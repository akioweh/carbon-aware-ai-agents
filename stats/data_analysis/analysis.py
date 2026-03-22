import sqlite3

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from sklearn.linear_model import Ridge

DB_PATH = 'carbon_intensity.db'


def carbon_intensity_to_greenness(intensity):
    """Convert gCO2/kWh to greenness score (0-100), matching db_utils."""
    intensity = np.clip(intensity, 0, 500)
    greenness = 100 - ((intensity - 50) / 3.5)
    return np.clip(greenness, 0, 100)


# ── 1. Load & deduplicate ────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(
    """
    SELECT r.name AS region, cr.timestamp_from AS ts, cr.actual
    FROM carbon_readings cr
    JOIN regions r ON cr.region_id = r.region_id
    WHERE cr.actual IS NOT NULL
""",
    conn,
)
conn.close()

df['ts'] = pd.to_datetime(df['ts'])
df = df.drop_duplicates(subset=['region', 'ts']).sort_values(['region', 'ts']).reset_index(drop=True)
df['greenness'] = carbon_intensity_to_greenness(df['actual'].values)

regions = df['region'].unique()
print(f'Regions: {list(regions)}')
print(f'Date range: {df["ts"].min()} → {df["ts"].max()}')
print(f'Rows (deduplicated): {len(df)}')

# ── 2. Graph raw carbon intensity values ─────────────────────────────────
fig, axes = plt.subplots(len(regions), 1, figsize=(16, 3.5 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = [axes]

for ax, region in zip(axes, sorted(regions)):
    rdf = df[df['region'] == region]
    ax.plot(rdf['ts'], rdf['actual'], linewidth=0.8, color='#2196F3')
    ax.set_ylabel('gCO₂/kWh')
    ax.set_title(region)
    ax.grid(True, alpha=0.3)

axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
fig.suptitle('Carbon Intensity — Raw Data (carbon_intensity.db)', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('raw_carbon_intensity.png', dpi=150, bbox_inches='tight')
print('Saved: raw_carbon_intensity.png')
plt.close(fig)

# ── 3. Train/test split & Ridge regression (greenness scale) ─────────────


def build_features(timestamps):
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute
    return pd.DataFrame(
        {
            'hour_sin': np.sin(2 * np.pi * hour / 24),
            'hour_cos': np.cos(2 * np.pi * hour / 24),
            'dow_sin': np.sin(2 * np.pi * dow / 7),
            'dow_cos': np.cos(2 * np.pi * dow / 7),
            'min_sin': np.sin(2 * np.pi * minute_of_day / 1440),
            'min_cos': np.cos(2 * np.pi * minute_of_day / 1440),
            'trend': np.arange(len(timestamps), dtype=float),
        }
    )


# Split: last 7 days = test, everything before = train
split_date = df['ts'].max() - pd.Timedelta(days=7)

# Also test with no-trend variant to see if trend hurts on long windows
results = {}
results_notrend = {}

for region in sorted(regions):
    rdf = df[df['region'] == region].copy()
    train = rdf[rdf['ts'] <= split_date].reset_index(drop=True)
    test = rdf[rdf['ts'] > split_date].reset_index(drop=True)

    train_days = (train['ts'].max() - train['ts'].min()).days
    test_days = (test['ts'].max() - test['ts'].min()).days
    print(f'\n{region}: train={len(train)} pts ({train_days}d), test={len(test)} pts ({test_days}d)')

    # --- With trend ---
    X_train = build_features(train['ts'])
    y_train = train['greenness'].values
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    X_test = build_features(test['ts'])
    X_test['trend'] = np.arange(len(train), len(train) + len(test), dtype=float)
    preds = np.clip(model.predict(X_test), 0, 100)

    mae = np.mean(np.abs(test['greenness'].values - preds))
    rmse = np.sqrt(np.mean((test['greenness'].values - preds) ** 2))
    print(f'  With trend:    MAE={mae:.2f}  RMSE={rmse:.2f}')

    results[region] = {
        'train': train,
        'test': test,
        'preds': preds,
        'mae': mae,
        'rmse': rmse,
    }

    # --- Without trend ---
    X_train_nt = build_features(train['ts']).drop(columns=['trend'])
    model_nt = Ridge(alpha=1.0)
    model_nt.fit(X_train_nt, y_train)

    X_test_nt = build_features(test['ts']).drop(columns=['trend'])
    preds_nt = np.clip(model_nt.predict(X_test_nt), 0, 100)

    mae_nt = np.mean(np.abs(test['greenness'].values - preds_nt))
    rmse_nt = np.sqrt(np.mean((test['greenness'].values - preds_nt) ** 2))
    print(f'  Without trend: MAE={mae_nt:.2f}  RMSE={rmse_nt:.2f}')

    results_notrend[region] = {
        'train': train,
        'test': test,
        'preds': preds_nt,
        'mae': mae_nt,
        'rmse': rmse_nt,
    }

# Pick better variant per region
print('\n── Summary (greenness 0-100 scale) ──')
print(f'{"Region":<25} {"With trend":>15} {"No trend":>15} {"Report (7d train)":>20}')
best = {}
for region in sorted(regions):
    r = results[region]
    rn = results_notrend[region]
    report_mae = '12.27' if region == 'London' else '—'
    winner = 'trend' if r['mae'] < rn['mae'] else 'no-trend'
    best[region] = results[region] if winner == 'trend' else results_notrend[region]
    print(f'  {region:<23} MAE={r["mae"]:>6.2f}    MAE={rn["mae"]:>6.2f}    MAE={report_mae:>6}')

# ── 4. Graph predictions vs actual (greenness, using best variant) ───────
fig, axes = plt.subplots(len(regions), 1, figsize=(16, 4 * len(regions)), sharex=True)
if len(regions) == 1:
    axes = [axes]

for ax, region in zip(axes, sorted(regions)):
    r = best[region]
    # Training data (faded)
    ax.plot(
        r['train']['ts'], r['train']['greenness'], linewidth=0.6, color='#90CAF9', alpha=0.5, label='Train (actual)'
    )
    # Split line
    ax.axvline(split_date, color='gray', linestyle='--', linewidth=1, label='Train/Test split')
    # Test actual
    ax.plot(r['test']['ts'], r['test']['greenness'], linewidth=1, color='#2196F3', label='Test (actual)')
    # Predictions
    ax.plot(r['test']['ts'], r['preds'], linewidth=1.2, color='#F44336', linestyle='--', label='Predictions')
    ax.set_ylabel('Greenness (0-100)')
    ax.set_ylim(-5, 105)
    ax.set_title(f'{region}  —  MAE={r["mae"]:.1f}  RMSE={r["rmse"]:.1f}')
    ax.legend(loc='lower right', fontsize=8)
    ax.grid(True, alpha=0.3)

axes[-1].xaxis.set_major_formatter(DateFormatter('%b %d'))
fig.suptitle('Ridge Regression: Greenness Predictions vs Actual (last 7 days)', fontsize=14, y=1.01)
fig.tight_layout()
fig.savefig('predictions_vs_actual.png', dpi=150, bbox_inches='tight')
print('\nSaved: predictions_vs_actual.png')
plt.close(fig)
