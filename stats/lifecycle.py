import threading

import carbon_collector
import db_utils
import services
from tasks import carbon_collector_loop, prediction_loop


def start_up():
    db_utils.initialize_db()
    carbon_collector.init_database()
    services.sync_carbon_to_historical(days_back=30)

    threads = [
        threading.Thread(target=prediction_loop, daemon=True),
        threading.Thread(target=carbon_collector_loop, daemon=True),
    ]
    for t in threads:
        t.start()
    return threads
