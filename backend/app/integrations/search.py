"""Web search through the Owner's search integration. Results are untrusted, unverified snippets."""
from dataclasses import dataclass

from app.ai_brain.network import provider_request
from app.campaigns.links import LinkRuleError, safe_url
from app.integrations.kinds import KINDS

MAX_SNIPPET = 1200


@dataclass(frozen=True)
class Hit:
    title: str
    url: str
    snippet: str


class SearchFailed(ValueError):
    pass


def _clean(title: object, url: object, snippet: object) -> Hit | None:
    if not isinstance(url, str) or not isinstance(title, str):
        return None
    try:
        safe_url(url)
    except LinkRuleError:
        return None
    text = ' '.join(str(snippet or '').split())[:MAX_SNIPPET]
    name = ' '.join(title.split())[:200]
    return Hit(name or url[:200], url, text) if text else None


def search(kind: str, secret: str, query: str, count: int, transport=provider_request) -> list[Hit]:
    """One paid query, no retry. Raises SearchFailed with a short, secret-free reason."""
    host = KINDS[kind].host
    if kind == 'SEARCH_TAVILY':
        code, raw = transport('POST', 'https://api.tavily.com/search', {host}, {'Authorization': f'Bearer {secret}'},
                              {'query': query, 'max_results': count, 'search_depth': 'basic', 'include_answer': False}, 20)
        items = raw.get('results') if isinstance(raw, dict) else None
        hits = [_clean(item.get('title'), item.get('url'), item.get('content')) for item in items or [] if isinstance(item, dict)]
    elif kind == 'SEARCH_BRAVE':
        code, raw = transport('GET', 'https://api.search.brave.com/res/v1/web/search', {host}, {'X-Subscription-Token': secret, 'Accept': 'application/json'}, None, 20,
                              query={'q': query, 'count': str(count), 'country': 'VN', 'search_lang': 'vi'})
        web = raw.get('web') if isinstance(raw, dict) else None
        items = web.get('results') if isinstance(web, dict) else None
        hits = [_clean(item.get('title'), item.get('url'), item.get('description')) for item in items or [] if isinstance(item, dict)]
    else:
        raise SearchFailed('Not a search integration')
    if code in (401, 403):
        raise SearchFailed('The search token was rejected')
    if code == 429:
        raise SearchFailed('The search service is rate limiting; try again later')
    if not 200 <= code < 300 or items is None:
        raise SearchFailed('The search service returned an error')
    return [hit for hit in hits if hit][:count]
