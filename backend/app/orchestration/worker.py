"""PostgreSQL-backed worker for explicitly approved, pure internal handlers.

Transactions only claim/finalize work. The handler runs outside a transaction;
lease tokens fence late workers. Cancellation discards in-flight results. Automatic
recovery never reuses a consumed approval: Owner must approve a retry again.
"""
from datetime import UTC, datetime, timedelta
from queue import Empty, Queue
from threading import Event, Thread
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals.service import is_expired
from app.db.models import ActionAuthorization, ApprovalRequest, AuditEvent, TaskDependency, TaskExecution, Workflow, WorkflowEvent, WorkflowTask
from app.orchestration.gate import GateDenied, task_action
from app.orchestration.handlers import dispatch
from app.orchestration.retry import is_retryable, retry_after
from app.orchestration.state import TASK_TRANSITIONS, WORKFLOW_TRANSITIONS, validate_transition


def _transition(db: Session, workflow: Workflow, task: WorkflowTask | None, target: str, actor: str, kind: str) -> None:
    obj = task or workflow
    old = obj.status
    validate_transition(TASK_TRANSITIONS if task else WORKFLOW_TRANSITIONS, old, target)
    obj.status = target
    db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id if task else None, event_type=kind, previous_status=old, new_status=target, actor=actor, metadata_json={}))
    db.add(AuditEvent(actor=actor, action='workflow.task_transition' if task else 'workflow.transition', entity_type='workflow_task' if task else 'workflow', entity_id=obj.id, detail={'workflow_id': str(workflow.id), 'previous_status': old, 'new_status': target}))


def _refresh_dependencies(db: Session, workflow: Workflow) -> None:
    tasks = list(db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.id).with_for_update()))
    dependencies = list(db.scalars(select(TaskDependency).where(TaskDependency.workflow_id == workflow.id)))
    by_id = {task.id: task for task in tasks}
    for task in tasks:
        if task.status not in {'PENDING', 'BLOCKED'}:
            continue
        parents = [by_id.get(dep.depends_on_task_id) for dep in dependencies if dep.task_id == task.id]
        ready = all(parent is not None and parent.status == 'SUCCEEDED' for parent in parents)
        target = 'READY' if ready else 'BLOCKED'
        if target != task.status:
            _transition(db, workflow, task, target, 'internal-worker', 'DEPENDENCIES_EVALUATED')
    if workflow.status == 'RUNNING' and tasks and all(task.status == 'SUCCEEDED' for task in tasks):
        _transition(db, workflow, None, 'COMPLETED', 'internal-worker', 'WORKFLOW_COMPLETED')
        workflow.completed_at = datetime.now(UTC)
    elif workflow.status == 'RUNNING' and any(task.status == 'FAILED' for task in tasks):
        _transition(db, workflow, None, 'FAILED', 'internal-worker', 'WORKFLOW_FAILED')
        workflow.completed_at = datetime.now(UTC)


def activate_one(factory: sessionmaker) -> bool:
    with factory.begin() as db:
        workflow = db.scalar(select(Workflow).where(Workflow.status == 'QUEUED').order_by(Workflow.updated_at, Workflow.id).with_for_update(skip_locked=True).limit(1))
        if workflow is None:
            return False
        _transition(db, workflow, None, 'RUNNING', 'internal-worker', 'WORKFLOW_STARTED')
        if workflow.started_at is None:
            workflow.started_at = datetime.now(UTC)
        _refresh_dependencies(db, workflow)
    return True


def _lock_execution(db: Session, execution_id: UUID, *, skip_locked: bool = True) -> tuple[Workflow, WorkflowTask, TaskExecution] | None:
    pair = db.execute(select(WorkflowTask.workflow_id, TaskExecution.task_id).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id).where(TaskExecution.id == execution_id)).first()
    if pair is None:
        return None
    workflow = db.scalar(select(Workflow).where(Workflow.id == pair.workflow_id).with_for_update(skip_locked=skip_locked))
    if workflow is None:
        return None
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.id == pair.task_id).with_for_update(skip_locked=skip_locked))
    execution = db.scalar(select(TaskExecution).where(TaskExecution.id == execution_id).with_for_update(skip_locked=skip_locked))
    if task is None or execution is None:
        return None
    return workflow, task, execution


def _fail_execution(db: Session, workflow: Workflow, task: WorkflowTask, execution: TaskExecution, code: str, transient: bool) -> None:
    now = datetime.now(UTC)
    execution.status = 'TIMED_OUT' if transient else 'FAILED'
    execution.completed_at = now
    execution.error_code = code
    execution.error_message = 'Task could not complete; review its controls and input.'
    deadline = retry_after(now, task.retry_count, task.max_retries) if transient else None
    target = 'RETRY_WAIT' if deadline else 'FAILED'
    task.next_retry_at = deadline
    task.finished_at = now if target == 'FAILED' else None
    db.add(AuditEvent(actor='internal-worker', action='workflow.execution_failed', entity_type='workflow_task', entity_id=task.id, detail={'execution_id': str(execution.id), 'error_code': code, 'retry_scheduled': deadline is not None}))
    _transition(db, workflow, task, target, 'internal-worker', 'TASK_FAILED')
    _refresh_dependencies(db, workflow)


def claim_one(factory: sessionmaker) -> tuple[UUID, UUID, str, dict, int] | None:
    with factory.begin() as db:
        candidates = list(db.scalars(select(TaskExecution.id).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id)
                                     .join(Workflow, Workflow.id == WorkflowTask.workflow_id)
                                     .where(TaskExecution.status == 'QUEUED', Workflow.status == 'RUNNING')
                                     .order_by(TaskExecution.started_at, TaskExecution.id).limit(100)))
        for execution_id in candidates:
            locked = _lock_execution(db, execution_id)
            if locked is None:
                continue
            workflow, task, execution = locked
            if execution.status != 'QUEUED' or workflow.status != 'RUNNING' or task.status != 'RUNNING':
                continue
            try:
                if not execution.policy_id or not execution.authorization_id or not execution.action_hash or execution.input_snapshot_json is None:
                    raise GateDenied('Execution authorization is incomplete')
                action, digest = task_action(db, workflow.id, task.id, execution.policy_id)
                auth = db.scalar(select(ActionAuthorization).where(ActionAuthorization.id == execution.authorization_id).with_for_update())
                approval = db.get(ApprovalRequest, auth.approval_id) if auth else None
                unfinished = db.scalar(select(func.count()).select_from(TaskDependency).join(WorkflowTask, WorkflowTask.id == TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task.id, WorkflowTask.status != 'SUCCEEDED')) or 0
                if (not auth or not approval or auth.status != 'CONSUMED' or approval.status != 'CONSUMED'
                    or is_expired(auth.expires_at) or is_expired(approval.expires_at) or unfinished
                    or digest != execution.action_hash or digest != auth.action_hash or digest != approval.action_hash
                    or action['action_payload']['handler_input'] != execution.input_snapshot_json):
                    raise GateDenied('Execution authorization or input changed')
            except GateDenied:
                _fail_execution(db, workflow, task, execution, 'AUTHORIZATION_INVALID', False)
                return None
            execution.status = 'RUNNING'
            execution.started_at = datetime.now(UTC)
            execution.lease_expires_at = execution.started_at + timedelta(seconds=task.timeout_seconds + 5)
            execution.lease_token = uuid4()
            task.started_at = execution.started_at
            db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='EXECUTION_CLAIMED', actor='internal-worker', metadata_json={'execution_id': str(execution.id), 'attempt': execution.attempt_number}))
            db.add(AuditEvent(actor='internal-worker', action='workflow.execution_claimed', entity_type='workflow_task', entity_id=task.id, detail={'execution_id': str(execution.id)}))
            return execution.id, execution.lease_token, task.task_type, execution.input_snapshot_json, task.timeout_seconds
    return None


def _invoke(task_type: str, payload: dict, timeout: int) -> tuple[dict | None, BaseException | None]:
    results: Queue = Queue(maxsize=1)
    def run() -> None:
        try:
            results.put((dispatch(task_type, payload).model_dump(mode='json'), None))
        except Exception as exc:
            results.put((None, exc))
    Thread(target=run, daemon=True).start()
    try:
        return results.get(timeout=timeout)
    except Empty:
        return None, TimeoutError('Internal handler timed out')


def finalize(factory: sessionmaker, execution_id: UUID, token: UUID, result: dict | None, error: BaseException | None) -> bool:
    with factory.begin() as db:
        locked = _lock_execution(db, execution_id, skip_locked=False)
        if locked is None:
            return False
        workflow, task, execution = locked
        if (execution.status != 'RUNNING' or execution.lease_token != token or task.status != 'RUNNING'
            or execution.lease_expires_at is None or is_expired(execution.lease_expires_at)):
            return False
        if workflow.status == 'CANCELLED':
            execution.status = 'CANCELLED'
            execution.completed_at = datetime.now(UTC)
            task.finished_at = execution.completed_at
            _transition(db, workflow, task, 'CANCELLED', 'internal-worker', 'TASK_CANCELLED')
            return True
        if workflow.status not in {'RUNNING', 'PAUSED', 'QUEUED'}:
            _fail_execution(db, workflow, task, execution, 'WORKFLOW_STATE_INVALID', False)
            return True
        if error is not None:
            _fail_execution(db, workflow, task, execution, 'HANDLER_TIMEOUT' if is_retryable(error) else 'HANDLER_FAILED', is_retryable(error))
            return True
        if not isinstance(result, dict) or result.get('status') not in {'COMPLETE', 'INCOMPLETE'} or not isinstance(result.get('missing'), list):
            _fail_execution(db, workflow, task, execution, 'OUTPUT_INVALID', False)
            return True
        if result['status'] == 'INCOMPLETE':
            execution.output_json = result
            _fail_execution(db, workflow, task, execution, 'VALIDATION_INCOMPLETE', False)
            return True
        execution.status = 'SUCCEEDED'
        execution.output_json = result
        execution.completed_at = datetime.now(UTC)
        task.finished_at = execution.completed_at
        _transition(db, workflow, task, 'SUCCEEDED', 'internal-worker', 'TASK_SUCCEEDED')
        _refresh_dependencies(db, workflow)
    return True


def recover_one(factory: sessionmaker) -> bool:
    with factory.begin() as db:
        candidates = list(db.scalars(select(TaskExecution.id).where(TaskExecution.status == 'RUNNING', TaskExecution.lease_expires_at <= datetime.now(UTC)).order_by(TaskExecution.lease_expires_at).limit(100)))
        for execution_id in candidates:
            locked = _lock_execution(db, execution_id)
            if locked is None:
                continue
            workflow, task, execution = locked
            if execution.status != 'RUNNING' or execution.lease_expires_at is None or not is_expired(execution.lease_expires_at) or task.status != 'RUNNING':
                continue
            execution.status = 'ABANDONED'
            execution.completed_at = datetime.now(UTC)
            execution.error_code = 'LEASE_EXPIRED'
            execution.error_message = 'Worker lease expired; a fresh Owner approval is required for any retry.'
            db.add(AuditEvent(actor='internal-worker', action='workflow.execution_abandoned', entity_type='workflow_task', entity_id=task.id, detail={'execution_id': str(execution.id), 'error_code': 'LEASE_EXPIRED'}))
            if workflow.status == 'CANCELLED':
                task.finished_at = execution.completed_at
                _transition(db, workflow, task, 'CANCELLED', 'internal-worker', 'TASK_CANCELLED')
            else:
                deadline = retry_after(execution.completed_at, task.retry_count, task.max_retries)
                task.next_retry_at = deadline
                if deadline is None:
                    task.finished_at = execution.completed_at
                _transition(db, workflow, task, 'RETRY_WAIT' if deadline else 'FAILED', 'internal-worker', 'LEASE_EXPIRED')
                _refresh_dependencies(db, workflow)
            return True
    return False


def run_once(factory: sessionmaker) -> bool:
    recovered = recover_one(factory)
    activated = activate_one(factory)
    claimed = claim_one(factory)
    if claimed:
        execution_id, token, task_type, payload, timeout = claimed
        result, error = _invoke(task_type, payload, timeout)
        finalize(factory, execution_id, token, result, error)
    return recovered or activated or claimed is not None


def main() -> None:
    import logging
    import signal
    from app.db.session import SessionLocal
    from app.core.config import get_settings

    get_settings().validate_deployment()
    stopping = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            if not run_once(SessionLocal):
                stopping.wait(2)
        except Exception:
            logging.exception('Internal worker iteration failed; no external execution attempted')
            stopping.wait(2)


if __name__ == '__main__':
    main()
