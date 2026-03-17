import threading

import carbon_collector
import db_utils
import services
from config import DATA_CENTRES, FAILURE_THRESHOLD, logger
from predictor import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)

stop_event = threading.Event()


def _run_loop(name, interval, func):
    failures = 0
    while not stop_event.is_set():
        try:
            func()
            failures = 0
        except Exception as e:
            failures += 1
            logger.error(f'{name} failed ({failures}): {e}')
            if failures >= FAILURE_THRESHOLD:
                logger.critical(f'ALERT: {name} is down!')
        stop_event.wait(timeout=interval)


def prediction_loop():
    def update():
        for dc in DATA_CENTRES:
            # Generate and cache Load
            db_utils.save_prediction(
                f'load_{dc}', generate_next_week_load_prediction(dc)
            )
            # Generate and cache Carbon
            db_utils.save_prediction(
                f'carbon_{dc}', generate_next_week_carbon_intensity_prediction(dc)
            )

    _run_loop('Prediction', 300, update)  # Run every 5 mins


def carbon_collector_loop():
    def collect_and_sync():
        with carbon_collector.get_db() as conn:
            carbon_collector.fetch_and_store(conn)

        # Bridge the newly fetched data over to the main cache DB
        services.sync_carbon_to_historical(days_back=1)

    _run_loop('Collector', 1800, collect_and_sync)  # Run every 30 mins
