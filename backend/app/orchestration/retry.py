"""Bounded retry decisions for pure internal handlers."""
from datetime import datetime, timedelta
from random import SystemRandom

_random = SystemRandom()


def retry_after(now: datetime, attempts_used: int, max_retries: int, *, jitter_seconds: float | None = None) -> datetime | None:
    if now.tzinfo is None:
        raise ValueError('Retry timestamps must be timezone-aware')
    if not 0 <= attempts_used <= max_retries <= 10:
        raise ValueError('Invalid retry bounds')
    if attempts_used == max_retries:
        return None
    base = min(300, 2 ** attempts_used)
    jitter = _random.uniform(0, base / 4) if jitter_seconds is None else jitter_seconds
    if not 0 <= jitter <= base / 4:
        raise ValueError('Jitter exceeds the permitted bound')
    return now + timedelta(seconds=base + jitter)


def is_retryable(error: BaseException) -> bool:
    # Invalid inputs, policy denials and unknown exceptions require review, not
    # automatic replay. These handlers have no external or irreversible effects.
    return isinstance(error, TimeoutError)
