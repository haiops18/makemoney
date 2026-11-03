"""Explicit state transitions and dependency validation for workflow orchestration."""
from collections.abc import Mapping, Iterable
from uuid import UUID

WORKFLOW_TRANSITIONS = {
    'DRAFT': frozenset({'PENDING_APPROVAL', 'CANCELLED'}),
    'PENDING_APPROVAL': frozenset({'APPROVED', 'DRAFT', 'CANCELLED'}),
    'APPROVED': frozenset({'QUEUED', 'DRAFT', 'CANCELLED'}),
    'QUEUED': frozenset({'RUNNING', 'PAUSED', 'CANCELLED'}),
    'RUNNING': frozenset({'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED'}),
    'PAUSED': frozenset({'QUEUED', 'CANCELLED'}),
    'COMPLETED': frozenset(), 'FAILED': frozenset(), 'CANCELLED': frozenset(),
}
TASK_TRANSITIONS = {
    'PENDING': frozenset({'BLOCKED', 'READY', 'CANCELLED', 'SKIPPED'}),
    'BLOCKED': frozenset({'READY', 'CANCELLED', 'SKIPPED'}),
    'READY': frozenset({'RUNNING', 'BLOCKED', 'CANCELLED'}),
    'RUNNING': frozenset({'SUCCEEDED', 'FAILED', 'RETRY_WAIT', 'CANCELLED'}),
    'RETRY_WAIT': frozenset({'READY', 'FAILED', 'CANCELLED'}),
    'FAILED': frozenset(), 'SUCCEEDED': frozenset(), 'CANCELLED': frozenset(), 'SKIPPED': frozenset(),
}


def validate_transition(matrix: Mapping[str, frozenset[str]], current: str, target: str) -> None:
    if target not in matrix.get(current, frozenset()):
        raise ValueError(f'Invalid transition: {current} -> {target}')


def validate_dependencies(graph: Mapping[UUID, Iterable[UUID]]) -> None:
    """Reject missing nodes, self-dependencies and cycles without recursion."""
    nodes = set(graph)
    remaining = {node: set(dependencies) for node, dependencies in graph.items()}
    if any(node in dependencies or not dependencies <= nodes for node, dependencies in remaining.items()):
        raise ValueError('Dependencies must refer to other tasks in the same workflow')
    while remaining:
        ready = {node for node, dependencies in remaining.items() if not dependencies}
        if not ready:
            raise ValueError('Dependency cycle detected')
        remaining = {node: dependencies - ready for node, dependencies in remaining.items() if node not in ready}
