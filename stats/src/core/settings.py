import logging
import os
from pathlib import Path

# Paths
BASE_PROJECT_DIRECTORY = Path(__file__).parent.parent
MAIN_CACHE_SQLITE_DB_PATH = BASE_PROJECT_DIRECTORY / 'cache.db'
CARBON_INTENSITY_SQLITE_DB_PATH = BASE_PROJECT_DIRECTORY / os.environ.get(
    'CARBON_DB_PATH', 'carbon_intensity.db'
)

# Mappings
UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING = {
    13: 'Data-Center-1',
    14: 'Data-Center-2',
    5: 'Data-Center-3',
    3: 'Data-Center-4',
    4: 'Data-Center-5',
}
SUPPORTED_DATACENTER_NAMES = list(
    UK_CARBON_API_REGION_ID_TO_DATACENTER_NAME_MAPPING.values()
)

# API Settings
API_HOST_ADDRESS = os.environ.get('STATS_HOST', '127.0.0.1')
API_PORT_NUMBER = int(os.environ.get('STATS_PORT', 5000))

# Worker Settings
CARBON_DATA_SYNC_INTERVAL_IN_SECONDS = int(os.environ.get('CARBON_SYNC_INTERVAL', 1800))
IS_CARBON_DATA_COLLECTION_ENABLED = (
    os.environ.get('CARBON_COLLECTION_ENABLED', '1') == '1'
)
BACKGROUND_JOB_FAILURE_ALERT_THRESHOLD = int(
    os.environ.get('FAILURE_ALERT_THRESHOLD', 5)
)

# Logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
application_logger = logging.getLogger('stats.app')

# Capacity & Load Settings
MAXIMUM_DATACENTER_CAPACITY_IN_UNITS = 50.0
DATACENTER_LOAD_SCALING_MULTIPLIER = float(os.environ.get('LOAD_SCALE_FACTOR', 2))
TOTAL_SCALED_DATACENTER_CAPACITY = (
    MAXIMUM_DATACENTER_CAPACITY_IN_UNITS * DATACENTER_LOAD_SCALING_MULTIPLIER
)
