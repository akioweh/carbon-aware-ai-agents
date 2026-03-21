#!/usr/bin/env python3
"""
New model benchmark (separate process).

Runs Chronos (zero-shot foundation model), N-BEATS, and N-HiTS on the same
data splits as benchmark.py. Results are saved to new_model_results.json for
benchmark.py to merge into the final report and graphs.

Run this BEFORE benchmark.py:

    python benchmark_new_models.py
    python benchmark.py           # auto-merges new_model_results.json

Separate process keeps heavyweight dependencies (chronos-forecasting,
neuralforecast) isolated and allows independent reruns.
"""

import json
import logging
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
# Suppress PyTorch Lightning verbosity from neuralforecast
logging.getLogger('pytorch_lightning').setLevel(logging.ERROR)
logging.getLogger('lightning.pytorch').setLevel(logging.ERROR)
logging.getLogger('lightning.fabric').setLevel(logging.ERROR)
os.environ.setdefault('PYTORCH_LIGHTNING_LOG_LEVEL', '0')

from benchmark import (
    DB_PATH,
    TEST_DAYS,
    compute_metrics,
    load_data,
)

NEW_RESULTS_PATH = Path(__file__).parent / 'new_model_results.json'

NEW_MODELS = ['Chronos-Tiny', 'N-BEATS', 'N-HiTS']

NEW_N_FEATURES = {
    'Chronos-Tiny': 0,
    'N-BEATS': 0,
    'N-HiTS': 0,
}


def _strip_tz(ts):
    """Remove timezone info from timestamp series for library compatibility."""
    if hasattr(ts, 'dt') and ts.dt.tz is not None:
        return pd.to_datetime(ts.to_numpy().astype('datetime64[ns]'))
    return ts


def _fill_gaps(train_ts, train_y):
    """Ensure regular 30-min frequency by filling gaps."""
    series = pd.Series(train_y, index=train_ts)
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time')
    return series.index, series.values


def train_predict_chronos(train_ts, train_y, test_ts, **kw):
    """Amazon Chronos-T5-Tiny: zero-shot foundation model forecast.

    Pre-trained on millions of time series. No training on local data —
    just tokenize the history and generate predictions autoregressively.
    """
    import torch
    from chronos import ChronosPipeline

    t0 = time.time()
    n_test = len(test_ts)

    print('[downloading/loading model]', end=' ', flush=True)
    pipeline = ChronosPipeline.from_pretrained(
        'amazon/chronos-t5-tiny',
        device_map='cpu',
        torch_dtype=torch.float32,
    )

    # Fill gaps for cleaner context
    ts_clean, y_clean = _fill_gaps(train_ts, train_y)

    context = torch.tensor(y_clean, dtype=torch.float32).unsqueeze(0)
    forecast = pipeline.predict(
        context,
        prediction_length=n_test,
        num_samples=20,
    )
    # forecast shape: (1, num_samples, prediction_length)
    preds = torch.median(forecast, dim=1).values.squeeze().numpy()

    return np.clip(preds, 0, 500), time.time() - t0


def train_predict_nbeats(train_ts, train_y, test_ts, **kw):
    """N-BEATS: Neural Basis Expansion Analysis for Time Series.

    Direct multi-horizon forecasting — predicts all h steps at once,
    avoiding recursive error compounding. Uses basis expansion
    (trend + seasonality blocks) to decompose the forecast.
    """
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATS

    t0 = time.time()
    n_test = len(test_ts)

    # Fill gaps and strip timezone
    ts_clean, y_clean = _fill_gaps(train_ts, train_y)
    ds = _strip_tz(pd.Series(ts_clean))

    input_size = min(96, len(y_clean) // 3)
    min_needed = input_size + n_test
    if len(y_clean) < min_needed:
        raise ValueError(
            f'Insufficient training data for N-BEATS: {len(y_clean)} < '
            f'{min_needed} (input_size={input_size} + horizon={n_test})'
        )

    train_df = pd.DataFrame(
        {
            'unique_id': ['series'] * len(y_clean),
            'ds': ds.values,
            'y': y_clean.astype(float),
        }
    )

    model = NBEATS(
        h=n_test,
        input_size=input_size,
        max_steps=300,
        learning_rate=1e-3,
        batch_size=32,
        scaler_type='standard',
        random_seed=42,
        enable_progress_bar=False,
    )

    nf = NeuralForecast(models=[model], freq='30min')
    nf.fit(df=train_df)
    preds_df = nf.predict()
    preds = preds_df['NBEATS'].values

    return np.clip(preds, 0, 500), time.time() - t0


def train_predict_nhits(train_ts, train_y, test_ts, **kw):
    """N-HiTS: Neural Hierarchical Interpolation for Time Series.

    Improved N-BEATS with multi-rate signal sampling — uses hierarchical
    interpolation to handle different temporal scales efficiently.
    Direct multi-horizon output (no recursive forecasting).
    """
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NHITS

    t0 = time.time()
    n_test = len(test_ts)

    # Fill gaps and strip timezone
    ts_clean, y_clean = _fill_gaps(train_ts, train_y)
    ds = _strip_tz(pd.Series(ts_clean))

    input_size = min(96, len(y_clean) // 3)
    min_needed = input_size + n_test
    if len(y_clean) < min_needed:
        raise ValueError(
            f'Insufficient training data for N-HiTS: {len(y_clean)} < '
            f'{min_needed} (input_size={input_size} + horizon={n_test})'
        )

    train_df = pd.DataFrame(
        {
            'unique_id': ['series'] * len(y_clean),
            'ds': ds.values,
            'y': y_clean.astype(float),
        }
    )

    model = NHITS(
        h=n_test,
        input_size=input_size,
        max_steps=300,
        learning_rate=1e-3,
        batch_size=32,
        scaler_type='standard',
        random_seed=42,
        enable_progress_bar=False,
    )

    nf = NeuralForecast(models=[model], freq='30min')
    nf.fit(df=train_df)
    preds_df = nf.predict()
    preds = preds_df['NHITS'].values

    return np.clip(preds, 0, 500), time.time() - t0


MODEL_FUNCS = {
    'Chronos-Tiny': train_predict_chronos,
    'N-BEATS': train_predict_nbeats,
    'N-HiTS': train_predict_nhits,
}


def main():
    df = load_data(DB_PATH)
    regions = sorted(df['region'].unique())
    print(f'Regions: {regions}')
    print(f'Date range: {df["ts"].min()} -> {df["ts"].max()}')

    total_days = (df['ts'].max() - df['ts'].min()).days

    split_date = df['ts'].max() - pd.Timedelta(days=TEST_DAYS)
    short_train_start = split_date - pd.Timedelta(days=7)

    windows = [('7-day', short_train_start)]
    if total_days > 14:
        windows.append(('Full backfill', None))

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

            train_ts = train['ts'].reset_index(drop=True)
            train_y = train['actual'].values
            test_ts = test['ts'].reset_index(drop=True)

            results = {}
            for model_name in NEW_MODELS:
                print(f'    {model_name}...', end=' ', flush=True)
                func = MODEL_FUNCS[model_name]
                try:
                    preds, elapsed = func(
                        train_ts=train_ts,
                        train_y=train_y,
                        test_ts=test_ts,
                        test_y=test_y,
                    )
                    if len(preds) != len(test_y):
                        min_len = min(len(preds), len(test_y))
                        preds = preds[:min_len]
                        test_y_eval = test_y[:min_len]
                    else:
                        test_y_eval = test_y

                    metrics = compute_metrics(test_y_eval, preds, n_features=NEW_N_FEATURES[model_name])
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
    NEW_RESULTS_PATH.write_text(json.dumps(all_results, indent=2))
    print(f'\nResults saved to {NEW_RESULTS_PATH}')

    # Summary
    print('\n' + '=' * 70)
    print('NEW MODEL BENCHMARK COMPLETE')
    print('=' * 70)
    for window_name, _ in windows:
        print(f'\n--- {window_name} ---')
        active_regions = [r for r in regions if r in all_results and window_name in all_results[r]]
        model_maes = {}
        for model_name in NEW_MODELS:
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

    print(f'\nNow run: python benchmark.py  (will auto-merge new model results)')


if __name__ == '__main__':
    main()
