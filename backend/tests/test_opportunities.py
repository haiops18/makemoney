from decimal import Decimal
import pytest

from app.api.opportunity_schemas import OpportunityEvaluate
from app.opportunities.service import calculate_score

from app.opportunities.service import financial_values


@pytest.mark.parametrize('rating,recommendation', [(100, 'HIGH PRIORITY'), (85, 'HIGH PRIORITY'), (84, 'PROMISING'), (75, 'PROMISING'), (74, 'NEEDS RESEARCH'), (50, 'NEEDS RESEARCH'), (49, 'LOW PRIORITY'), (0, 'LOW PRIORITY')])
def test_scoring_thresholds(rating, recommendation):
    from app.opportunities.service import WEIGHTS
    payload = OpportunityEvaluate(scores={key: rating for key in WEIGHTS}, risk_level='LOW')
    weighted, total, disqualified, _, result = calculate_score(payload)
    assert total == rating
    assert sum(weighted.values()) == total
    assert not disqualified
    assert result == recommendation


@pytest.mark.parametrize('risk', ['SEVERE_LEGAL_RISK', 'SEVERE_COPYRIGHT_RISK', 'SEVERE_PLATFORM_POLICY_VIOLATION', 'FRAUD_INDICATOR', 'PROHIBITED_OPERATION'])
def test_every_disqualifier_overrides_perfect_score(risk):
    from app.opportunities.service import WEIGHTS
    payload = OpportunityEvaluate(scores={key: 100 for key in WEIGHTS}, risk_level='LOW', disqualifiers=[risk])
    _, total, disqualified, reason, result = calculate_score(payload)
    assert total == 100 and disqualified and reason and result == 'DISQUALIFIED'


def test_financial_unknown_and_zero_investment():
    assert financial_values(None, None, None) == (None, None, None)
    assert financial_values(Decimal('0'), Decimal('10'), Decimal('25')) == (Decimal('15'), None, Decimal('0'))
    assert financial_values(Decimal('100'), Decimal('20'), Decimal('10')) == (Decimal('-10'), Decimal('-10'), None)


def test_opportunity_lifecycle(client, auth_headers):
    assert client.get('/api/v1/opportunities').status_code == 401
    headers = {**auth_headers, 'Idempotency-Key': 'create-opportunity'}
    payload = {'title': 'Owner research', 'business_model': 'MICRO_SAAS'}
    created = client.post('/api/v1/opportunities', json=payload, headers=headers)
    assert created.status_code == 201
    item = created.json()
    assert item['score'] is None
    assert client.post('/api/v1/opportunities', json=payload, headers=headers).json()['id'] == item['id']
    assert client.post('/api/v1/opportunities', json={**payload, 'title': 'Changed'}, headers=headers).status_code == 409
    path = '/api/v1/opportunities/' + item['id']
    scores = {key: 100 for key in ['market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence']}
    evaluation = client.post(path + '/evaluate', json={'scores': scores, 'risk_level': 'SEVERE'}, headers={**auth_headers, 'Idempotency-Key': 'evaluate'})
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()['score']['disqualified'] is True
    assert evaluation.json()['recommendation'] == 'DISQUALIFIED'
    assert client.get('/api/v1/opportunities/rankings', headers=auth_headers).json()['items'] == []
    assert client.patch(path, json={'status': 'RESEARCHING'}, headers={**auth_headers, 'Idempotency-Key': 'bypass'}).status_code == 409
    assert len(client.get(path + '/evaluations', headers=auth_headers).json()) == 1
    evidence = {'source_name': 'Interview', 'source_type': 'OWNER', 'evidence_type': 'DEMAND', 'summary': '<script>untrusted</script>', 'captured_at': '2026-11-02T00:00:00Z'}
    assert client.post(path + '/evidence', json={**evidence, 'source_url': 'javascript:alert(1)'}, headers={**auth_headers, 'Idempotency-Key': 'bad-url'}).status_code == 422
    assert client.post(path + '/evidence', json=evidence, headers={**auth_headers, 'Idempotency-Key': 'evidence'}).status_code == 201
    estimate = {'scenario': 'BASE', 'currency': 'USD', 'setup_cost': '10', 'monthly_operating_cost': '2', 'expected_monthly_revenue': '5', 'evaluated_at': '2026-11-02T00:00:00Z'}
    result = client.post(path + '/estimates', json=estimate, headers={**auth_headers, 'Idempotency-Key': 'estimate'})
    assert result.status_code == 201
    assert Decimal(result.json()['expected_roi']) == Decimal('30')
    other = client.post('/api/v1/opportunities', json={'title': 'Second', 'business_model': 'AI_SERVICES'}, headers={**auth_headers, 'Idempotency-Key': 'second'}).json()
    comparison = client.post('/api/v1/opportunities/compare', json={'opportunity_ids': [item['id'], other['id']]}, headers=auth_headers)
    assert comparison.status_code == 200
    assert comparison.json()['items'][-1]['opportunity']['status'] == 'DISQUALIFIED'
    summary = client.get('/api/v1/opportunities/summary', headers=auth_headers).json()
    assert summary['total'] == 2
    assert summary['disqualified'] == 1
    detail = client.get(path, headers=auth_headers).json()
    assert Decimal(detail['estimated_monthly_profit']) == 3
    assert detail['last_evaluated'] is not None
    assert client.post(path + '/estimates', json={**estimate, 'setup_cost': '0.000001', 'expected_monthly_revenue': '999999999999'}, headers={**auth_headers, 'Idempotency-Key': 'overflow'}).status_code == 422
