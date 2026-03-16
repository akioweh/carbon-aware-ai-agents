import threading

import db_utils
from carbon_collector import (
    DB_PATH as CARBON_DB_PATH,
)
from carbon_collector import INTERVAL_MINUTES as CARBON_INTERVAL_MINUTES
from carbon_collector import collect_current, get_reading_count
from carbon_collector import init_database as init_carbon_db
from config import _FAILURE_ALERT_THRESHOLD, CARBON_SYNC_INTERVAL, logger
from generate_history import DATA_CENTRES
from predictor import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)

stop_event = threading.Event()


def prediction_loop():
    """Background loop to update predictions every 5 minutes."""
    consecutive_failures: dict[str, int] = {dc: 0 for dc in DATA_CENTRES}
    while not stop_event.is_set():
        logger.info('Updating predictions cache...')
        for dc in DATA_CENTRES:
            try:
                # Update Load Predictions
                load_data = generate_next_week_load_prediction(dc)
                db_utils.save_prediction(f'load_forecast_{dc}', load_data)

                # Update Carbon Intensity Predictions
                try:
                    ci_data = generate_next_week_carbon_intensity_prediction(dc)
                    db_utils.save_prediction(f'carbon_intensity_forecast_{dc}', ci_data)
                except ValueError as e:
                    logger.warning(
                        'ValueError updating CI predictions for %s: %s', dc, e
                    )
                    logger.warning(
                        'No carbon intensity data for %s, skipping CI forecast', dc
                    )

                if consecutive_failures[dc]:
                    logger.info(
                        'Prediction loop recovered for %s after %d failure(s)',
                        dc,
                        consecutive_failures[dc],
                    )
                consecutive_failures[dc] = 0
            except Exception as e:
                consecutive_failures[dc] += 1
                logger.error(
                    'Error updating predictions for %s (consecutive failures: %d): %s',
                    dc,
                    consecutive_failures[dc],
                    e,
                    exc_info=True,
                )
                if consecutive_failures[dc] >= _FAILURE_ALERT_THRESHOLD:
                    logger.critical(
                        'ALERT: prediction loop for %s has failed %d times in a row — predictions may be stale',
                        dc,
                        consecutive_failures[dc],
                    )

        stop_event.wait(timeout=CARBON_SYNC_INTERVAL)


def carbon_sync_loop():
    """Background loop to sync carbon intensity data periodically."""
    consecutive_failures = 0
    while not stop_event.is_set():
        try:
            if db_utils.has_carbon_data():
                count = db_utils.sync_carbon_to_historical(days_back=7)
                logger.info('Carbon sync: %d records updated', count)
            if consecutive_failures:
                logger.info(
                    'Carbon sync loop recovered after %d failure(s)',
                    consecutive_failures,
                )
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.error(
                'Error syncing carbon data (consecutive failures: %d)',
                consecutive_failures,
                exc_info=True,
            )
            if consecutive_failures >= _FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon sync loop has failed %d times in a row — carbon data in cache.db may be stale',
                    consecutive_failures,
                )
        stop_event.wait(timeout=CARBON_SYNC_INTERVAL)


def carbon_collector_loop():
    """Background loop to collect carbon intensity data from UK API."""
    logger.info('Carbon collector starting (interval: %d min)', CARBON_INTERVAL_MINUTES)
    logger.info('Database: %s', CARBON_DB_PATH)

    conn = init_carbon_db(CARBON_DB_PATH)

    consecutive_failures = 0
    while not stop_event.is_set():
        try:
            collect_current(conn)
            logger.info('Carbon readings total: %d', get_reading_count(conn))
            if consecutive_failures:
                logger.info(
                    'Carbon collector loop recovered after %d failure(s)',
                    consecutive_failures,
                )
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.error(
                'Error collecting carbon data (consecutive failures: %d)',
                consecutive_failures,
                exc_info=True,
            )
            if consecutive_failures >= _FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon collector has failed %d times in a row — no new carbon readings are being stored',
                    consecutive_failures,
                )
        stop_event.wait(CARBON_INTERVAL_MINUTES * 60)
