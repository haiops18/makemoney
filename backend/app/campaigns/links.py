"""Affiliate link rules. Links are stored and composed only; the server never opens them.

The Owner sets, per program, which hosts a link may use and which query keys the app may
add. The original URL is kept byte-for-byte; tracking parameters are only appended.
"""
import re
from urllib.parse import urlencode, urlsplit

HOST = re.compile(r'^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')
PARAM_KEY = re.compile(r'^[A-Za-z0-9_]{1,50}$')
PARAM_VALUE = re.compile(r'^[A-Za-z0-9_.\-]{1,100}$')
MAX_URL = 2048
MAX_PARAMS = 10


class LinkRuleError(ValueError):
    pass


def normalize_hosts(hosts: list[str]) -> list[str]:
    cleaned = sorted({host.strip().lower().rstrip('.') for host in hosts})
    if not 1 <= len(cleaned) <= 10 or not all(HOST.match(host) for host in cleaned):
        raise LinkRuleError('Link hosts must be 1-10 plain host names, for example s.shopee.vn')
    return cleaned


def normalize_keys(keys: list[str]) -> list[str]:
    cleaned = sorted({key.strip() for key in keys})
    if len(cleaned) > MAX_PARAMS or not all(PARAM_KEY.match(key) for key in cleaned):
        raise LinkRuleError('Tracking keys must be at most 10 names of letters, digits or underscores')
    return cleaned


def safe_url(value: str, *, https_only: bool = False) -> str:
    """Syntax check only. Rejects credentials, control characters and non-web schemes."""
    if len(value) > MAX_URL or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise LinkRuleError('Invalid URL')
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        raise LinkRuleError('Invalid URL') from None
    schemes = {'https'} if https_only else {'http', 'https'}
    if parts.scheme not in schemes or not parts.hostname or parts.username or parts.password:
        raise LinkRuleError('Affiliate links must be https without credentials' if https_only else 'Invalid URL')
    return value


def host_allowed(host: str, allowed: list[str]) -> bool:
    host = host.lower().rstrip('.')
    return any(host == item or host.endswith('.' + item) for item in allowed)


def compose(original_url: str, link_hosts: list[str], allowed_keys: list[str], params: dict[str, str]) -> str:
    safe_url(original_url, https_only=True)
    parts = urlsplit(original_url)
    if not host_allowed(parts.hostname or '', link_hosts):
        raise LinkRuleError('The link host is not allowed for this affiliate program')
    if len(params) > MAX_PARAMS:
        raise LinkRuleError('Too many tracking parameters')
    existing = {pair.split('=', 1)[0] for pair in parts.query.split('&') if pair}
    for key, value in params.items():
        if key not in allowed_keys:
            raise LinkRuleError(f'Tracking key {key} is not allowed for this program')
        if key in existing:
            raise LinkRuleError(f'Tracking key {key} is already in the original link')
        if not PARAM_VALUE.match(value):
            raise LinkRuleError('Tracking values may contain only letters, digits, dot, dash or underscore')
    if not params:
        return original_url
    base, hash_mark, fragment = original_url.partition('#')
    separator = '' if base.endswith(('?', '&')) else ('&' if '?' in base else '?')
    final = base + separator + urlencode(sorted(params.items())) + hash_mark + fragment
    if len(final) > MAX_URL:
        raise LinkRuleError('The final link is too long')
    return final
