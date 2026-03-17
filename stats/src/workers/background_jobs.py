import threading

from ..core.settings import (
    BACKGROUND_JOB_FAILURE_ALERT_THRESHOLD,
    SUPPORTED_DATACENTER_NAMES,
    application_logger,
)
from ..database import repository
from ..services import carbon_api_client, data_synchronizer
from ..services.forecasting_engine import (
    predict_carbon_intensity_for_next_seven_days,
    predict_datacenter_load_for_next_seven_days,
)

background_worker_stop_signal = threading.Event()


def execute_function_in_continuous_loop(
    job_name, sleep_interval_seconds, target_function
):
    consecutive_failures = 0
    while not background_worker_stop_signal.is_set():
        try:
            target_function()
            consecutive_failures = 0
        except Exception as error:
            consecutive_failures += 1
            application_logger.error(
                f'Background Job [{job_name}] failed ({consecutive_failures} times): {error}'
            )

            if consecutive_failures >= BACKGROUND_JOB_FAILURE_ALERT_THRESHOLD:
                application_logger.critical(
                    f'ALERT: Background Job[{job_name}] has exceeded failure threshold and is down!'
                )

        background_worker_stop_signal.wait(timeout=sleep_interval_seconds)


def start_continuous_forecast_generation_worker_loop():
    def update_predictions_in_cache():
        for datacenter in SUPPORTED_DATACENTER_NAMES:
            repository.save_forecast_to_cache_database(
                cache_key=f'load_forecast_{datacenter}',
                forecast_data_dict=predict_datacenter_load_for_next_seven_days(
                    datacenter
                ),
            )
            repository.save_forecast_to_cache_database(
                cache_key=f'carbon_intensity_forecast_{datacenter}',
                forecast_data_dict=predict_carbon_intensity_for_next_seven_days(
                    datacenter
                ),
            )

    # Run every 5 minutes (300s)
    execute_function_in_continuous_loop(
        'ForecastGeneration', 300, update_predictions_in_cache
    )


def start_continuous_carbon_data_collection_worker_loop():
    def collect_and_synchronize_carbon_data():
        with carbon_api_client.get_carbon_database_connection() as db_connection:
            carbon_api_client.fetch_latest_carbon_intensity_and_store_in_db(
                db_connection
            )

        data_synchronizer.synchronize_carbon_readings_to_main_historical_database(
            days_to_look_back=1
        )

    # Run every 30 mins (1800s)
    execute_function_in_continuous_loop(
        'CarbonDataCollector', 1800, collect_and_synchronize_carbon_data
    )
