from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    kind: Literal['OPENAI', 'GEMINI', 'ANTHROPIC', 'OPENAI_COMPATIBLE']
    base_url: str | None = Field(default=None, max_length=2048)
    default_model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr | None = None

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            url = urlsplit(value)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
                raise ValueError
        except ValueError:
            raise ValueError('Base URL must be HTTPS without credentials, query or fragment') from None
        return value


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    kind: str
    base_url: str | None
    default_model: str
    enabled: bool
    archived: bool
    is_default: bool
    has_api_key: bool
    adapter_verified: bool = False
    last_checked_at: datetime | None = None
    last_check_status: str | None = None
    last_check_model_listed: bool | None = None
    created_at: datetime
    updated_at: datetime


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    base_url: str | None = Field(default=None, max_length=2048)
    default_model: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    api_key: SecretStr | None = None
    revoke_api_key: bool = False

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return ProviderCreate.validate_base_url(value)
