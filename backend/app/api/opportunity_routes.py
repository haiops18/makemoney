import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.opportunity_schemas import (
    CompareRequest, CompareResponse, ComparisonItem, EstimateCreate, EstimateResponse, EvaluationResponse,
    EvaluationResult, EvidenceCreate, EvidenceResponse, OpportunityCreate, OpportunityEvaluate, OpportunityListResponse,
    OpportunityResponse, OpportunityUpdate, RankingsResponse, ScoreDetailResponse,
)
from app.auth.dependencies import require_owner
from app.db.models import AuditEvent, IdempotencyRecord, Opportunity, OpportunityEstimate, OpportunityEvaluation, OpportunityEvidence, OpportunityScoreDetail
from app.db.session import get_db
from app.opportunities.service import calculate_score, financial_values

router = APIRouter(prefix="/api/v1/opportunities", dependencies=[Depends(require_owner)], tags=["opportunities"])


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _idempotent(db: Session, actor: str, key: str, method: str, path: str, payload: dict[str, Any], schema: Any) -> Any | None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(f"{actor}:{key}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor == actor, IdempotencyRecord.key == key))
    if record is None:
        return None
    if (record.method, record.path, record.request_hash) != (method, path, _hash(payload)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for another request")
    return schema.model_validate(record.response_body)


def _store_idempotency(db: Session, actor: str, key: str, method: str, path: str, payload: dict[str, Any], response: Any, code: int) -> None:
    db.add(IdempotencyRecord(actor=actor, key=key, method=method, path=path, request_hash=_hash(payload), status_code=code, response_body=response.model_dump(mode="json")))


def _opportunity_or_404(db: Session, opportunity_id: UUID) -> Opportunity:
    opportunity = db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update())
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opportunity


def _commit_or_conflict(db: Session, actor: str, key: str, method: str, path: str, payload: dict[str, Any], schema: Any, response: Response) -> Any:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _idempotent(db, actor, key, method, path, payload, schema)
        if existing is not None:
            response.status_code = status.HTTP_201_CREATED if method == "POST" and path.endswith("opportunities") else 200
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request conflicts with existing opportunity data")
    return None


def _estimate_response(estimate: OpportunityEstimate) -> EstimateResponse:
    return EstimateResponse.model_validate(estimate)


def _flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request conflicts with existing opportunity data")


def _latest_estimate(db: Session, opportunity_id: UUID, scenario: str) -> OpportunityEstimate | None:
    return db.scalar(select(OpportunityEstimate).where(OpportunityEstimate.opportunity_id == opportunity_id, OpportunityEstimate.scenario == scenario).order_by(OpportunityEstimate.evaluated_at.desc(), OpportunityEstimate.id.desc()))


def _response(db: Session, opportunity: Opportunity) -> OpportunityResponse:
    result = OpportunityResponse.model_validate(opportunity)
    result.last_evaluated = db.scalar(select(func.max(OpportunityEvaluation.evaluated_at)).where(OpportunityEvaluation.opportunity_id == opportunity.id))
    estimate = _latest_estimate(db, opportunity.id, "BASE")
    if estimate:
        result.estimated_setup_cost = estimate.setup_cost
        result.estimated_monthly_cost = estimate.monthly_operating_cost
        result.estimated_monthly_profit = estimate.expected_monthly_profit
        result.estimated_roi = estimate.expected_roi
        result.estimate_currency = estimate.currency
    return result


@router.get("", response_model=OpportunityListResponse)
def list_opportunities(
    search: str | None = None, business_model: str | None = None, status_filter: str | None = None, category: str | None = None,
    sort_by: str = "updated_at", sort_dir: str = "desc", limit: int = 25, offset: int = 0, db: Session = Depends(get_db),
) -> OpportunityListResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be 1..100 and offset must be non-negative")
    if status_filter and status_filter not in {"DRAFT", "RESEARCHING", "EVALUATED", "DISQUALIFIED", "ARCHIVED"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid opportunity status")
    columns = {"title": Opportunity.title, "score": Opportunity.score, "created_at": Opportunity.created_at, "updated_at": Opportunity.updated_at, "risk_level": Opportunity.risk_level}
    if sort_by not in columns or sort_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid sort field or direction")
    statement = select(Opportunity)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(Opportunity.title.ilike(term) | Opportunity.business_model.ilike(term) | Opportunity.target_market.ilike(term))
    if business_model:
        statement = statement.where(Opportunity.business_model == business_model.strip().upper())
    if status_filter:
        statement = statement.where(Opportunity.status == status_filter)
    if category:
        statement = statement.where(Opportunity.category == category)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    ordering = asc(columns[sort_by]) if sort_dir == "asc" else desc(columns[sort_by])
    items = list(db.scalars(statement.order_by(ordering, Opportunity.id).offset(offset).limit(limit)))
    return OpportunityListResponse(items=[_response(db, item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/summary")
def opportunity_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    def count(*conditions):
        return db.scalar(select(func.count()).select_from(Opportunity).where(*conditions)) or 0
    eligible = Opportunity.status.notin_(["DISQUALIFIED", "ARCHIVED"])
    average = db.scalar(select(func.avg(Opportunity.score)))
    return {"total": count(), "high_priority": count(eligible, Opportunity.score >= 85), "promising": count(eligible, Opportunity.score >= 75, Opportunity.score < 85), "needs_research": count(eligible, Opportunity.score >= 50, Opportunity.score < 75), "disqualified": count(Opportunity.status == "DISQUALIFIED"), "evaluated": count(Opportunity.score.is_not(None)), "average_score": str(average) if average is not None else None}


@router.get("/rankings", response_model=RankingsResponse)
def rankings(limit: int = 25, db: Session = Depends(get_db)) -> RankingsResponse:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be 1..100")
    statement = select(Opportunity).where(Opportunity.status.notin_(["DISQUALIFIED", "ARCHIVED"])).order_by(Opportunity.score.desc().nullslast(), Opportunity.confidence_score.desc().nullslast(), Opportunity.updated_at.desc())
    items = list(db.scalars(statement.limit(limit)))
    return RankingsResponse(items=[OpportunityResponse.model_validate(item) for item in items], total=db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status.notin_(["DISQUALIFIED", "ARCHIVED"]))) or 0)


@router.post("/compare", response_model=CompareResponse)
def compare(body: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    opportunities = list(db.scalars(select(Opportunity).where(Opportunity.id.in_(body.opportunity_ids))))
    if len(opportunities) != len(body.opportunity_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more opportunities were not found")
    by_id = {item.id: item for item in opportunities}
    candidates: list[tuple[Opportunity, OpportunityEstimate | None, OpportunityScoreDetail | None, Decimal]] = []
    for opportunity_id in body.opportunity_ids:
        opportunity = by_id[opportunity_id]
        estimate = _latest_estimate(db, opportunity.id, body.scenario)
        detail = db.scalar(select(OpportunityScoreDetail).where(OpportunityScoreDetail.opportunity_id == opportunity.id).order_by(OpportunityScoreDetail.created_at.desc(), OpportunityScoreDetail.id.desc()))
        composite = Decimal(opportunity.score or 0) + Decimal(opportunity.confidence_score or 0) / Decimal("10")
        if opportunity.risk_level == "LOW": composite += Decimal("5")
        if opportunity.status in {"DISQUALIFIED", "ARCHIVED"} or (detail and detail.disqualified): composite -= Decimal("1000")
        candidates.append((opportunity, estimate, detail, composite))
    candidates.sort(key=lambda item: item[3], reverse=True)
    results: list[ComparisonItem] = []
    for index, (opportunity, estimate, detail, _) in enumerate(candidates, start=1):
        reasons: list[str] = []
        if opportunity.status in {"DISQUALIFIED", "ARCHIVED"} or (detail and detail.disqualified): reasons.append("Excluded from implementation: disqualified or archived")
        if opportunity.score is None: reasons.append("Score is UNKNOWN until evaluated")
        elif opportunity.score >= 75: reasons.append("Strong weighted score; ranking does not represent a guarantee")
        if opportunity.risk_level == "LOW": reasons.append("Low recorded risk")
        if estimate is None: reasons.append(f"{body.scenario} financial scenario is UNKNOWN")
        elif estimate.setup_cost is not None: reasons.append("Financial scenario is an estimate, not confirmed revenue or profit")
        results.append(ComparisonItem(opportunity=OpportunityResponse.model_validate(opportunity), scenario=body.scenario, currency=estimate.currency if estimate else None,
            setup_cost=estimate.setup_cost if estimate else None, monthly_operating_cost=estimate.monthly_operating_cost if estimate else None,
            expected_monthly_revenue=estimate.expected_monthly_revenue if estimate else None, expected_monthly_profit=estimate.expected_monthly_profit if estimate else None,
            expected_roi=estimate.expected_roi if estimate else None, break_even_months=estimate.break_even_months if estimate else None,
            automation_score=detail.automation_score if detail else None, ranking=index, reasons=reasons))
    return CompareResponse(items=results, disclaimer="Comparison supports Owner review only. It does not authorize investment, execution, or promise profit.")


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
def create_opportunity(body: OpportunityCreate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> OpportunityResponse:
    path = "/api/v1/opportunities"; payload = body.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, "POST", path, payload, OpportunityResponse)
    if existing: return existing
    opportunity = Opportunity(**body.model_dump(), created_by=actor)
    db.add(opportunity); _flush(db)
    result = OpportunityResponse.model_validate(opportunity)
    db.add(AuditEvent(actor=actor, action="opportunity.created", entity_type="opportunity", entity_id=opportunity.id, detail={"business_model": opportunity.business_model, "data_origin": opportunity.data_origin}))
    _store_idempotency(db, actor, idempotency_key, "POST", path, payload, result, 201)
    replay = _commit_or_conflict(db, actor, idempotency_key, "POST", path, payload, OpportunityResponse, response)
    return replay or result


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(opportunity_id: UUID, db: Session = Depends(get_db)) -> OpportunityResponse:
    return _response(db, _opportunity_or_404(db, opportunity_id))


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
def update_opportunity(opportunity_id: UUID, body: OpportunityUpdate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> OpportunityResponse:
    path = f"/api/v1/opportunities/{opportunity_id}"; payload = body.model_dump(mode="json", exclude_unset=True)
    if not payload: raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field is required")
    existing = _idempotent(db, actor, idempotency_key, "PATCH", path, payload, OpportunityResponse)
    if existing: return existing
    opportunity = _opportunity_or_404(db, opportunity_id)
    latest_risk = db.scalar(select(OpportunityScoreDetail).where(OpportunityScoreDetail.opportunity_id == opportunity_id).order_by(OpportunityScoreDetail.created_at.desc(), OpportunityScoreDetail.id.desc()))
    if (opportunity.status == "DISQUALIFIED" or (latest_risk and latest_risk.disqualified)) and payload.get("status") not in (None, "ARCHIVED"):
        raise HTTPException(status_code=409, detail="Risk disqualification requires a new risk evaluation")
    for name, value in payload.items(): setattr(opportunity, name, value)
    _flush(db); result = OpportunityResponse.model_validate(opportunity)
    db.add(AuditEvent(actor=actor, action="opportunity.updated", entity_type="opportunity", entity_id=opportunity.id, detail={"fields": sorted(payload)}))
    _store_idempotency(db, actor, idempotency_key, "PATCH", path, payload, result, 200)
    replay = _commit_or_conflict(db, actor, idempotency_key, "PATCH", path, payload, OpportunityResponse, response)
    return replay or result


@router.get("/{opportunity_id}/evidence", response_model=list[EvidenceResponse])
def list_evidence(opportunity_id: UUID, db: Session = Depends(get_db)) -> list[EvidenceResponse]:
    _opportunity_or_404(db, opportunity_id)
    return [_ for _ in db.scalars(select(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity_id).order_by(OpportunityEvidence.captured_at.desc()))]


@router.post("/{opportunity_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def create_evidence(opportunity_id: UUID, body: EvidenceCreate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> EvidenceResponse:
    path = f"/api/v1/opportunities/{opportunity_id}/evidence"; payload = body.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, "POST", path, payload, EvidenceResponse)
    if existing: return existing
    _opportunity_or_404(db, opportunity_id)
    evidence = OpportunityEvidence(opportunity_id=opportunity_id, **body.model_dump())
    db.add(evidence); _flush(db); result = EvidenceResponse.model_validate(evidence)
    db.add(AuditEvent(actor=actor, action="opportunity_evidence.created", entity_type="opportunity_evidence", entity_id=evidence.id, detail={"opportunity_id": str(opportunity_id), "verification_status": "UNVERIFIED"}))
    _store_idempotency(db, actor, idempotency_key, "POST", path, payload, result, 201)
    replay = _commit_or_conflict(db, actor, idempotency_key, "POST", path, payload, EvidenceResponse, response)
    return replay or result


@router.get("/{opportunity_id}/estimates", response_model=list[EstimateResponse])
def list_estimates(opportunity_id: UUID, db: Session = Depends(get_db)) -> list[EstimateResponse]:
    _opportunity_or_404(db, opportunity_id)
    return [_estimate_response(item) for item in db.scalars(select(OpportunityEstimate).where(OpportunityEstimate.opportunity_id == opportunity_id).order_by(OpportunityEstimate.scenario, OpportunityEstimate.evaluated_at.desc()))]


@router.post("/{opportunity_id}/estimates", response_model=EstimateResponse, status_code=status.HTTP_201_CREATED)
def create_estimate(opportunity_id: UUID, body: EstimateCreate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> EstimateResponse:
    path = f"/api/v1/opportunities/{opportunity_id}/estimates"; payload = body.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, "POST", path, payload, EstimateResponse)
    if existing: return existing
    _opportunity_or_404(db, opportunity_id)
    profit, roi, break_even = financial_values(body.setup_cost, body.monthly_operating_cost, body.expected_monthly_revenue)
    if any(value is not None and abs(value) >= Decimal('1000000000000') for value in (profit, roi, break_even)):
        raise HTTPException(status_code=422, detail="Derived financial value exceeds supported precision")
    values = body.model_dump()
    values["assumptions_json"] = {**body.assumptions_json, "_calculation": {"version": "2026.11.1", "roi_period_months": 1, "roi_net_return": "monthly_profit_minus_setup_investment", "break_even": "constant_monthly_cash_flow", "expected_value": "UNKNOWN"}}
    estimate = OpportunityEstimate(opportunity_id=opportunity_id, **values, expected_monthly_profit=profit, expected_roi=roi, break_even_months=break_even)
    db.add(estimate); _flush(db); result = _estimate_response(estimate)
    db.add(AuditEvent(actor=actor, action="opportunity_estimate.created", entity_type="opportunity_estimate", entity_id=estimate.id, detail={"opportunity_id": str(opportunity_id), "scenario": body.scenario, "roi_known": roi is not None}))
    _store_idempotency(db, actor, idempotency_key, "POST", path, payload, result, 201)
    replay = _commit_or_conflict(db, actor, idempotency_key, "POST", path, payload, EstimateResponse, response)
    return replay or result


@router.post("/{opportunity_id}/evaluate", response_model=EvaluationResult)
def evaluate_opportunity(opportunity_id: UUID, body: OpportunityEvaluate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> EvaluationResult:
    path = f"/api/v1/opportunities/{opportunity_id}/evaluate"; payload = body.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, "POST", path, payload, EvaluationResult)
    if existing: return existing
    opportunity = _opportunity_or_404(db, opportunity_id)
    weighted, total, disqualified, disqualification_reason, recommendation = calculate_score(body)
    detail = OpportunityScoreDetail(opportunity_id=opportunity_id, scoring_version=body.scoring_version, market_demand_score=weighted["market_demand"], monetization_score=weighted["monetization_potential"], automation_score=weighted["automation_feasibility"], cost_efficiency_score=weighted["experiment_cost"], competitive_advantage_score=weighted["competitive_advantage"], scalability_score=weighted["scalability"], evidence_confidence_score=weighted["evidence_confidence"], total_score=total, disqualified=disqualified, disqualification_reason=disqualification_reason)
    db.add(detail); _flush(db)
    opportunity.score = int(total); opportunity.confidence_score = body.scores.evidence_confidence; opportunity.risk_level = body.risk_level; opportunity.status = "DISQUALIFIED" if disqualified else "EVALUATED"
    evaluated_at = datetime.now(UTC)
    result_snapshot = {"total_score": str(total), "recommendation": recommendation, "disqualified": disqualified, "disqualification_reason": disqualification_reason, "breakdown": {key: str(value) for key, value in weighted.items()}}
    evaluation = OpportunityEvaluation(opportunity_id=opportunity_id, scoring_version=body.scoring_version, input_snapshot_json=payload, result_snapshot_json=result_snapshot, evaluated_by=actor, evaluated_at=evaluated_at)
    db.add(evaluation); _flush(db)
    result = EvaluationResult(opportunity=OpportunityResponse.model_validate(opportunity), score=ScoreDetailResponse.model_validate(detail), evaluation=EvaluationResponse.model_validate(evaluation), recommendation=recommendation)
    db.add(AuditEvent(actor=actor, action="opportunity.evaluated", entity_type="opportunity", entity_id=opportunity.id, detail={"scoring_version": body.scoring_version, "disqualified": disqualified, "total_score": str(total)}))
    _store_idempotency(db, actor, idempotency_key, "POST", path, payload, result, 200)
    replay = _commit_or_conflict(db, actor, idempotency_key, "POST", path, payload, EvaluationResult, response)
    return replay or result


@router.get("/{opportunity_id}/score", response_model=ScoreDetailResponse)
def get_score(opportunity_id: UUID, db: Session = Depends(get_db)) -> ScoreDetailResponse:
    _opportunity_or_404(db, opportunity_id)
    detail = db.scalar(select(OpportunityScoreDetail).where(OpportunityScoreDetail.opportunity_id == opportunity_id).order_by(OpportunityScoreDetail.created_at.desc(), OpportunityScoreDetail.id.desc()))
    if detail is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity has not been evaluated")
    return ScoreDetailResponse.model_validate(detail)


@router.get("/{opportunity_id}/evaluations", response_model=list[EvaluationResponse])
def evaluation_history(opportunity_id: UUID, db: Session = Depends(get_db), limit: int = 25, offset: int = 0) -> list[EvaluationResponse]:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    _opportunity_or_404(db, opportunity_id)
    return [EvaluationResponse.model_validate(item) for item in db.scalars(select(OpportunityEvaluation).where(OpportunityEvaluation.opportunity_id == opportunity_id).order_by(OpportunityEvaluation.evaluated_at.desc(), OpportunityEvaluation.id).offset(offset).limit(limit))]
