import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import create_admin_session
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class AdminLoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=AdminLoginResponse)
def login(body: AdminLoginInput, settings: Settings = Depends(get_settings)) -> AdminLoginResponse:
    valid = secrets.compare_digest(body.username, settings.admin_username) and secrets.compare_digest(body.password, settings.admin_password.get_secret_value())
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return AdminLoginResponse(access_token=create_admin_session(settings), expires_in=settings.session_ttl_minutes * 60)
