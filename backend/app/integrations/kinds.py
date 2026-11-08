"""Supported integrations: fixed hosts, non-secret settings and a bounded connection check.

Each kind talks to exactly one official host. Secrets are encrypted at rest and are only
decrypted at the moment of a request; they are never returned by the API.
"""
import re
from dataclasses import dataclass
from typing import Any, Callable

GRAPH_VERSION = re.compile(r'^v\d{2}\.0$')
PAGE_ID = re.compile(r'^\d{5,25}$')


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: dict[str, str]
    payload: dict | None = None
    query: dict[str, str] | None = None


@dataclass(frozen=True)
class Kind:
    name: str
    host: str
    purpose: str
    config_keys: tuple[str, ...]
    check_costs: bool  # whether a connection check consumes a paid unit
    clean: Callable[[dict[str, Any]], dict[str, Any]]
    check: Callable[[dict[str, Any], str], Request]
    verify: Callable[[dict[str, Any], Any], str | None]  # returns a short non-secret detail, None if invalid


def _no_config(config: dict[str, Any]) -> dict[str, Any]:
    if config:
        raise ConfigError('This integration has no settings')
    return {}


def _facebook_config(config: dict[str, Any]) -> dict[str, Any]:
    if set(config) - {'page_id', 'graph_version'}:
        raise ConfigError('Facebook settings are page_id and graph_version')
    page_id = str(config.get('page_id', '')).strip()
    version = str(config.get('graph_version') or 'v26.0').strip()
    if not PAGE_ID.match(page_id):
        raise ConfigError('Page ID must be the numeric Facebook Page ID')
    if not GRAPH_VERSION.match(version):
        raise ConfigError('Graph API version must look like v26.0')
    return {'page_id': page_id, 'graph_version': version}


def _tavily_verify(config, raw):
    return f"{len(raw['results'])} result(s)" if isinstance(raw, dict) and isinstance(raw.get('results'), list) else None


def _brave_verify(config, raw):
    results = raw.get('web', {}).get('results') if isinstance(raw, dict) and isinstance(raw.get('web'), dict) else None
    return f'{len(results)} result(s)' if isinstance(results, list) else None


def _accesstrade_verify(config, raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('data'), list):
        return None
    total = raw.get('total')
    return f'{total if isinstance(total, int) else len(raw["data"])} approved campaign(s)'


def _facebook_verify(config, raw):
    if not isinstance(raw, dict) or str(raw.get('id')) != config['page_id']:
        return None
    name = raw.get('name')
    return f'Page: {name[:100]}' if isinstance(name, str) else 'Page found'


KINDS: dict[str, Kind] = {
    'SEARCH_TAVILY': Kind(
        'SEARCH_TAVILY', 'api.tavily.com', 'search', (), True, _no_config,
        lambda config, secret: Request('POST', 'https://api.tavily.com/search', {'Authorization': f'Bearer {secret}'},
                                       payload={'query': 'Tiếp thị liên kết Việt Nam', 'max_results': 1, 'search_depth': 'basic'}),
        _tavily_verify),
    'SEARCH_BRAVE': Kind(
        'SEARCH_BRAVE', 'api.search.brave.com', 'search', (), True, _no_config,
        lambda config, secret: Request('GET', 'https://api.search.brave.com/res/v1/web/search', {'X-Subscription-Token': secret, 'Accept': 'application/json'},
                                       query={'q': 'tiếp thị liên kết', 'count': '1'}),
        _brave_verify),
    'ACCESSTRADE': Kind(
        'ACCESSTRADE', 'api.accesstrade.vn', 'affiliate', (), False, _no_config,
        lambda config, secret: Request('GET', 'https://api.accesstrade.vn/v1/campaigns', {'Authorization': f'Token {secret}'},
                                       query={'approval': 'successful', 'limit': '1', 'page': '1'}),
        _accesstrade_verify),
    'FACEBOOK_PAGE': Kind(
        'FACEBOOK_PAGE', 'graph.facebook.com', 'posting', ('page_id', 'graph_version'), False, _facebook_config,
        lambda config, secret: Request('GET', f"https://graph.facebook.com/{config['graph_version']}/{config['page_id']}", {'Authorization': f'Bearer {secret}'},
                                       query={'fields': 'id,name'}),
        _facebook_verify),
}
