"""ACCESSTRADE publisher API (Vietnam): products, approved campaigns and tracking links.

Fixed host api.accesstrade.vn, header `Authorization: Token <key>`. Each function is one or a
few bounded requests with no retry. Responses are untrusted and sanitized here.
"""
from dataclasses import dataclass

from app.ai_brain.network import provider_request
from app.campaigns.links import LinkRuleError, safe_url

HOST = 'api.accesstrade.vn'
BASE = f'https://{HOST}/v1'


class AccesstradeError(ValueError):
    pass


@dataclass(frozen=True)
class Product:
    product_id: str
    name: str
    url: str
    merchant: str
    price: int | None
    discount: int | None
    image: str | None


@dataclass(frozen=True)
class TrackingLink:
    url_origin: str
    link: str


def _headers(secret: str) -> dict[str, str]:
    return {'Authorization': f'Token {secret}'}


def _check(code: int) -> None:
    if code in (401, 403):
        raise AccesstradeError('ACCESSTRADE rejected the access key')
    if code == 429:
        raise AccesstradeError('ACCESSTRADE is rate limiting; try again in a minute')
    if not 200 <= code < 300:
        raise AccesstradeError('ACCESSTRADE returned an error')


def _money(value: object) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if 0 < number < 10_000_000_000 else None


def _https(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return safe_url(value, https_only=True)
    except LinkRuleError:
        return None


def list_products(secret: str, merchant: str, limit: int, transport=provider_request) -> list[Product]:
    code, raw = transport('GET', f'{BASE}/datafeeds', {HOST}, _headers(secret), None, 20, query={'campaign': merchant, 'limit': str(limit), 'page': '1'})
    _check(code)
    items = raw.get('data') if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise AccesstradeError('ACCESSTRADE returned an unexpected response')
    products = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        url, name = _https(item.get('url')), ' '.join(str(item.get('name') or '').split())[:300]
        if not url or not name:
            continue
        products.append(Product(product_id=str(item.get('product_id') or item.get('sku') or url)[:100], name=name, url=url,
                                merchant=str(item.get('merchant') or item.get('campaign') or merchant)[:200], price=_money(item.get('price')),
                                discount=_money(item.get('discount')), image=_https(item.get('image'))))
    return products


def approved_campaign(secret: str, merchant: str, transport=provider_request) -> str:
    """The id of an ACCESSTRADE campaign the Owner is approved for, matched by merchant name."""
    wanted = merchant.casefold()
    for page in ('1', '2', '3'):
        code, raw = transport('GET', f'{BASE}/campaigns', {HOST}, _headers(secret), None, 20, query={'approval': 'successful', 'limit': '100', 'page': page})
        _check(code)
        items = raw.get('data') if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise AccesstradeError('ACCESSTRADE returned an unexpected response')
        for item in items:
            if isinstance(item, dict) and wanted in {str(item.get('merchant') or '').casefold(), str(item.get('name') or '').casefold()} and item.get('id'):
                return str(item['id'])[:50]
        if len(items) < 100:
            break
    raise AccesstradeError(f'Your ACCESSTRADE account is not approved for a "{merchant}" campaign yet')


def create_links(secret: str, campaign_id: str, urls: list[str], tag: str, transport=provider_request) -> list[TrackingLink]:
    """One request. utm_source/utm_campaign let later steps attribute orders to this app."""
    body = {'campaign_id': campaign_id, 'urls': urls, 'utm_source': 'sinhloi', 'utm_medium': 'social', 'utm_campaign': tag}
    code, raw = transport('POST', f'{BASE}/product_link/create', {HOST}, {**_headers(secret), 'Content-Type': 'application/json'}, body, 30)
    _check(code)
    data = raw.get('data') if isinstance(raw, dict) else None
    items = data.get('success_link') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise AccesstradeError('ACCESSTRADE returned an unexpected response')
    links = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = _https(item.get('short_link')) or _https(item.get('aff_link'))
        origin = item.get('url_origin')
        if link and isinstance(origin, str):
            links.append(TrackingLink(url_origin=origin, link=link))
    return links
