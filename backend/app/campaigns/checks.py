"""Deterministic Level B content checks. They inform the Owner; they never approve.

Every check returns PASS, FAIL or NEEDS_OWNER. Checks that need human judgement (media
rights, legal/advertising/tax) are always NEEDS_OWNER and only an Owner attestation
can turn them into PASS. The rule lists are app heuristics, not legal advice.
"""
import re
from dataclasses import dataclass, field

from app.ai_brain.content_contract import _WEB_ADDRESS, LINK_PLACEHOLDER

# Guarantees, unprovable superlatives and health/finance promises. Vietnamese advertising
# rules restrict superlatives and guarantees without proof; the Owner decides on each hit.
BANNED_PHRASES = ('tốt nhất', 'rẻ nhất', 'duy nhất', 'số 1', 'số một', 'hàng đầu', 'cam kết', 'đảm bảo', 'bảo đảm', 'chắc chắn', '100%', '100 %',
                  'chữa khỏi', 'chữa bệnh', 'điều trị', 'trị dứt điểm', 'khỏi hẳn', 'giàu nhanh', 'làm giàu', 'thu nhập thụ động', 'không rủi ro',
                  'best', '#1', 'guarantee', 'risk-free', 'risk free', 'cure')
MONEY = re.compile(r'(?i)(\$\s?\d[\d.,]*|\d[\d.,]*\s?(?:%|đ\b|₫|vnđ|vnd|usd|k\b|nghìn|ngàn|triệu|tr\b))')
NUMBER = re.compile(r'\d[\d.,]*')
DUPLICATE_THRESHOLD = 0.8


@dataclass(frozen=True)
class Draft:
    title: str
    body: str
    cta: str
    hashtags: list[str]
    claims: list[dict]
    author_kind: str


@dataclass
class Context:
    disclosure_text: str | None
    verified_source_ids: set[str]
    verified_texts: list[str]
    other_bodies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Result:
    check: str
    result: str
    note: str
    evidence: list[str] = field(default_factory=list)


def _digits(value: str) -> str:
    return re.sub(r'\D', '', value)


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r'\w+', text.casefold())
    return {tuple(words[index:index + 3]) for index in range(max(len(words) - 2, 0))}


def similarity(first: str, second: str) -> float:
    a, b = _shingles(first), _shingles(second)
    return len(a & b) / len(a | b) if a and b else 0.0


def run_checks(draft: Draft, context: Context) -> list[Result]:
    text = '\n'.join([draft.title, draft.body, draft.cta, ' '.join(draft.hashtags)])
    folded = text.casefold()
    results = []

    placeholder = LINK_PLACEHOLDER in draft.body or LINK_PLACEHOLDER in draft.cta
    results.append(Result('LINK_PLACEHOLDER', 'PASS' if placeholder else 'FAIL',
                          'The link placeholder is present.' if placeholder else f'Add {LINK_PLACEHOLDER} where the affiliate link goes.'))

    if context.disclosure_text:
        results.append(Result('DISCLOSURE', 'PASS', 'The campaign disclosure is added on export.', [context.disclosure_text]))
    else:
        results.append(Result('DISCLOSURE', 'NEEDS_OWNER', 'The campaign has no disclosure text. Confirm how this post discloses the affiliate link.'))

    facts = [claim for claim in draft.claims if claim.get('classification') == 'FACT']
    unsupported = [claim['statement'] for claim in facts if not set(claim.get('source_ids') or []) or not set(claim['source_ids']) <= context.verified_source_ids]
    if unsupported:
        results.append(Result('CLAIM_EVIDENCE', 'FAIL', 'Some factual claims lack a verified source.', unsupported))
    elif draft.author_kind == 'OWNER':
        results.append(Result('CLAIM_EVIDENCE', 'NEEDS_OWNER', 'The text was edited by the Owner. Confirm the factual statements still match the verified sources.',
                              [claim['statement'] for claim in facts]))
    else:
        results.append(Result('CLAIM_EVIDENCE', 'PASS', 'Every factual claim cites a verified source.', [claim['statement'] for claim in facts]))

    known_numbers = {_digits(match) for source in context.verified_texts for match in NUMBER.findall(source)} - {''}
    mentions = [match.group(0).strip() for match in MONEY.finditer(text.replace(LINK_PLACEHOLDER, ''))]
    unmatched = [mention for mention in mentions if _digits(mention) not in known_numbers]
    results.append(Result('PRICE_CLAIM', 'FAIL' if unmatched else 'PASS',
                          'Prices, percentages or amounts not found in verified data.' if unmatched else 'Every price or percentage matches verified data.' if mentions else 'No price or percentage.',
                          unmatched or mentions))

    hits = sorted({phrase for phrase in BANNED_PHRASES if phrase in folded})
    results.append(Result('PLATFORM_POLICY', 'FAIL' if hits else 'PASS',
                          'Remove guarantees, unprovable superlatives or health/finance promises.' if hits else 'No restricted phrases found.', hits))

    links = _WEB_ADDRESS.findall(text.replace(LINK_PLACEHOLDER, ''))
    results.append(Result('EXTRA_LINKS', 'NEEDS_OWNER' if links else 'PASS',
                          'The text contains other web addresses. Confirm they are intended.' if links else 'No other web addresses.', [str(link) for link in links]))

    closest = max((similarity(draft.body, other) for other in context.other_bodies), default=0.0)
    results.append(Result('DUPLICATE', 'FAIL' if closest >= DUPLICATE_THRESHOLD else 'PASS',
                          f'Very similar to another item in this campaign ({closest:.0%}).' if closest >= DUPLICATE_THRESHOLD else f'Highest similarity {closest:.0%}.'))

    results.append(Result('MEDIA_RIGHTS', 'NEEDS_OWNER', 'Confirm you have the right to use every image, video and document you post with this text.'))
    results.append(Result('LEGAL_ADS_TAX', 'NEEDS_OWNER', 'Confirm the post follows advertising and e-commerce rules and the platform policy, and that affiliate income is declared for tax.'))
    return results
