import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_admin_session(settings: Settings) -> str:
    now = int(time.time())
    payload = {"sub": "owner", "iat": now, "exp": now + settings.session_ttl_minutes * 60, "nonce": secrets.token_urlsafe(16)}
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def _is_valid_admin_session(token: str, settings: Settings) -> bool:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_encode(expected), signature):
            return False
        payload = json.loads(_decode(encoded))
        return payload.get("sub") == "owner" and isinstance(payload.get("exp"), int) and payload["exp"] > time.time()
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def require_owner(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    if not (secrets.compare_digest(credentials.credentials, settings.owner_api_key.get_secret_value()) or _is_valid_admin_session(credentials.credentials, settings)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return "owner"

