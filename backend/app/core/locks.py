"""A request-scoped lock that survives the rollback done before a network call."""
import hashlib
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import text


@contextmanager
def paid_call_lock(db, actor: str, key: str):
    """Serialize requests with the same Idempotency-Key across paid outbound calls.

    Uses a PostgreSQL session advisory lock on a dedicated connection, so releasing the request
    transaction before the network call does not release the lock. A concurrent duplicate gets 409
    instead of repeating paid calls. No-op on other databases (tests).
    """
    bind = db.get_bind()
    if bind.dialect.name != 'postgresql':
        yield
        return
    lock_id = int.from_bytes(hashlib.sha256(f'paid:{actor}:{key}'.encode()).digest()[:8], 'big', signed=True)
    connection = bind.connect()
    try:
        if not connection.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': lock_id}).scalar():
            raise HTTPException(status_code=409, detail='The same request is already running; wait for it to finish')
        try:
            yield
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': lock_id})
            connection.commit()
    finally:
        connection.close()
