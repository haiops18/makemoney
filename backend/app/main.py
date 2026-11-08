from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.routes import router
from app.api.approval_routes import router as approval_router
from app.api.finance_routes import router as finance_router
from app.api.auth_routes import router as auth_router
from app.api.opportunity_routes import router as opportunity_router
from app.api.workflow_routes import router as workflow_router
from app.api.ai_provider_routes import router as ai_provider_router
from app.api.ai_profile_routes import router as ai_profile_router
from app.api.ai_research_routes import router as ai_research_router
from app.api.ai_pricing_routes import router as ai_pricing_router
from app.api.ai_prompt_routes import router as ai_prompt_router
from app.api.ai_control_routes import router as ai_control_router
from app.api.ai_usage_routes import router as ai_usage_router
from app.api.campaign_routes import router as campaign_router
from app.api.content_routes import router as content_router
from app.api.content_review_routes import router as content_review_router
from app.api.integration_routes import router as integration_router
from app.api.discovery_routes import router as discovery_router
from app.core.config import get_settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().validate_deployment()
    yield


app = FastAPI(title="AUTO MONEY AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(approval_router)
app.include_router(finance_router)
app.include_router(auth_router)
app.include_router(opportunity_router)
app.include_router(workflow_router)
app.include_router(ai_provider_router)
app.include_router(ai_profile_router)
app.include_router(ai_research_router)
app.include_router(ai_pricing_router)
app.include_router(ai_prompt_router)
app.include_router(ai_control_router)
app.include_router(ai_usage_router)
app.include_router(campaign_router)
app.include_router(content_router)
app.include_router(content_review_router)
app.include_router(integration_router)
app.include_router(discovery_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}

