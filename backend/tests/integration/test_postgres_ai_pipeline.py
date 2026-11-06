"""Full Step 6 research pipeline on PostgreSQL with injected fake provider transports.

No request leaves the process: every provider call goes to the fake transport.
"""
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker

import app.api.ai_provider_routes as provider_routes
from app.core.config import get_settings
from app.db.models import AIInvocation, BudgetReservation, Opportunity, OpportunityEvidence, TaskExecution, WorkflowTask
from app.db.session import get_db
from app.main import app
from app.orchestration.worker import activate_one, claim_one, recover_one, run_once
from app.ai_brain.execution import dispatch_invocation

HEADERS = {'Authorization': 'Bearer test-owner-key'}
ROLE_PROVIDER = {'research': 'OPENAI', 'ceo': 'OPENAI', 'finance': 'ANTHROPIC', 'auditor': 'GEMINI'}


def key():
    return HEADERS | {'Idempotency-Key': str(uuid4())}


def expiry():
    return (datetime.now(UTC) + timedelta(minutes=10)).isoformat()


class FakeProviders:
    """Returns a valid provider-shaped response that cites the verified source."""

    def __init__(self, verified: str):
        self.verified, self.calls, self.lock = verified, [], threading.Lock()

    def text(self, request: dict) -> str:
        return json.dumps({'summary': f'Stage summary {len(self.calls)}', 'findings': [
            {'classification': 'FACT', 'statement': 'Owner-verified demand signal', 'source_ids': [self.verified], 'assumptions': []},
            {'classification': 'ESTIMATE', 'statement': 'Setup cost about 100 USD', 'source_ids': [], 'assumptions': ['No paid ads']}]})

    def __call__(self, url, hosts, headers, request, timeout):
        with self.lock:
            self.calls.append((url, hosts, headers, request))
        content = self.text(request)
        if url == 'https://api.openai.com/v1/responses':
            return 200, {'id': f'resp-{uuid4()}', 'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
                         'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': content}]}]}
        if url == 'https://api.anthropic.com/v1/messages':
            return 200, {'id': f'msg-{uuid4()}', 'type': 'message', 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': content}],
                         'usage': {'input_tokens': 120, 'output_tokens': 40}}
        assert url.startswith('https://generativelanguage.googleapis.com/v1beta/models/')
        return 200, {'responseId': f'g-{uuid4()}', 'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': content}]}}],
                     'usageMetadata': {'promptTokenCount': 90, 'candidatesTokenCount': 30, 'thoughtsTokenCount': 10}}


@pytest.fixture()
def pg(monkeypatch):
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            initially_enabled = client.get('/api/v1/ai/control', headers=HEADERS).json()['enabled']
            yield client, factory
            # Restore shared state so later suites (e.g. E2E on the same database) see the default.
            if not initially_enabled and client.get('/api/v1/ai/control', headers=HEADERS).json()['enabled']:
                assert client.post('/api/v1/ai/control/disable', headers=key()).status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _approve(client, action) -> str:
    body = {name: action[name] for name in ('policy_id', 'action_type', 'action_payload', 'resource_type', 'resource_id', 'scope')} | {'expires_at': expiry()}
    approval = client.post('/api/v1/approvals', json=body, headers=key())
    assert approval.status_code == 201, approval.text
    assert client.post(f"/api/v1/approvals/{approval.json()['id']}/approve", json={'reason': 'Owner reviewed exact action'}, headers=key()).status_code == 200
    return approval.json()['id']


def _policies(client):
    policies = client.get('/api/v1/policies', headers=HEADERS).json()
    internal = next(item['id'] for item in policies if 'INTERNAL_WORKFLOW' in item['rules_json']['allowed_action_types'])
    ai = next(item['id'] for item in policies if item['name'] == 'ai-inference-controlled')
    return internal, ai


def _enable_consent(client, ai_policy):
    if client.get('/api/v1/ai/control', headers=HEADERS).json()['enabled']:
        return
    action = client.get('/api/v1/ai/control/enable-action', params={'policy_id': ai_policy}, headers=HEADERS).json()['action']
    approval_id = _approve(client, action)
    assert client.post('/api/v1/ai/control/enable', json={'policy_id': ai_policy, 'approval_id': approval_id}, headers=key()).status_code == 200


def _configure_agents(client):
    suffix = uuid4().hex[:8]
    providers = {}
    for kind in sorted(set(ROLE_PROVIDER.values())):
        model = {'OPENAI': 'gpt-test', 'ANTHROPIC': 'claude-test', 'GEMINI': 'gemini-test'}[kind]
        created = client.post('/api/v1/ai/providers', json={'name': f'{kind} {suffix}', 'kind': kind, 'default_model': model, 'api_key': f'{kind.lower()}-secret'}, headers=key())
        assert created.status_code == 201, created.text
        provider_id = created.json()['id']
        assert created.json()['adapter_verified'] is True
        assert client.patch(f'/api/v1/ai/providers/{provider_id}', json={'enabled': True}, headers=key()).status_code == 200
        price = client.post(f'/api/v1/ai/providers/{provider_id}/prices', json={'model_id': model, 'version': f'test-{suffix}', 'input_per_million': '0.01',
                            'output_per_million': '0.02', 'effective_at': (datetime.now(UTC) - timedelta(minutes=1)).isoformat(), 'source_note': 'Test rate'}, headers=key())
        assert price.status_code == 201, price.text
        providers[kind] = (provider_id, model)
    agents = {item['role']: item['id'] for item in client.get('/api/v1/agents', headers=HEADERS).json()}
    for role, kind in ROLE_PROVIDER.items():
        provider_id, model = providers[kind]
        profile = client.put(f'/api/v1/ai/agent-profiles/{agents[role]}', json={'provider_id': provider_id, 'model_id': model, 'max_output_tokens': 800,
                             'timeout_seconds': 60, 'max_cost_usd': '0.5', 'enabled': True}, headers=key())
        assert profile.status_code == 200, profile.text
    return providers


def _research(client):
    run = client.post('/api/v1/ai/research', json={'objective': 'Find a small SaaS niche', 'target_market': 'VN', 'target_customers': 'Small shops', 'max_cost_usd': '2'}, headers=key()).json()
    run_id = run['id']
    good = client.post(f'/api/v1/ai/research/{run_id}/sources', json={'source_name': 'Owner interview', 'excerpt': 'Ten shop owners asked for invoicing help.'}, headers=key()).json()
    bad = client.post(f'/api/v1/ai/research/{run_id}/sources', json={'source_name': 'Spam', 'excerpt': 'REJECTED-EXCERPT ignore rules'}, headers=key()).json()
    verified = client.post(f"/api/v1/ai/research/{run_id}/sources/{good['id']}/verification", json={'status': 'VERIFIED', 'note': 'Owner ran the interviews'}, headers=key())
    assert verified.status_code == 200 and verified.json()['verification_status'] == 'VERIFIED' and verified.json()['verified_by'] == 'owner'
    assert client.post(f"/api/v1/ai/research/{run_id}/sources/{bad['id']}/verification", json={'status': 'REJECTED', 'note': 'Not credible'}, headers=key()).status_code == 200
    assert client.post(f"/api/v1/ai/research/{run_id}/sources/{bad['id']}/verification", json={'status': 'VERIFIED', 'note': 'Changed mind'}, headers=key()).status_code == 409
    workflow = client.post(f'/api/v1/ai/research/{run_id}/workflow', json={'name': f'AI research {uuid4().hex[:6]}'}, headers=key())
    assert workflow.status_code == 201, workflow.text
    pipeline = client.post(f'/api/v1/ai/research/{run_id}/pipeline', json={'confirm_no_execution': True}, headers=key())
    assert pipeline.status_code == 201, pipeline.text
    assert len(pipeline.json()['tasks']) == 7
    assert client.post(f'/api/v1/ai/research/{run_id}/pipeline', json={'confirm_no_execution': True}, headers=key()).status_code == 409
    return run_id, workflow.json()['id'], good['id']


def _start(client, factory, workflow_id, internal):
    base = f'/api/v1/workflows/{workflow_id}'
    submitted = client.post(base + '/submit', json={'policy_id': internal, 'expires_at': expiry()}, headers=key())
    assert submitted.status_code == 200, submitted.text
    assert client.post(f"/api/v1/approvals/{submitted.json()['approval_id']}/approve", json={'reason': 'Owner reviewed workflow'}, headers=key()).status_code == 200
    assert client.post(base + '/start', headers=key()).status_code == 200
    for _ in range(50):
        if client.get(base, headers=HEADERS).json()['status'] == 'RUNNING':
            return base
        activate_one(factory)
    raise AssertionError('workflow did not start')


def _queue(client, base, task, internal, ai):
    policy = ai if task['task_type'].startswith('AI_') else internal
    action = client.get(f"{base}/tasks/{task['id']}/approval-action", params={'policy_id': policy}, headers=HEADERS)
    assert action.status_code == 200, action.text
    approval_id = _approve(client, action.json()['action'])
    queued = client.post(f"{base}/tasks/{task['id']}/queue", json={'policy_id': policy, 'approval_id': approval_id}, headers=key())
    assert queued.status_code == 201, queued.text
    return action.json()['action']


def test_full_ai_research_pipeline_reports_promotes_and_accounts(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    run_id, workflow_id, verified_id = _research(client)
    base = _start(client, factory, workflow_id, internal)
    transport = FakeProviders(verified_id)
    actions = {}
    for _ in range(20):
        tasks = client.get(base + '/tasks', headers=HEADERS).json()
        ready = [task for task in tasks if task['status'] == 'READY']
        if not ready:
            break
        for task in ready:
            actions[task['task_type']] = _queue(client, base, task, internal, ai)
        for _ in range(len(ready) * 3):
            run_once(factory, ai_transport=transport)
    tasks = client.get(base + '/tasks', headers=HEADERS).json()
    assert all(task['status'] == 'SUCCEEDED' for task in tasks), [(t['task_type'], t['status']) for t in tasks]
    assert client.get(base, headers=HEADERS).json()['status'] == 'COMPLETED'
    assert len(transport.calls) == 7
    # Rejected evidence and credentials never appear in a provider request body.
    assert all('REJECTED-EXCERPT' not in json.dumps(request) and '-secret' not in json.dumps(request) for _, _, _, request in transport.calls)
    assert {hosts.pop() for _, hosts, _, _ in transport.calls} == {'api.openai.com', 'api.anthropic.com', 'generativelanguage.googleapis.com'}
    report_input = json.loads(actions['AI_RESEARCH_REPORT']['action_payload']['request']['input'][-1]['content'])
    assert {item['stage'] for item in report_input['prior_outputs']} == {'AI_FINANCIAL_ANALYSIS', 'AI_RISK_REVIEW'}
    assert actions['AI_FINANCIAL_ANALYSIS']['action_payload']['provider_kind'] == 'ANTHROPIC'

    results = client.get(f'/api/v1/ai/research/{run_id}/results', headers=HEADERS).json()
    assert [stage['task_type'] for stage in results['stages']][0] == 'AI_RESEARCH_PLAN' and len(results['stages']) == 7
    assert all(stage['invocation_status'] == 'SUCCEEDED' and stage['output']['findings'][0]['classification'] == 'FACT' for stage in results['stages'])

    usage = client.get('/api/v1/ai/usage', params={'research_run_id': run_id}, headers=HEADERS).json()
    assert usage['invocations'] == 7 and usage['by_status']['SUCCEEDED'] == 7 and usage['needs_reconciliation'] == 7
    assert Decimal(usage['confirmed_cost']) == 0 and Decimal(usage['calculated_cost']) > 0 and Decimal(usage['held_amount']) > 0
    item = usage['items'][0]
    settle = client.post(f"/api/v1/budgets/reservations/{item['reservation_id']}/settle", json={'actual_amount': '0.000004', 'reason': 'Provider invoice line'}, headers=key())
    assert settle.status_code == 200, settle.text
    after = client.get('/api/v1/ai/usage', params={'research_run_id': run_id}, headers=HEADERS).json()
    assert after['needs_reconciliation'] == 6 and Decimal(after['confirmed_cost']) == Decimal('0.000004')

    promoted = client.post(f'/api/v1/ai/research/{run_id}/promote', json={'title': 'Invoicing helper for small shops', 'business_model': 'SAAS'}, headers=key())
    assert promoted.status_code == 201, promoted.text
    assert promoted.json()['evidence_count'] == 1
    assert client.post(f'/api/v1/ai/research/{run_id}/promote', json={'title': 'Again', 'business_model': 'SAAS'}, headers=key()).status_code == 409
    with factory() as db:
        opportunity = db.get(Opportunity, UUID(promoted.json()['opportunity_id']))
        assert opportunity.status == 'DRAFT' and opportunity.data_origin == 'AI_RESEARCH' and opportunity.score is None
        assert opportunity.description.startswith('AI-generated research draft')
        evidence = db.scalars(select(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity.id)).all()
        assert [row.verification_status for row in evidence] == ['VERIFIED']


def test_concurrent_workers_dispatch_once_and_crash_keeps_reservation(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    run_id, workflow_id, verified_id = _research(client)
    base = _start(client, factory, workflow_id, internal)
    validation = next(task for task in client.get(base + '/tasks', headers=HEADERS).json() if task['status'] == 'READY')
    _queue(client, base, validation, internal, ai)
    for _ in range(5):
        run_once(factory)
    plan = next(task for task in client.get(base + '/tasks', headers=HEADERS).json() if task['task_type'] == 'AI_RESEARCH_PLAN')
    assert plan['status'] == 'READY'
    _queue(client, base, plan, internal, ai)

    transport = FakeProviders(verified_id)
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        run_once(factory, ai_transport=transport)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(transport.calls) == 1
    assert next(task for task in client.get(base + '/tasks', headers=HEADERS).json() if task['task_type'] == 'AI_RESEARCH_PLAN')['status'] == 'SUCCEEDED'

    # Crash after DISPATCHED: the process dies before recording any outcome.
    market = next(task for task in client.get(base + '/tasks', headers=HEADERS).json() if task['task_type'] == 'AI_MARKET_RESEARCH')
    assert market['status'] == 'READY'
    _queue(client, base, market, internal, ai)
    claimed = None
    for _ in range(5):
        claimed = claim_one(factory)
        if claimed:
            break
        activate_one(factory)
    assert claimed and claimed[2] == 'AI_MARKET_RESEARCH'

    class Crash(BaseException):
        pass

    def crashing(url, hosts, headers, request, timeout):
        transport.calls.append(url)
        raise Crash()
    with pytest.raises(Crash):
        dispatch_invocation(factory, claimed[0], claimed[1], transport=crashing)
    with factory.begin() as db:
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.execution_id == claimed[0]))
        assert invocation.status == 'DISPATCHED'
        db.execute(update(TaskExecution).where(TaskExecution.id == claimed[0]).values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    reservation_id = invocation.reservation_id
    assert client.post(f'/api/v1/budgets/reservations/{reservation_id}/release', json={'actual_amount': '0', 'reason': 'Too early'}, headers=key()).status_code == 409
    assert recover_one(factory)
    calls = len(transport.calls)
    for _ in range(3):
        run_once(factory, ai_transport=transport)
    assert len(transport.calls) == calls  # never automatically redispatched
    with factory() as db:
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.execution_id == claimed[0]))
        assert invocation.status == 'USAGE_UNKNOWN' and invocation.error_code == 'LEASE_EXPIRED'
        assert db.get(BudgetReservation, reservation_id).status in {'ACTIVE', 'EXPIRED'}
        assert db.get(WorkflowTask, UUID(market['id'])).status == 'FAILED'
    usage = client.get('/api/v1/ai/usage', params={'research_run_id': run_id}, headers=HEADERS).json()
    assert usage['by_status']['USAGE_UNKNOWN'] == 1 and usage['needs_reconciliation'] == 2
    released = client.post(f'/api/v1/budgets/reservations/{reservation_id}/release', json={'actual_amount': '0', 'reason': 'Provider shows no charge'}, headers=key())
    assert released.status_code == 200, released.text


def test_connection_test_is_consent_gated_and_records_outcome(pg, monkeypatch):
    client, _ = pg
    _, ai = _policies(client)
    created = client.post('/api/v1/ai/providers', json={'name': f'Conn {uuid4().hex[:8]}', 'kind': 'ANTHROPIC', 'default_model': 'claude-test', 'api_key': 'conn-secret'}, headers=key()).json()
    seen = []

    def fake(url, hosts, headers, timeout):
        seen.append((url, hosts, headers))
        return 200, {'data': [{'id': 'claude-test'}]}
    monkeypatch.setattr(provider_routes, 'connection_transport', fake)
    if client.get('/api/v1/ai/control', headers=HEADERS).json()['enabled']:
        assert client.post('/api/v1/ai/control/disable', headers=key()).status_code == 200
    assert client.post(f"/api/v1/ai/providers/{created['id']}/connection-test", headers=key()).status_code == 403
    assert not seen
    _enable_consent(client, ai)
    request_key = key()
    result = client.post(f"/api/v1/ai/providers/{created['id']}/connection-test", headers=request_key)
    assert result.status_code == 200 and result.json()['status'] == 'OK' and result.json()['model_listed'] is True
    assert client.post(f"/api/v1/ai/providers/{created['id']}/connection-test", headers=request_key).json() == result.json()
    assert seen == [('https://api.anthropic.com/v1/models', {'api.anthropic.com'}, {'x-api-key': 'conn-secret', 'anthropic-version': '2023-06-01'})]
    monkeypatch.setattr(provider_routes, 'connection_transport', lambda *args: (401, {'error': 'bad key'}))
    assert client.post(f"/api/v1/ai/providers/{created['id']}/connection-test", headers=key()).json()['status'] == 'AUTH_FAILED'
    listed = next(item for item in client.get('/api/v1/ai/providers', params={'limit': 100}, headers=HEADERS).json() if item['id'] == created['id'])
    assert listed['last_check_status'] == 'AUTH_FAILED' and 'conn-secret' not in json.dumps(listed)
    custom = client.post('/api/v1/ai/providers', json={'name': f'Compat {uuid4().hex[:8]}', 'kind': 'OPENAI_COMPATIBLE', 'base_url': 'https://llm.example.com/v1', 'default_model': 'm', 'api_key': 'x'}, headers=key()).json()
    assert custom['adapter_verified'] is False
    assert client.post(f"/api/v1/ai/providers/{custom['id']}/connection-test", headers=key()).status_code == 403


def _auto_run_approval(client, base, internal, ai):
    prepared = client.get(base + '/auto-run-action', params={'ai_policy_id': ai, 'internal_policy_id': internal}, headers=HEADERS)
    assert prepared.status_code == 200, prepared.text
    return prepared.json(), _approve(client, prepared.json()['action'])


def _drain(factory, transport, rounds=60):
    for _ in range(rounds):
        if not run_once(factory, ai_transport=transport):
            break


def test_one_auto_run_approval_runs_the_whole_pipeline_in_order(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    run_id, workflow_id, verified_id = _research(client)
    base = _start(client, factory, workflow_id, internal)
    prepared, approval_id = _auto_run_approval(client, base, internal, ai)
    assert prepared['summary']['task_count'] == 8 and prepared['summary']['ai_task_count'] == 7 and prepared['summary']['max_cost_usd'] == '2.000000'
    started = client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key())
    assert started.status_code == 201, started.text
    # The one approval is consumed; it cannot start a second auto-run.
    again = client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key())
    assert again.status_code == 403
    transport = FakeProviders(verified_id)
    _drain(factory, transport)
    tasks = client.get(base + '/tasks', headers=HEADERS).json()
    assert all(task['status'] == 'SUCCEEDED' for task in tasks), [(t['task_type'], t['status']) for t in tasks]
    assert client.get(base, headers=HEADERS).json()['status'] == 'COMPLETED'
    assert len(transport.calls) == 7
    state = client.get(base + '/auto-run', headers=HEADERS).json()
    assert state['status'] == 'COMPLETED' and state['id'] == started.json()['id']
    with factory() as db:
        rows = db.scalars(select(TaskExecution).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id).where(WorkflowTask.workflow_id == UUID(workflow_id))).all()
        assert len(rows) == 8 and all(row.auto_run_id == UUID(state['id']) and row.authorization_id is None for row in rows)
        assert db.scalar(select(func.count()).select_from(BudgetReservation).join(AIInvocation, AIInvocation.reservation_id == BudgetReservation.id)
                         .where(AIInvocation.research_run_id == UUID(run_id))) == 7
    results = client.get(f'/api/v1/ai/research/{run_id}/results', headers=HEADERS).json()
    assert len(results['stages']) == 7


def test_auto_run_stops_when_the_approved_plan_changes(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    run_id, workflow_id, verified_id = _research(client)
    base = _start(client, factory, workflow_id, internal)
    _, approval_id = _auto_run_approval(client, base, internal, ai)
    assert client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key()).status_code == 201
    # A source added after the approval changes the plan: nothing more may be queued under it.
    assert client.post(f'/api/v1/ai/research/{run_id}/sources', json={'source_name': 'Late', 'excerpt': 'Added after approval'}, headers=key()).status_code == 201
    transport = FakeProviders(verified_id)
    _drain(factory, transport)
    state = client.get(base + '/auto-run', headers=HEADERS).json()
    assert state['status'] == 'STOPPED' and 'changed' in state['stop_reason']
    assert transport.calls == []
    tasks = {task['task_type']: task['status'] for task in client.get(base + '/tasks', headers=HEADERS).json()}
    assert tasks['VALIDATE_RESEARCH_DRAFT'] == 'READY' and tasks['AI_RESEARCH_PLAN'] == 'BLOCKED'


def test_auto_run_requires_sources_and_can_be_stopped_by_owner(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    run = client.post('/api/v1/ai/research', json={'objective': 'No sources yet', 'target_market': 'VN', 'max_cost_usd': '1'}, headers=key()).json()
    workflow = client.post(f"/api/v1/ai/research/{run['id']}/workflow", json={'name': f'No source {uuid4().hex[:6]}'}, headers=key()).json()
    assert client.post(f"/api/v1/ai/research/{run['id']}/pipeline", json={'confirm_no_execution': True}, headers=key()).status_code == 201
    base = _start(client, factory, workflow['id'], internal)
    missing = client.get(base + '/auto-run-action', params={'ai_policy_id': ai, 'internal_policy_id': internal}, headers=HEADERS)
    assert missing.status_code == 409 and 'source' in missing.json()['detail']
    # Wrong policy pairing is denied.
    assert client.get(base + '/auto-run-action', params={'ai_policy_id': internal, 'internal_policy_id': internal}, headers=HEADERS).status_code == 409
    source = client.post(f"/api/v1/ai/research/{run['id']}/sources", json={'source_name': 'Owner note', 'excerpt': 'Shops want invoices.'}, headers=key()).json()
    _, approval_id = _auto_run_approval(client, base, internal, ai)
    assert client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key()).status_code == 201
    stopped = client.post(base + '/auto-run/stop', headers=key())
    assert stopped.status_code == 200 and stopped.json()['status'] == 'STOPPED'
    assert client.post(base + '/auto-run/stop', headers=key()).status_code == 409
    transport = FakeProviders(source['id'])
    _drain(factory, transport)
    assert transport.calls == []
    assert {task['status'] for task in client.get(base + '/tasks', headers=HEADERS).json()} == {'READY', 'BLOCKED'}


def test_owner_stop_lets_a_queued_step_finish_but_queues_nothing_more(pg):
    from app.orchestration.auto_run import auto_queue_one
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _configure_agents(client)
    _, workflow_id, verified_id = _research(client)
    base = _start(client, factory, workflow_id, internal)
    _, approval_id = _auto_run_approval(client, base, internal, ai)
    assert client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key()).status_code == 201
    assert auto_queue_one(factory)  # Queues the validation step only.
    assert client.post(base + '/auto-run/stop', headers=key()).status_code == 200
    transport = FakeProviders(verified_id)
    _drain(factory, transport)
    tasks = {task['task_type']: task['status'] for task in client.get(base + '/tasks', headers=HEADERS).json()}
    assert tasks['VALIDATE_RESEARCH_DRAFT'] == 'SUCCEEDED' and tasks['AI_RESEARCH_PLAN'] == 'READY'
    assert client.get(base, headers=HEADERS).json()['status'] == 'RUNNING' and transport.calls == []
