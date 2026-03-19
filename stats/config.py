"""Shared configuration — env vars, constants, and logging setup."""

import logging
import os

LOG_FILE = os.environ.get('STATS_LOG_FILE', 'app.log')

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
CARBON_COLLECTION_ENABLED = os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'

PREDICTION_WINDOW_HOURS = 7 * 24

# Datacenter capacity constants
GPUS_PER_DATACENTER = 200
FLOS_PER_GPU = 4.92e15  # FLOs per GPU per 5-minute interval
DEFAULT_CAPACITY = GPUS_PER_DATACENTER * FLOS_PER_GPU

# Threshold: log a CRITICAL alert after this many consecutive failures in a loop
FAILURE_ALERT_THRESHOLD = int(os.environ.get('FAILURE_ALERT_THRESHOLD', 5))
