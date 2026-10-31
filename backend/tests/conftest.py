import os

os.environ["OWNER_API_KEY"] = "test-owner-key"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Agent, Policy
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session(engine) as session:
        session.add(Agent(name="Research Agent", role="research", model=None, enabled=True))
        session.add(Policy(
            name="owner-controlled-internal",
            version="1.0",
            description="Test policy",
            rules_json={"allowed_action_types": ["INTERNAL_WORKFLOW", "OPPORTUNITY_REVIEW"], "authorization_scope": "ONCE", "external_execution": False, "require_approval": True},
            enabled=True,
        ))
        session.commit()

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-owner-key"}

