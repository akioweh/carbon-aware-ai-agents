import logging
import os

DB_FILE = 'cache.db'
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
logger = logging.getLogger('stats.app')

# Threshold: log a CRITICAL alert after this many consecutive failures in a loop
_FAILURE_ALERT_THRESHOLD = int(os.environ.get('FAILURE_ALERT_THRESHOLD', 5))

# Configuration for Oracle/server deployment
HOST = os.environ.get('STATS_HOST', '127.0.0.1')
PORT = int(os.environ.get('STATS_PORT', 5000))
CARBON_SYNC_INTERVAL = int(os.environ.get('CARBON_SYNC_INTERVAL', 1800))  # 30 min
CARBON_COLLECTION_ENABLED = os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'
