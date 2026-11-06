import time

from pydantic import SecretStr

from app.auth.dependencies import _is_valid_admin_session, create_admin_session
from app.core.config import Settings


def settings(secret: str = 'test-session-secret') -> Settings:
    return Settings(_env_file=None, session_secret=SecretStr(secret))


def test_default_admin_session_lasts_twelve_hours(monkeypatch):
    monkeypatch.delenv('SESSION_TTL_MINUTES', raising=False)
    config = settings()
    assert config.session_ttl_minutes == 720
    issued = 1_800_000_000
    monkeypatch.setattr(time, 'time', lambda: issued)
    token = create_admin_session(config)
    monkeypatch.setattr(time, 'time', lambda: issued + 12 * 3600 - 1)
    assert _is_valid_admin_session(token, config)
    monkeypatch.setattr(time, 'time', lambda: issued + 12 * 3600)
    assert not _is_valid_admin_session(token, config)


def test_session_is_rejected_after_secret_rotation():
    token = create_admin_session(settings())
    assert not _is_valid_admin_session(token, settings('rotated-secret'))
