"""SARIMAX-based greenness predictor.

Predicts carbon intensity with SARIMAX(1,0,1)(1,0,1,48) and converts
the forecast to greenness (0-100). Falls back to predicting greenness
directly if carbon_intensity data is unavailable.
"""

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from predictor_linreg import get_next_week_load  # load stays on Ridge

warnings.filterwarnings('ignore', module='statsmodels')

# 48 half-hour slots per day; cap training to last 14 days
MAX_TRAIN_POINTS = 48 * 14  # 672


def get_next_week_greenness(historical_greenness_df):
    """Predict next-week greenness using SARIMAX on carbon intensity.

    Args:
        historical_greenness_df: DataFrame with columns
            'timestamp', 'greenness', and optionally 'carbon_intensity'.

    Returns:
        DataFrame with columns 'ds' (datetime) and 'yhat' (greenness 0-100).
    """
    df = historical_greenness_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    has_ci = (
        'carbon_intensity' in df.columns
        and df['carbon_intensity'].notna().any()
    )

    if has_ci:
        value_col = 'carbon_intensity'
        clip_min, clip_max = 0, 500
    else:
        value_col = 'greenness'
        clip_min, clip_max = 0, 100

    # Build a regular 30-min time-indexed series
    series = df.set_index('timestamp')[value_col].copy()
    series = series[series.notna()]
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time').asfreq('30min')

    # Cap training length for performance
    if len(series) > MAX_TRAIN_POINTS:
        series = series.iloc[-MAX_TRAIN_POINTS:]

    # Fit SARIMAX — trend='c' includes an intercept so forecasts revert
    # to the data mean instead of zero.
    model = SARIMAX(
        series,
        order=(1, 0, 1),
        seasonal_order=(1, 0, 1, 48),
        trend='c',
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)

    # SARIMAX was trained on 30-min data. Forecast 337 steps so that
    # upsampling to 5-min covers a full 2016-point (7-day) window.
    n_forecast = 337
    raw_forecast = fit.forecast(steps=n_forecast)
    raw_forecast = np.clip(raw_forecast.values, clip_min, clip_max)

    last_ts = series.index[-1]
    forecast_30min = pd.date_range(
        start=last_ts + pd.Timedelta(minutes=30),
        periods=n_forecast,
        freq='30min',
    )

    # Build 30-min forecast series, then upsample to 5-min via interpolation
    fc_series = pd.Series(raw_forecast, index=forecast_30min)
    fc_5min = fc_series.resample('5min').interpolate(method='linear')
    # Keep exactly 2016 5-min steps (7 days)
    fc_5min = fc_5min.iloc[:2016]

    # Convert to greenness if we predicted carbon intensity
    if has_ci:
        # Same formula as db_utils.carbon_intensity_to_greenness, vectorised
        ci = np.clip(fc_5min.values, 0, 500)
        yhat = 100.0 - ((ci - 50) / 3.5)
    else:
        yhat = fc_5min.values
        ci = None

    yhat = np.clip(yhat, 0, 100)

    result = pd.DataFrame({'ds': fc_5min.index, 'yhat': yhat})
    if ci is not None:
        result['ci'] = ci
    return result


def get_next_week_carbon_intensity(historical_df):
    """Predict next-week carbon intensity (gCO2/kWh) using SARIMAX.

    Args:
        historical_df: DataFrame with columns 'timestamp' and 'carbon_intensity'.

    Returns:
        DataFrame with columns 'ds' (datetime) and 'yhat' (gCO2/kWh, 0-500).
    """
    df = historical_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    series = df.set_index('timestamp')['carbon_intensity'].copy()
    series = series[series.notna()]
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq='30min')
    series = series.reindex(full_idx).interpolate(method='time').asfreq('30min')

    if len(series) > MAX_TRAIN_POINTS:
        series = series.iloc[-MAX_TRAIN_POINTS:]

    model = SARIMAX(
        series,
        order=(1, 0, 1),
        seasonal_order=(1, 0, 1, 48),
        trend='c',
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False, maxiter=200)

    n_forecast = 337
    raw_forecast = fit.forecast(steps=n_forecast)
    raw_forecast = np.clip(raw_forecast.values, 0, 500)

    last_ts = series.index[-1]
    forecast_30min = pd.date_range(
        start=last_ts + pd.Timedelta(minutes=30),
        periods=n_forecast,
        freq='30min',
    )

    fc_series = pd.Series(raw_forecast, index=forecast_30min)
    fc_5min = fc_series.resample('5min').interpolate(method='linear')
    fc_5min = fc_5min.iloc[:2016]

    yhat = np.clip(fc_5min.values, 0, 500)

    return pd.DataFrame({'ds': fc_5min.index, 'yhat': yhat})
