# Opportunity engine — S2-M3 / Step 4

Owner-entered research only. Evidence is untrusted text; URLs are stored without
fetching. All mutations require Owner authentication and an Idempotency-Key and
record an audit event in the same transaction. Archival replaces deletion.

Migration 20261102_0004 extends 20261031_0003 with opportunities, evidence,
append-only estimates, score details and evaluation snapshots. Business models
are extensible string identifiers. Missing estimates are SQL NULL / UNKNOWN.

Scoring rules 2026.11.1 accept seven explicit Owner ratings from 0–100 and weight
them by 25/20/15/15/10/10/5. The total is a ranking, never a probability. Severe
legal, copyright or platform risk, fraud, prohibited operations or a SEVERE risk
assessment disqualify the opportunity regardless of score. Evaluation snapshots
preserve inputs, risk assessment and outputs. Rule changes require a new version.

Each estimate is a single-currency, constant monthly cash-flow scenario. Monthly
profit = revenue minus operating cost. ROI is the one-month operating net return
divided by upfront setup investment, multiplied by 100; setup investment is not
deducted a second time from operating profit. Break-even months = setup investment
divided by positive monthly profit, assuming immediate recurring cash flow and no
growth, financing, tax or discounting beyond supplied costs. It is an estimate.
Zero or missing investment yields UNKNOWN ROI; nonpositive profit yields UNKNOWN
break-even. No FX conversion, probability, expected value or ledger posting occurs.

API prefix: /api/v1/opportunities. Static /rankings and /compare routes precede
UUID routes. Detail subresources: /evidence, /estimates, /evaluate, /score and
/evaluations. List supports search, business_model, status_filter, category,
sort_by, sort_dir, limit and offset. No route authorizes business execution.

Release remains blocked pending complete command-center forms, comparison UI,
PostgreSQL migration/concurrency checks, feature E2E and GitHub CI verification.
