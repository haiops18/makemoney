from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration.retry import is_retryable, retry_after


def test_retry_is_bounded_exponential_and_only_transient():
    now = datetime.now(UTC)
    assert retry_after(now, 0, 3, jitter_seconds=0) == now + timedelta(seconds=1)
    assert retry_after(now, 1, 3, jitter_seconds=0) == now + timedelta(seconds=2)
    assert retry_after(now, 3, 3) is None
    assert is_retryable(TimeoutError())
    assert not is_retryable(ValueError())
    assert not is_retryable(RuntimeError())
    with pytest.raises(ValueError):
        retry_after(now, 4, 3)
    with pytest.raises(ValueError):
        retry_after(now.replace(tzinfo=None), 0, 1)
