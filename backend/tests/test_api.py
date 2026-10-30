def test_protected_routes_require_owner(client):
    assert client.get("/api/v1/agents").status_code == 401


def test_root_redirects_to_api_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_agent_update_is_audited_and_idempotent(client, auth_headers):
    agents = client.get("/api/v1/agents", headers=auth_headers).json()
    agent_id = agents[0]["id"]
    headers = auth_headers | {"Idempotency-Key": "disable-research-001"}

    first = client.patch(f"/api/v1/agents/{agent_id}", headers=headers, json={"enabled": False})
    second = client.patch(f"/api/v1/agents/{agent_id}", headers=headers, json={"enabled": False})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["enabled"] is False
    events = client.get("/api/v1/audit-events", headers=auth_headers).json()
    assert len(events) == 1
    assert events[0]["action"] == "agent.updated"


def test_idempotency_key_cannot_be_reused_for_another_request(client, auth_headers):
    agent_id = client.get("/api/v1/agents", headers=auth_headers).json()[0]["id"]
    headers = auth_headers | {"Idempotency-Key": "same-key"}
    client.patch(f"/api/v1/agents/{agent_id}", headers=headers, json={"enabled": False})

    response = client.patch(f"/api/v1/agents/{agent_id}", headers=headers, json={"enabled": True})
    assert response.status_code == 409


def test_production_rejects_example_owner_key():
    from app.core.config import Settings

    settings = Settings(environment="production", owner_api_key="replace-with-a-long-random-secret")
    try:
        settings.validate_deployment()
    except RuntimeError:
        return
    assert False, "example owner key must not be accepted in production"
