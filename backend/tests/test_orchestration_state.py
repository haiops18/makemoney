from uuid import uuid4

import pytest

from app.orchestration.state import TASK_TRANSITIONS, WORKFLOW_TRANSITIONS, validate_dependencies, validate_transition


def test_terminal_and_invalid_transitions_fail_closed():
    validate_transition(WORKFLOW_TRANSITIONS, 'DRAFT', 'PENDING_APPROVAL')
    validate_transition(TASK_TRANSITIONS, 'READY', 'RUNNING')
    for current, target in [('DRAFT', 'RUNNING'), ('COMPLETED', 'QUEUED'), ('CANCELLED', 'RUNNING'), ('UNKNOWN', 'DRAFT')]:
        with pytest.raises(ValueError):
            validate_transition(WORKFLOW_TRANSITIONS, current, target)
    with pytest.raises(ValueError):
        validate_transition(TASK_TRANSITIONS, 'CANCELLED', 'READY')


def test_dependency_graph_rejects_cycles_self_and_missing_nodes():
    a, b, c, missing = (uuid4() for _ in range(4))
    validate_dependencies({a: [], b: [a], c: [a, b]})
    for graph in ({a: [a]}, {a: [missing]}, {a: [b], b: [c], c: [a]}):
        with pytest.raises(ValueError):
            validate_dependencies(graph)
