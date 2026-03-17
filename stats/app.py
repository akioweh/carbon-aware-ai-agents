from contextlib import asynccontextmanager

from fastapi import FastAPI
from src.core.app_startup import initialize_app_and_start_background_workers

from src.api.routers import forecast_api_router
from src.core.settings import API_HOST_ADDRESS, API_PORT_NUMBER
from src.workers.background_jobs import background_worker_stop_signal


@asynccontextmanager
async def app_lifespan_manager(fastapi_app: FastAPI):
    running_worker_threads = initialize_app_and_start_background_workers()
    yield
    background_worker_stop_signal.set()
    for worker_thread in running_worker_threads:
        worker_thread.join(timeout=2)


application = FastAPI(lifespan=app_lifespan_manager)
application.include_router(forecast_api_router)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(application, host=API_HOST_ADDRESS, port=API_PORT_NUMBER)
