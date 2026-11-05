"""Authenticated encryption for provider credentials; key comes from deployment secrets."""
import hashlib
import hmac
import json
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CredentialUnavailable(ValueError):
    pass


def _key() -> bytes:
    value = get_settings().ai_credentials_key
    if value is None:
        raise CredentialUnavailable('AI credential encryption key is not configured')
    key = value.get_secret_value().encode('ascii', errors='strict')
    try:
        Fernet(key)
    except (ValueError, TypeError):
        raise CredentialUnavailable('AI credential encryption key is invalid') from None
    return key


def encrypt_credential(provider_id: UUID, secret: str) -> str:
    if not secret or len(secret) > 4096:
        raise CredentialUnavailable('Invalid provider credential')
    payload = json.dumps({'provider_id': str(provider_id), 'secret': secret}, separators=(',', ':')).encode()
    return Fernet(_key()).encrypt(payload).decode('ascii')


def decrypt_credential(provider_id: UUID, ciphertext: str) -> str:
    try:
        payload = json.loads(Fernet(_key()).decrypt(ciphertext.encode('ascii')))
        if payload['provider_id'] != str(provider_id) or not isinstance(payload['secret'], str):
            raise ValueError
        return payload['secret']
    except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
        raise CredentialUnavailable('Credential could not be verified') from None


def credential_digest(secret: str) -> str:
    # Domain separation ensures a digest of a credential is not a Fernet token.
    return hmac.new(_key(), b'provider-idempotency-v1\0' + secret.encode(), hashlib.sha256).hexdigest()
