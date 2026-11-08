"""Durable usage, distinct from task completion and confirmed provider charges."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text

from app.ai_brain.content_contract import ContentDraftOutput
from app.ai_brain.openai_contract import ProviderOutputError
from app.ai_brain.pricing import Pricing
from app.ai_brain.providers import ProviderResult
from app.db.models import AIInvocation, AIModelPrice, AIResearchRun, AuditEvent, BudgetAccount, BudgetReservation, ContentItem, ContentVersion, CostRecord, UsageRecord


def record_outcome(factory, execution_id: UUID, result: ProviderResult | None, error: ProviderOutputError | None) -> bool:
    """Record a single dispatch outcome even after cancellation/lease expiry.

    Usage-derived cost is an estimate, never a confirmed charge. Keep at least
    the original reservation, including expired reservations; only the existing
    Owner reconciliation operation may settle/release uncertain provider costs.
    A later known outcome can refine USAGE_UNKNOWN without dispatching again.
    """
    if (result is None) == (error is None):
        raise ValueError('Exactly one result or error is required')
    usage = result.usage if result else error.usage
    request_id = result.provider_request_id if result else error.request_id
    with factory.begin() as db:
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.execution_id == execution_id).with_for_update())
        if invocation is None or invocation.status not in {'DISPATCHED', 'USAGE_UNKNOWN'}:
            return False
        if invocation.status == 'USAGE_UNKNOWN' and usage is None:
            return False
        if request_id:
            # Serialize request identity independently of the invocation lock.
            # A conflicting response cannot wipe out the pending charge hold.
            if db.bind.dialect.name == 'postgresql':
                db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': f'ai-response:{invocation.provider_id}:{request_id}'})
            duplicate = db.scalar(select(AIInvocation.id).where(AIInvocation.provider_id == invocation.provider_id, AIInvocation.provider_request_id == request_id, AIInvocation.id != invocation.id))
            if duplicate:
                usage = None
                request_id = None
                error = ProviderOutputError('DUPLICATE_PROVIDER_RESPONSE')
                result = None
        invocation.provider_request_id = request_id
        invocation.completed_at = datetime.now(UTC)
        invocation.error_code = error.code if error else None
        invocation.status = 'SUCCEEDED' if result else ('FAILED' if usage else 'USAGE_UNKNOWN')
        if result:
            invocation.output_json = result.payload.model_dump(mode='json')
            if isinstance(result.payload, ContentDraftOutput):
                _materialize_content(db, invocation, result.payload)
        if usage is not None:
            price = db.get(AIModelPrice, invocation.price_id)
            pricing = Pricing(price.model_id, price.version, price.effective_at.replace(tzinfo=UTC) if price.effective_at.tzinfo is None else price.effective_at, Decimal(price.input_per_million), Decimal(price.output_per_million))
            calculated = pricing.ceiling(usage.input_tokens, usage.output_tokens)
            reservation = db.get(BudgetReservation, invocation.reservation_id)
            db.scalar(select(BudgetAccount).where(BudgetAccount.id == reservation.budget_account_id).with_for_update())
            reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.id == reservation.id).with_for_update().execution_options(populate_existing=True))
            invocation.input_tokens = usage.input_tokens
            invocation.output_tokens = usage.output_tokens
            invocation.calculated_cost = calculated
            confirmed = Decimal(reservation.actual_amount) if reservation.status in {'SETTLED', 'RELEASED'} and reservation.actual_amount is not None else None
            record = UsageRecord(agent_run_id=invocation.id, provider=str(invocation.provider_id), model=invocation.model_id,
                                 input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, estimated_cost=calculated,
                                 actual_cost=confirmed, currency='USD')
            db.add(record)
            db.flush()
            invocation.usage_record_id = record.id
            db.add(CostRecord(task_id=invocation.execution_id, category='AI_INFERENCE', provider=str(invocation.provider_id), amount=confirmed if confirmed is not None else calculated,
                              currency='USD', source='OWNER_RECONCILIATION' if confirmed is not None else 'PROVIDER_TOKEN_USAGE', status='CONFIRMED' if confirmed is not None else 'PENDING_RECONCILIATION'))
            if calculated > Decimal(reservation.reserved_amount) and reservation.status in {'ACTIVE', 'EXPIRED'}:
                reservation.reserved_amount = calculated
                db.add(AuditEvent(actor='ai-worker', action='ai_invocation.usage_ceiling_exceeded', entity_type='ai_invocation', entity_id=invocation.id,
                                  detail={'reservation_id': str(reservation.id), 'calculated_cost': str(calculated), 'estimated_cost': str(invocation.estimated_cost)}))
        db.add(AuditEvent(actor='ai-worker', action='ai_invocation.outcome_recorded', entity_type='ai_invocation', entity_id=invocation.id,
                          detail={'execution_id': str(execution_id), 'status': invocation.status, 'usage_known': usage is not None,
                                  'error_code': invocation.error_code, 'charge_confirmed': False}))
    return True


def _materialize_content(db, invocation: AIInvocation, output: ContentDraftOutput) -> None:
    """Create one DRAFT content item and its AI version 1 per output item, in the outcome transaction.

    record_outcome runs once per DISPATCHED invocation; the unique (invocation, index) key
    additionally guarantees a replay can never duplicate drafts.
    """
    run = db.get(AIResearchRun, invocation.research_run_id)
    spec = run.content_spec_json if run is not None and run.kind == 'CONTENT' else None
    if not spec:
        raise ValueError('Content output without a content batch')
    language = spec['request']['language']
    for index, item in enumerate(output.items):
        content = ContentItem(campaign_id=run.campaign_id, batch_run_id=run.id, source_invocation_id=invocation.id, item_index=index,
                              product_id=UUID(spec['product_id']) if spec.get('product_id') else None, affiliate_link_id=UUID(spec['affiliate_link_id']), content_type=item.content_type,
                              language=language, status='DRAFT', current_version_no=1)
        db.add(content)
        db.flush()
        db.add(ContentVersion(content_id=content.id, version_no=1, title=item.title, body=item.body, hashtags=item.hashtags, cta=item.cta,
                              claims=[claim.model_dump(mode='json') for claim in item.claims], author_kind='AI', invocation_id=invocation.id, author='content-agent'))
        db.add(AuditEvent(actor='ai-worker', action='content.drafted', entity_type='content_item', entity_id=content.id,
                          detail={'campaign_id': str(run.campaign_id), 'batch_run_id': str(run.id), 'invocation_id': str(invocation.id), 'content_type': item.content_type}))
