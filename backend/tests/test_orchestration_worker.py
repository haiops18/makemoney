import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from app.db.models import Opportunity, TaskExecution, Workflow, WorkflowTask
from app.db.session import get_db
from app.main import app
from app.orchestration.worker import finalize

from app.orchestration.worker import _invoke


def test_internal_handler_timeout_is_bounded(monkeypatch):
    def slow_handler(*_args):
        time.sleep(1)
    monkeypatch.setattr('app.orchestration.worker.dispatch', slow_handler)
    started = time.monotonic()
    result, error = _invoke('VALIDATE_OPPORTUNITY', {}, 0.02)
    assert result is None
    assert isinstance(error, TimeoutError)
    assert time.monotonic() - started < 0.5


def test_incomplete_validation_fails_workflow_without_affecting_another(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    opportunity = Opportunity(title='Isolation test', business_model='MICRO_SAAS', created_by='owner')
    db.add(opportunity); db.flush()
    first = Workflow(name='First', opportunity_id=opportunity.id, created_by='owner', status='RUNNING')
    second = Workflow(name='Second', opportunity_id=opportunity.id, created_by='owner', status='RUNNING')
    db.add_all([first, second]); db.flush()
    task = WorkflowTask(workflow_id=first.id, name='Validate', task_type='VALIDATE_OPPORTUNITY', assigned_role='research', status='RUNNING', input_json={})
    db.add(task); db.flush()
    token = uuid4()
    execution = TaskExecution(task_id=task.id, attempt_number=1, status='RUNNING', idempotency_key='isolation-test', lease_token=token, lease_expires_at=datetime.now(UTC) + timedelta(minutes=1))
    db.add(execution); db.commit()
    first_id, second_id, execution_id = first.id, second.id, execution.id
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False, autoflush=False)
    assert finalize(factory, execution_id, token, {'status': 'INCOMPLETE', 'missing': ['target_market']}, None)
    db.expire_all()
    assert db.get(Workflow, first_id).status == 'FAILED'
    assert db.get(Workflow, second_id).status == 'RUNNING'
    assert db.get(TaskExecution, execution_id).error_code == 'VALIDATION_INCOMPLETE'
    generator.close()
