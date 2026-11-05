"""Pinned HTTPS transport primitives. Calling this module does not grant permission.

The execution boundary must supply the exact approved host. No redirects, proxies,
provider retries or caller-selected headers are supported.
"""
import http.client
import ipaddress
import json
import socket
import ssl
import time
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread, Timer
from urllib.parse import urlsplit


class NetworkDenied(ValueError):
    pass


_DNS_SLOTS = BoundedSemaphore(4)


def _bounded_resolve(host: str, port: int, *, type: int, timeout: float):
    if not _DNS_SLOTS.acquire(blocking=False):
        raise NetworkDenied('Provider DNS capacity unavailable')
    result = Queue(maxsize=1)
    def run():
        try:
            result.put((True, socket.getaddrinfo(host, port, type=type)))
        except Exception:
            result.put((False, None))
        finally:
            _DNS_SLOTS.release()
    Thread(target=run, daemon=True).start()
    try:
        succeeded, addresses = result.get(timeout=timeout)
    except Empty:
        raise NetworkDenied('Provider DNS lookup timed out') from None
    if not succeeded:
        raise NetworkDenied('Provider DNS lookup failed')
    return addresses


def resolve_public_target(url: str, allowed_hosts: set[str], resolver=None) -> tuple[str, str, str]:
    """Validate every resolved address and return a pinned target without fetching."""
    if resolver is None:
        resolver = socket.getaddrinfo
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment
            or any(ord(char) < 32 for char in url)):
            raise ValueError
        host = host.encode('idna').decode('ascii').lower()
        if host.endswith('.') or host not in allowed_hosts:
            raise ValueError
        addresses = resolver(host, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError
        public = []
        for family, socktype, _, _, address in addresses:
            if family not in {socket.AF_INET, socket.AF_INET6} or socktype != socket.SOCK_STREAM:
                raise ValueError
            ip = ipaddress.ip_address(address[0])
            if not ip.is_global:
                raise ValueError
            public.append(str(ip))
        return host, public[0], parsed.path or '/'
    except (ValueError, UnicodeError, OSError):
        raise NetworkDenied('Provider target is not an approved public HTTPS destination') from None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        # Avoid a second hostname lookup after authorization. TLS still verifies
        # the original hostname and sends it as SNI, not the pinned address.
        raw = socket.create_connection((self._pinned_address, 443), self.timeout)
        try:
            self.sock = raw
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def post_provider_json(url: str, allowed_hosts: set[str], headers: dict[str, str], payload: dict, timeout_seconds: int) -> tuple[int, object]:
    """One request, no automatic retry. Failures can still have provider charges."""
    return provider_request('POST', url, allowed_hosts, headers, payload, timeout_seconds)


def get_provider_json(url: str, allowed_hosts: set[str], headers: dict[str, str], timeout_seconds: int) -> tuple[int, object]:
    """One bounded read-only request (connection test); same destination controls."""
    return provider_request('GET', url, allowed_hosts, headers, None, timeout_seconds)


def provider_request(method: str, url: str, allowed_hosts: set[str], headers: dict[str, str], payload: dict | None, timeout_seconds: int) -> tuple[int, object]:
    if method not in {'GET', 'POST'} or (method == 'POST') != (payload is not None):
        raise NetworkDenied('Invalid provider request method')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise NetworkDenied('Invalid provider timeout')
    allowed_headers = {'authorization', 'x-api-key', 'x-goog-api-key', 'anthropic-version', 'content-type'}
    if any(name.lower() not in allowed_headers or any(ord(char) < 32 or ord(char) == 127 for char in value) for name, value in headers.items()):
        raise NetworkDenied('Invalid provider headers')
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
    if body is not None and len(body) > 1_000_000:
        raise NetworkDenied('Provider payload exceeds the input limit')
    deadline = time.monotonic() + timeout_seconds
    host, address, path = resolve_public_target(url, allowed_hosts, resolver=lambda host, port, **kwargs: _bounded_resolve(host, port, **kwargs, timeout=timeout_seconds))
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NetworkDenied('Provider request deadline expired before dispatch')
    connection = _PinnedHTTPSConnection(host, address, remaining)
    def abort():
        # A per-read socket timeout alone permits a peer to trickle bytes
        # indefinitely. Shutdown interrupts header/body reads at the total deadline.
        sock = getattr(connection, 'sock', None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
    timer = Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request(method, path, body=body, headers={'Content-Type': 'application/json', **headers} if body is not None else dict(headers))
        response = connection.getresponse()
        # Never follow a redirect or forward credentials to a new destination.
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise NetworkDenied('Provider response exceeds the output limit')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise NetworkDenied('Provider response is not valid bounded JSON') from None
        return response.status, result
    finally:
        timer.cancel()
        connection.close()
