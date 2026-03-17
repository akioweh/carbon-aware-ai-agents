from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import HOST, PORT
from lifecycle import start_up
from routes import router
from tasks import stop_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    active_threads = start_up()
    yield
    stop_event.set()
    for t in active_threads:
        t.join(timeout=2)


app = FastAPI(lifespan=lifespan)
app.include_router(router)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
