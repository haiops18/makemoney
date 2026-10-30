from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().validate_deployment()
    yield


app = FastAPI(title="AUTO MONEY AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}

