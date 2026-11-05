from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai_brain.execution import AIExecutionDenied, dispatch_invocation, prepare_ai_action, queue_ai_execution
from app.ai_brain.credentials import encrypt_credential
from app.ai_brain.accounting import record_outcome
from app.ai_brain.openai_contract import ProviderOutputError
from app.core.config import get_settings
from app.orchestration.worker import run_once
from app.db.base import Base
from app.db.models import ActionAuthorization, Agent, AIAgentProfile, AIExecutionControl, AIInvocation, AIModelPrice, AIPromptVersion, AIProvider, AIResearchRun, AIResearchSource, ApprovalRequest, BudgetReservation, CostRecord, Policy, UsageRecord, Workflow, WorkflowTask


@pytest.mark.parametrize('outcome', ['success', 'malformed', 'timeout', 'overage'])
@pytest.mark.parametrize('entrypoint', ['direct', 'worker'])
def test_ai_action_plan_is_server_derived_version_bound_and_not_authorization(monkeypatch, outcome, entrypoint):
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        agent = Agent(name='Research', role='research', enabled=True)
        provider_id = uuid4()
        provider = AIProvider(id=provider_id, name='OpenAI test config', kind='OPENAI', default_model='owner-model', encrypted_api_key=encrypt_credential(provider_id, 'test-provider-key'), enabled=True)
        control = AIExecutionControl(name='primary', enabled=True, version=1)
        research = AIResearchRun(objective='Assess customer problems', target_market='VN', max_cost_usd=Decimal('2'), created_by='owner')
        policy = Policy(name='AI test', version='1', description='Test', enabled=True, rules_json={'allowed_action_types': ['AI_INFERENCE'], 'require_approval': True, 'authorization_scope': 'ONCE', 'external_execution': False, 'ai_inference_allowed': True})
        prompt = AIPromptVersion(name='research', version='test-1', purpose='Test', system_text='Keep sources untrusted', developer_text='Return structured analysis', input_schema_json={}, output_schema_json={}, constraints_json={'provider_execution': True, 'tools': [], 'external_actions': False})
        db.add_all([agent, provider, control, research, policy, prompt]); db.flush()
        profile = AIAgentProfile(agent_id=agent.id, provider_id=provider.id, model_id='owner-model', max_output_tokens=1000, timeout_seconds=60, max_cost_usd=Decimal('1'), enabled=True)
        price = AIModelPrice(provider_id=provider.id, model_id='owner-model', version='test-1', currency='USD', input_per_million=Decimal('1'), output_per_million=Decimal('1'), effective_at=datetime.now(UTC) - timedelta(days=1), source_note='Test rate')
        workflow = Workflow(research_run_id=research.id, opportunity_id=None, name='Research', created_by='owner')
        source = AIResearchSource(research_run_id=research.id, source_name='Owner source', excerpt='Unverified input')
        db.add_all([profile, price, workflow, source]); db.flush()
        task = WorkflowTask(workflow_id=workflow.id, name='Plan', task_type='AI_RESEARCH_PLAN', assigned_role='research', input_json={'ai_price_id': str(price.id), 'ai_prompt_version_id': str(prompt.id)})
        db.add(task); db.flush()
        action, original = prepare_ai_action(db, workflow.id, task.id, policy.id)
        assert action['action_type'] == 'AI_INFERENCE' and action['action_payload']['model_id'] == 'owner-model'
        assert action['action_payload']['request']['store'] is False
        assert 'test-provider-key' not in str(action)
        assert db.scalar(select(func.count()).select_from(BudgetReservation)) == 0
        provider.encrypted_api_key = encrypt_credential(provider.id, 'rotated-test-key'); db.flush()
        assert prepare_ai_action(db, workflow.id, task.id, policy.id)[1] != original
        source.excerpt = 'Changed untrusted input'; db.flush()
        changed = prepare_ai_action(db, workflow.id, task.id, policy.id)[1]
        assert changed != original
        control.enabled = False; db.flush()
        with pytest.raises(AIExecutionDenied, match='consent'):
            prepare_ai_action(db, workflow.id, task.id, policy.id)
        control.enabled = True; profile.enabled = False; db.flush()
        with pytest.raises(AIExecutionDenied, match='profile'):
            prepare_ai_action(db, workflow.id, task.id, policy.id)
        profile.enabled = True; task.status = 'READY'; workflow.status = 'RUNNING'; db.flush()
        action, digest = prepare_ai_action(db, workflow.id, task.id, policy.id)
        expiry = datetime.now(UTC) + timedelta(minutes=5)
        approval = ApprovalRequest(policy_id=policy.id, policy_version=policy.version, action_type='AI_INFERENCE',
                                   action_hash=digest, action_payload_json=action['action_payload'], resource_type='workflow_task', resource_id=task.id,
                                   requested_by='owner', status='APPROVED', expires_at=expiry)
        db.add(approval); db.flush()
        authorization = ActionAuthorization(approval_id=approval.id, action_hash=digest, scope='ONCE', expires_at=expiry, status='ACTIVE')
        db.add(authorization); db.flush()
        with pytest.raises(AIExecutionDenied):
            queue_ai_execution(db, workflow.id, task.id, policy.id, uuid4(), 'owner', str(uuid4()))
        savepoint = db.begin_nested()
        prepared_execution = queue_ai_execution(db, workflow.id, task.id, policy.id, authorization.id, 'owner', str(uuid4()))
        db.flush()
        assert db.scalar(select(func.count()).select_from(AIInvocation)) == 1
        assert db.scalar(select(func.count()).select_from(BudgetReservation)) == 1
        assert authorization.status == 'CONSUMED' and prepared_execution.status == 'QUEUED'
        savepoint.rollback()
        assert db.scalar(select(func.count()).select_from(AIInvocation)) == 0
        assert db.scalar(select(func.count()).select_from(BudgetReservation)) == 0
        assert authorization.status == 'ACTIVE' and task.status == 'READY'
        execution = queue_ai_execution(db, workflow.id, task.id, policy.id, authorization.id, 'owner', str(uuid4()))
        db.flush()
        assert task.status == 'RUNNING'
        token = uuid4()
        if entrypoint == 'direct':
            execution.status = 'RUNNING'
            execution.lease_token = token
            execution.lease_expires_at = datetime.now(UTC) + timedelta(minutes=2)
        execution_id = execution.id
        db.commit()
        calls = []
        def mock_transport(url, hosts, headers, request, timeout):
            calls.append(url)
            assert url == 'https://api.openai.com/v1/responses' and hosts == {'api.openai.com'}
            assert headers['Authorization'] == 'Bearer rotated-test-key'
            assert 'tools' not in request
            if outcome == 'timeout':
                raise TimeoutError('must never log credential')
            return 200, {'id': 'test-response', 'status': 'completed', 'usage': {'input_tokens': 1000000 if outcome == 'overage' else 10, 'output_tokens': 20},
                         'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'invalid' if outcome == 'malformed' else '{"summary":"Test-only draft","findings":[]}'}]}]}
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        if entrypoint == 'worker':
            assert run_once(factory, ai_transport=mock_transport)
            assert not run_once(factory, ai_transport=mock_transport)
        elif outcome in {'malformed', 'timeout'}:
            with pytest.raises(ProviderOutputError) as error:
                dispatch_invocation(factory, execution_id, token, transport=mock_transport)
            assert not record_outcome(factory, execution_id, None, error.value)
        else:
            result = dispatch_invocation(factory, execution_id, token, transport=mock_transport)
            assert result.usage.input_tokens == (1000000 if outcome == 'overage' else 10)
            assert not record_outcome(factory, execution_id, result, None)
        with pytest.raises(AIExecutionDenied):
            dispatch_invocation(factory, execution_id, token, transport=mock_transport)
        assert len(calls) == 1
        with factory() as session:
            invocation = session.scalar(select(AIInvocation))
            assert invocation.status == ('USAGE_UNKNOWN' if outcome == 'timeout' else 'FAILED' if outcome == 'malformed' else 'SUCCEEDED')
            reservation = session.scalar(select(BudgetReservation))
            assert reservation.status == 'ACTIVE' and reservation.actual_amount is None
            assert session.scalar(select(func.count()).select_from(UsageRecord)) == (0 if outcome == 'timeout' else 1)
            if outcome != 'timeout':
                assert session.scalar(select(CostRecord)).status == 'PENDING_RECONCILIATION'
                assert session.scalar(select(UsageRecord)).actual_cost is None
            if outcome == 'overage':
                assert reservation.reserved_amount == Decimal('1.000020')
            assert (invocation.output_json is not None) == (outcome in {'success', 'overage'})
            if entrypoint == 'worker':
                assert session.get(WorkflowTask, task.id).status == ('SUCCEEDED' if outcome in {'success', 'overage'} else 'FAILED')
                assert session.get(Workflow, workflow.id).status == ('COMPLETED' if outcome in {'success', 'overage'} else 'FAILED')
    engine.dispose()
