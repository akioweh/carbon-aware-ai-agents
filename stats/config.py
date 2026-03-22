"""Shared configuration — env vars, constants, and logging setup."""

import logging
import os
from pathlib import Path

_STATS_DIR = Path(__file__).parent

LOG_FILE = os.environ.get('STATS_LOG_FILE', 'app.log')

# Database paths
DB_FILE = _STATS_DIR / 'cache.db'
CARBON_DB_FILE = Path(os.environ.get('CARBON_DB_PATH', _STATS_DIR / 'carbon_intensity.db'))

# Logging setup — writes to both stdout and a persistent log file
_log_fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=_log_fmt,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)

HOST = os.environ.get('STATS_HOST', '127.0.0.1')
PORT = int(os.environ.get('STATS_PORT', 5000))
CARBON_SYNC_INTERVAL = int(os.environ.get('CARBON_SYNC_INTERVAL', 1800))  # 30 min
PREDICTION_INTERVAL = int(os.environ.get('PREDICTION_INTERVAL', 1800))  # 30 min
PREDICTION_CACHE_TTL = int(os.environ.get('PREDICTION_CACHE_TTL', 2400))  # 35 min
CARBON_COLLECTION_ENABLED = os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'

PREDICTION_WINDOW_HOURS = 7 * 24

# Carbon collector settings
CARBON_INTERVAL_MINUTES = int(os.environ.get('CARBON_INTERVAL_MINUTES', 30))
BACKFILL_DAYS = int(os.environ.get('BACKFILL_DAYS', 365))
API_BASE_URL = 'https://api.carbonintensity.org.uk'

# Datacenter capacity constants
GPUS_PER_DATACENTER = 200
FLOS_PER_GPU = 4.92e15  # FLOs per GPU per 5-minute interval
DEFAULT_CAPACITY = GPUS_PER_DATACENTER * FLOS_PER_GPU

# Threshold: log a CRITICAL alert after this many consecutive failures in a loop
FAILURE_ALERT_THRESHOLD = int(os.environ.get('FAILURE_ALERT_THRESHOLD', 5))
