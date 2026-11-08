"""Rule checks for a content version, shared by the Owner's "run checks" and the automatic run after drafting.

Checks are pure rules over stored data; nothing leaves the server. A standing campaign
attestation by the Owner turns that check into an Owner PASS; nothing else is ever passed on the
Owner's behalf, and a FAIL can only be fixed by editing.
"""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.campaigns.checks import Context, Draft, run_checks
from app.db.models import AIResearchRun, AIResearchSource, Campaign, CampaignAttestation, ContentCheck, ContentItem, ContentVersion


def check_context(db, item: ContentItem) -> Context:
    campaign = db.get(Campaign, item.campaign_id)
    run = db.get(AIResearchRun, item.batch_run_id)
    spec = (run.content_spec_json or {}).get('request', {})
    verified = list(db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == run.id, AIResearchSource.verification_status == 'VERIFIED')))
    texts = [source.excerpt for source in verified]
    texts += [f"{term['value_text']} {term.get('value_numeric') or ''}" for term in spec.get('terms', []) if term.get('evidence_status') == 'VERIFIED']
    product = spec.get('product') or {}
    if product.get('price_text') and product.get('price_evidence_status') == 'VERIFIED':
        texts.append(product['price_text'])
    others = db.execute(select(ContentVersion.body).join(ContentItem, (ContentItem.id == ContentVersion.content_id) & (ContentItem.current_version_no == ContentVersion.version_no))
                        .where(ContentItem.campaign_id == item.campaign_id, ContentItem.id != item.id, ContentItem.status != 'REJECTED')).scalars()
    return Context(disclosure_text=campaign.disclosure_text, verified_source_ids={str(source.id) for source in verified}, verified_texts=texts, other_bodies=list(others))


def standing_attestations(db, campaign_id) -> dict[str, CampaignAttestation]:
    rows = db.scalars(select(CampaignAttestation).where(CampaignAttestation.campaign_id == campaign_id, CampaignAttestation.revoked_at.is_(None)))
    return {row.check_name: row for row in rows}


def ensure_checks(db, item: ContentItem) -> str:
    """Run the checks once for the current version and set CHECK_FAILED or IN_REVIEW. Returns the new status."""
    version = db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.version_no == item.current_version_no))
    if not db.scalar(select(func.count()).select_from(ContentCheck).where(ContentCheck.version_id == version.id)):
        draft = Draft(title=version.title, body=version.body, cta=version.cta, hashtags=version.hashtags, claims=version.claims, author_kind=version.author_kind)
        standing = standing_attestations(db, item.campaign_id)
        for result in run_checks(draft, check_context(db, item)):
            attestation = standing.get(result.check) if result.result == 'NEEDS_OWNER' else None
            if attestation:
                db.add(ContentCheck(version_id=version.id, check_name=result.check, result='PASS', method='OWNER', attested_by=attestation.attested_by, attested_at=attestation.attested_at,
                                    note=f'{result.note} Owner (campaign-wide, {attestation.attested_at:%Y-%m-%d}): {attestation.note}'[:1000], evidence=[]))
            else:
                db.add(ContentCheck(version_id=version.id, check_name=result.check, result=result.result, method='RULE', note=result.note, evidence=result.evidence[:20]))
        db.flush()
    failed = db.scalar(select(func.count()).select_from(ContentCheck).where(ContentCheck.version_id == version.id, ContentCheck.result == 'FAIL'))
    item.status, item.decided_by, item.decided_at, item.decision_note = ('CHECK_FAILED' if failed else 'IN_REVIEW'), None, None, None
    return item.status


def open_checks(db, item: ContentItem) -> list[str]:
    version = db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.version_no == item.current_version_no))
    return sorted(db.scalars(select(ContentCheck.check_name).where(ContentCheck.version_id == version.id, ContentCheck.result != 'PASS')))


def now() -> datetime:
    return datetime.now(UTC)
