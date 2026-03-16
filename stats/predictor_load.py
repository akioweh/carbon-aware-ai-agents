"""Load predictor — generates synthetic next-week load using generate_load()."""

import pandas as pd

from generate_history import generate_load


def get_next_week_load(historical_df) -> pd.DataFrame:
    """Generate next week's load forecast (2016 data points, 7 days × 288/day).

    Returns DataFrame with columns 'ds' and 'yhat'.
    """
    now = pd.Timestamp.now()
    start = now.ceil('5min')
    timestamps = pd.date_range(start, periods=2016, freq='5min')
    values = [generate_load(ts.to_pydatetime(), 0) for ts in timestamps]
    return pd.DataFrame({'ds': timestamps, 'yhat': values})
