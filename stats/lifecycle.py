import threading

import db_utils
from carbon_collector import DB_PATH as CARBON_DB_PATH
from carbon_collector import backfill
from carbon_collector import init_database as init_carbon_db
from config import CARBON_COLLECTION_ENABLED, logger
from generate_history import generate_history
from tasks import carbon_collector_loop, carbon_sync_loop, prediction_loop


def run_startup_logic():
    """Initializes DBs, backfills data, and starts background threads."""
    db_utils.initialize_db()

    if CARBON_COLLECTION_ENABLED:
        try:
            conn = init_carbon_db(CARBON_DB_PATH)
            backfill(conn)
            conn.close()
        except Exception:
            logger.error('Carbon backfill failed', exc_info=True)

    if db_utils.has_carbon_data():
        db_utils.sync_carbon_to_historical(days_back=30)

    if db_utils.count_historical_data() == 0:
        generate_history()

    # Define and start threads
    threads = [threading.Thread(target=prediction_loop, daemon=True)]
    if CARBON_COLLECTION_ENABLED or db_utils.has_carbon_data():
        threads.extend(
            [
                threading.Thread(target=carbon_collector_loop, daemon=True),
                threading.Thread(target=carbon_sync_loop, daemon=True),
            ]
        )

    for t in threads:
        t.start()

    return threads
