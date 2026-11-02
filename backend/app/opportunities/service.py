from decimal import Decimal

from app.api.opportunity_schemas import OpportunityEvaluate, rounded

WEIGHTS = {
    "market_demand": Decimal("25"), "monetization_potential": Decimal("20"), "automation_feasibility": Decimal("15"),
    "experiment_cost": Decimal("15"), "competitive_advantage": Decimal("10"), "scalability": Decimal("10"), "evidence_confidence": Decimal("5"),
}

DISQUALIFIER_LABELS = {
    "SEVERE_LEGAL_RISK": "Severe legal risk", "SEVERE_COPYRIGHT_RISK": "Severe copyright risk",
    "SEVERE_PLATFORM_POLICY_VIOLATION": "Severe platform-policy violation", "FRAUD_INDICATOR": "Fraud indicator",
    "PROHIBITED_OPERATION": "Model requires a prohibited operation",
}


def financial_values(setup_cost: Decimal | None, operating_cost: Decimal | None, revenue: Decimal | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    profit = revenue - operating_cost if revenue is not None and operating_cost is not None else None
    roi = ((profit - setup_cost) / setup_cost * Decimal("100")) if profit is not None and setup_cost not in (None, Decimal("0")) else None
    break_even = (setup_cost / profit) if setup_cost is not None and profit is not None and profit > 0 else None
    return profit, roi, break_even


def calculate_score(payload: OpportunityEvaluate) -> tuple[dict[str, Decimal], Decimal, bool, str | None, str]:
    inputs = payload.scores.model_dump()
    weighted = {key: rounded(Decimal(inputs[key]) * weight / Decimal("100")) for key, weight in WEIGHTS.items()}
    total = rounded(sum(weighted.values(), Decimal("0")))
    reasons = [DISQUALIFIER_LABELS[item] for item in payload.disqualifiers]
    if payload.risk_level == "SEVERE" and not reasons:
        reasons.append("Severe risk assessment")
    disqualified = bool(reasons)
    if disqualified:
        recommendation = "DISQUALIFIED"
    elif total >= 85:
        recommendation = "HIGH PRIORITY"
    elif total >= 75:
        recommendation = "PROMISING"
    elif total >= 50:
        recommendation = "NEEDS RESEARCH"
    else:
        recommendation = "LOW PRIORITY"
    return weighted, total, disqualified, "; ".join(reasons) or None, recommendation
