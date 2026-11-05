"""Read-only, Owner-accessible prompt version registry."""
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_owner
from app.db.models import AIPromptVersion
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/prompts', dependencies=[Depends(require_owner)], tags=['ai-prompts'])


class PromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    version: str
    purpose: str
    system_text: str
    developer_text: str
    input_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    constraints_json: dict[str, Any]
    created_at: datetime


@router.get('', response_model=list[PromptResponse])
def list_prompts(limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    return list(db.scalars(select(AIPromptVersion).order_by(AIPromptVersion.created_at, AIPromptVersion.id).offset(offset).limit(limit)))
