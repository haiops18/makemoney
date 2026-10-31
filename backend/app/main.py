from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.routes import router
from app.api.approval_routes import router as approval_router
from app.api.finance_routes import router as finance_router
from app.core.config import get_settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().validate_deployment()
    yield


app = FastAPI(title="AUTO MONEY AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(approval_router)
app.include_router(finance_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}

