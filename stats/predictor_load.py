"""Load predictor — generates synthetic next-week load using generate_load()."""

import pandas as pd

from generate_history import generate_load


def get_next_week_load(historical_df, now=None, dc_index: int = 0) -> pd.DataFrame:
    """Generate next week's load forecast (2016 data points, 7 days × 288/day).

    Args:
        historical_df: Historical load DataFrame (unused by the synthetic generator
            but kept for API compatibility with future ML-based predictors).
        now: Reference timestamp; defaults to the current time.
        dc_index: Index into DC_GPU_CONFIGS identifying the datacenter.  Determines
            the FLO scale of the generated values.

    Returns DataFrame with columns 'ds' and 'yhat'.
    """
    if now is None:
        now = pd.Timestamp.now()
    start = now.ceil('5min')
    timestamps = pd.date_range(start, periods=2016, freq='5min')
    values = [generate_load(ts.to_pydatetime(), dc_index) for ts in timestamps]
    return pd.DataFrame({'ds': timestamps, 'yhat': values})
