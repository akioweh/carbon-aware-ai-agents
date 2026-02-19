import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


def _build_features(timestamps):
    """Build cyclical and trend features from timestamps."""
    ts = pd.Series(timestamps) if not isinstance(timestamps, pd.Series) else timestamps
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek
    minute_of_day = ts.dt.hour * 60 + ts.dt.minute

    features = pd.DataFrame({
        'hour_sin': np.sin(2 * np.pi * hour / 24),
        'hour_cos': np.cos(2 * np.pi * hour / 24),
        'dow_sin': np.sin(2 * np.pi * dow / 7),
        'dow_cos': np.cos(2 * np.pi * dow / 7),
        'minute_sin': np.sin(2 * np.pi * minute_of_day / 1440),
        'minute_cos': np.cos(2 * np.pi * minute_of_day / 1440),
        'trend': np.arange(len(timestamps), dtype=float),
    })
    return features


def _predict(historical_df, value_col, clip_min, clip_max):
    df = historical_df.rename(columns={'timestamp': 'ds', value_col: 'y'})
    df['ds'] = pd.to_datetime(df['ds'])
    df = df.sort_values('ds').reset_index(drop=True)

    X_train = _build_features(df['ds'])
    y_train = df['y'].values

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    last_ts = df['ds'].iloc[-1]
    future_ds = pd.date_range(
        start=last_ts + pd.Timedelta(minutes=5),
        periods=2016,
        freq='5min',
    )

    X_future = _build_features(future_ds)
    # Continue trend from where training left off
    X_future['trend'] = np.arange(len(df), len(df) + 2016, dtype=float)

    yhat = model.predict(X_future)
    yhat = np.clip(yhat, clip_min, clip_max)

    return pd.DataFrame({'ds': future_ds, 'yhat': yhat})


def get_next_week_load(historical_load):
    return _predict(historical_load, 'load', 0, 50)


def get_next_week_greenness(historical_greenness):
    return _predict(historical_greenness, 'greenness', 0, 100)
