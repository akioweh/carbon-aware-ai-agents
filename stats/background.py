"""Background loops for prediction updates, carbon sync, and carbon collection."""

import logging
import time

import db_utils
from carbon_collector import (
    DB_PATH as CARBON_DB_PATH,
)
from carbon_collector import (
    INTERVAL_MINUTES as CARBON_INTERVAL_MINUTES,
)
from carbon_collector import (
    collect_current,
    get_reading_count,
)
from carbon_collector import (
    init_database as init_carbon_db,
)
from config import CARBON_SYNC_INTERVAL, FAILURE_ALERT_THRESHOLD
from predictors import (
    generate_next_week_carbon_intensity_prediction,
    generate_next_week_load_prediction,
)

logger = logging.getLogger('stats.background')


def prediction_loop():
    """Background loop to update predictions every 5 minutes."""
    consecutive_failures: dict[str, int] = {}
    while True:
        logger.info('Updating predictions cache...')

        active_datacenters = db_utils.get_all_datacenter_ids()
        if not active_datacenters:
            logger.warning(
                'No active datacenters configured; skipping prediction refresh'
            )
            time.sleep(300)
            continue

        for dc in list(consecutive_failures):
            if dc not in active_datacenters:
                del consecutive_failures[dc]

        for dc in active_datacenters:
            consecutive_failures.setdefault(dc, 0)
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
                if consecutive_failures[dc] >= FAILURE_ALERT_THRESHOLD:
                    logger.critical(
                        'ALERT: prediction loop for %s has failed %d times in a row — predictions may be stale',
                        dc,
                        consecutive_failures[dc],
                    )

        time.sleep(300)


def carbon_sync_loop():
    """Background loop to sync carbon intensity data periodically."""
    consecutive_failures = 0
    while True:
        try:
            if db_utils.has_carbon_data():
                count = db_utils.sync_carbon_to_historical()
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
            if consecutive_failures >= FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon sync loop has failed %d times in a row — carbon data in cache.db may be stale',
                    consecutive_failures,
                )
        time.sleep(CARBON_SYNC_INTERVAL)


def carbon_collector_loop():
    """Background loop to collect carbon intensity data from UK API."""
    logger.info('Carbon collector starting (interval: %d min)', CARBON_INTERVAL_MINUTES)
    logger.info('Database: %s', CARBON_DB_PATH)

    conn = init_carbon_db(CARBON_DB_PATH)

    consecutive_failures = 0
    while True:
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
            if consecutive_failures >= FAILURE_ALERT_THRESHOLD:
                logger.critical(
                    'ALERT: carbon collector has failed %d times in a row — no new carbon readings are being stored',
                    consecutive_failures,
                )
        time.sleep(CARBON_INTERVAL_MINUTES * 60)
