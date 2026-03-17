import pandas as pd

from ..src.scripts.generate_mock_historical_data import (
    calculate_simulated_datacenter_load,
)


def get_next_week_load(historical_df, now=None) -> pd.DataFrame:
    """Generate next week's load forecast using the simulator function."""
    if now is None:
        now = pd.Timestamp.now()

    start = now.ceil('5min')
    timestamps = pd.date_range(start, periods=2016, freq='5min')

    # Use calculate_simulated_datacenter_load instead of the module name
    values = [
        calculate_simulated_datacenter_load(ts.to_pydatetime(), 0) for ts in timestamps
    ]

    return pd.DataFrame({'ds': timestamps, 'yhat': values})
