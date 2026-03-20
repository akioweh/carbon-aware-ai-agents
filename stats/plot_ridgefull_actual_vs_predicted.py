import sys
sys.path.insert(0, '/Users/alirazajafree/carbon-aware-ai-agents/stats')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from predictor_ridge_v2 import (
    load_carbon_from_db, build_direct_features, train_ridge, predict_ridge,
    get_weather, REGIONS, _align_weather, WX_FEATURES
)

all_data = load_carbon_from_db()

fig, axes = plt.subplots(5, 1, figsize=(14, 16), sharex=False)
fig.suptitle('RidgeFull: Actual vs Predicted (7-day forecast)', fontsize=16, fontweight='bold')

region_order = [13, 14, 5, 3, 4]  # London, SE, SY, NW, NE

all_maes = []

for i, rid in enumerate(region_order):
    dc_name, region_name, lat, lon = REGIONS[rid]
    rdf = all_data[all_data['region_id'] == rid].sort_values('timestamp').reset_index(drop=True)

    t_max = rdf['timestamp'].max()
    t_test = t_max - pd.Timedelta(days=7)
    t_val = t_max - pd.Timedelta(days=14)

    # Same split as benchmark
    train = rdf[rdf['timestamp'] <= t_val].reset_index(drop=True)
    test = rdf[rdf['timestamp'] > t_test].reset_index(drop=True)

    train_ts = train['timestamp'].values
    train_y = train['carbon_intensity'].values.astype(float)
    test_ts = test['timestamp'].values
    test_y = test['carbon_intensity'].values.astype(float)

    # Weather
    s_date = train['timestamp'].iloc[0].strftime('%Y-%m-%d')
    e_date = rdf['timestamp'].iloc[-1].strftime('%Y-%m-%d')
    wx = get_weather(lat, lon, s_date, e_date, cache_key=f'bench_{rid}')

    train_wx = test_wx = None
    if not wx.empty:
        full_ts = rdf['timestamp'].values
        full_wx = _align_weather(wx, full_ts)
        if full_wx is not None:
            train_wx = full_wx[:len(train)]
            # Skip val portion, take test portion
            val_len = len(rdf[(rdf['timestamp'] > t_val) & (rdf['timestamp'] <= t_test)])
            test_wx = full_wx[len(train) + val_len:]

    # Build features with subsample=3
    X_train, y_train, X_test = build_direct_features(
        train_ts, train_y, test_ts,
        train_wx=train_wx, test_wx=test_wx,
        subsample=3,
    )

    ridge, scaler = train_ridge(X_train, y_train)
    preds = predict_ridge(ridge, scaler, X_test)

    mae = np.mean(np.abs(test_y - preds))
    all_maes.append(mae)

    ax = axes[i]
    ax.plot(test['timestamp'], test_y, color='#2196F3', linewidth=1.2, label='Actual')
    ax.plot(test['timestamp'], preds, color='#FF9800', linewidth=1.2, linestyle='--', label='Predicted')
    ax.set_title(f'{region_name}', fontsize=12)
    ax.set_ylabel('gCO₂/kWh')
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    print(f'{region_name}: MAE = {mae:.2f}')

axes[-1].set_xlabel('Date')
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig('/Users/alirazajafree/carbon-aware-ai-agents/docs/stats_experiments/analysis/ridgefull_actual_vs_predicted.png', dpi=150)

avg_mae = np.mean(all_maes)
print(f'\nAverage MAE: {avg_mae:.2f}')
print('Plot saved.')
