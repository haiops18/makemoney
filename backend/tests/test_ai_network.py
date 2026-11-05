import socket

import pytest

from app.ai_brain.network import NetworkDenied, post_provider_json, resolve_public_target
from app.ai_brain import network


def addresses(*values):
    return lambda *_args, **_kwargs: [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in values]


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.1.1', '::1', 'fc00::1', '::ffff:127.0.0.1'])
def test_provider_network_denies_local_and_metadata_targets(ip):
    with pytest.raises(NetworkDenied):
        resolve_public_target('https://allowed.example/v1/responses', {'allowed.example'}, addresses(ip))


def test_provider_network_rejects_mixed_dns_redirect_shapes_and_unapproved_hosts():
    with pytest.raises(NetworkDenied):
        resolve_public_target('https://allowed.example', {'allowed.example'}, addresses('8.8.8.8', '10.0.0.1'))
    for url in ['http://allowed.example', 'https://user:key@allowed.example', 'https://allowed.example:8443', 'https://allowed.example?key=value', 'https://other.example', 'https://allowed.example./']:
        with pytest.raises(NetworkDenied):
            resolve_public_target(url, {'allowed.example'}, addresses('8.8.8.8'))
    assert resolve_public_target('https://allowed.example/v1/responses', {'allowed.example'}, addresses('8.8.8.8')) == ('allowed.example', '8.8.8.8', '/v1/responses')


def test_transport_does_not_follow_redirects_or_retry(monkeypatch):
    monkeypatch.setattr(network, 'resolve_public_target', lambda *_, **__: ('allowed.example', '8.8.8.8', '/v1'))
    calls = []
    class Connection:
        def __init__(self, host, ip, timeout): calls.append(('connect', host, ip))
        def request(self, method, path, body, headers): calls.append(('request', method, path))
        def getresponse(self): return self
        status = 302
        def read(self, _): return b'{"redirect":"https://127.0.0.1/"}'
        def close(self): calls.append(('close',))
    monkeypatch.setattr(network, '_PinnedHTTPSConnection', Connection)
    status, _ = post_provider_json('https://allowed.example/v1', {'allowed.example'}, {'Authorization': 'Bearer test-only'}, {}, 10)
    assert status == 302 and sum(call[0] == 'request' for call in calls) == 1
    calls.clear()
    def timeout(self): raise TimeoutError('Unknown billing outcome')
    monkeypatch.setattr(Connection, 'getresponse', timeout)
    with pytest.raises(TimeoutError):
        post_provider_json('https://allowed.example/v1', {'allowed.example'}, {}, {}, 10)
    assert sum(call[0] == 'request' for call in calls) == 1 and calls[-1] == ('close',)


def test_dns_timeout_never_dispatches_a_request(monkeypatch):
    from threading import Event
    release = Event()
    def stalled(*_, **__):
        release.wait(1)
        return []
    monkeypatch.setattr(network.socket, 'getaddrinfo', stalled)
    try:
        with pytest.raises(NetworkDenied, match='timed out'):
            network._bounded_resolve('allowed.example', 443, type=socket.SOCK_STREAM, timeout=0.01)
    finally:
        release.set()
