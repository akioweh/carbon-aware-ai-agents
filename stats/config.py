import logging
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / 'cache.db'
CARBON_DB_FILE = BASE_DIR / os.environ.get('CARBON_DB_PATH', 'carbon_intensity.db')

# Mappings
UK_REGION_TO_DC = {
    13: 'Data-Center-1',
    14: 'Data-Center-2',
    5: 'Data-Center-3',
    3: 'Data-Center-4',
    4: 'Data-Center-5',
}
DATA_CENTRES = list(UK_REGION_TO_DC.values())

# Settings
HOST = os.environ.get('STATS_HOST', '127.0.0.1')
PORT = int(os.environ.get('STATS_PORT', 5000))
CARBON_SYNC_INTERVAL = int(os.environ.get('CARBON_SYNC_INTERVAL', 1800))
CARBON_COLLECTION_ENABLED = os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'
FAILURE_THRESHOLD = int(os.environ.get('FAILURE_ALERT_THRESHOLD', 5))

# Logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('stats.app')

MAX_CAPACITY_UNITS = 50.0
LOAD_SCALE_FACTOR = float(os.environ.get('LOAD_SCALE_FACTOR', 1e12))
TOTAL_CAPACITY = MAX_CAPACITY_UNITS * LOAD_SCALE_FACTOR
