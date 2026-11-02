import pytest
from pydantic import ValidationError

from app.orchestration.handlers import dispatch


def test_registry_is_closed_and_validation_does_not_invent_evidence():
    assert dispatch('VALIDATE_OPPORTUNITY', {'title': 'Test', 'business_model': 'MICRO_SAAS'}).missing == ['target_market']
    assert dispatch('VALIDATE_EVIDENCE', {'evidence_count': 2, 'verified_count': 0}).status == 'INCOMPLETE'
    assert dispatch('VALIDATE_EVIDENCE', {'evidence_count': 2, 'verified_count': 1}).status == 'COMPLETE'
    with pytest.raises(ValueError):
        dispatch('SHELL', {'command': 'anything'})
    with pytest.raises(ValueError):
        dispatch('VALIDATE_EVIDENCE', {'evidence_count': 1, 'verified_count': 2})
    with pytest.raises(ValidationError):
        dispatch('VALIDATE_OPPORTUNITY', {'title': 'Test', 'business_model': 'MICRO_SAAS', 'command': 'anything'})
