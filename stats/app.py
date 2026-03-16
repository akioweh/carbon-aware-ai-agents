from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from config import HOST, PORT, logger
from lifecycle import run_startup_logic
from routes import router
from tasks import stop_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    active_threads = run_startup_logic()

    with open('openapi.yaml', 'w') as f:
        yaml.dump(app.openapi(), f, sort_keys=False)

    yield  # App is running

    logger.info('Shutting down...')
    stop_event.set()
    for t in active_threads:
        t.join(timeout=2)


app = FastAPI(title='Stats API', version='1.0.0', lifespan=lifespan)
app.include_router(router)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
