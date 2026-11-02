# Step 4 verification checkpoint — 2026-11-02

Feature ID: S2-M3 / STEP4. Baseline: baa42e5b16fed914a4cd26dbe66d3464cfe2399a.
Target candidate: v27.0.0 (remote latest v26.4.0 verified; no new tag created).
Business requirement: Owner records and compares opportunities with explicit
evidence, scenarios and versioned advisory scoring. Modules: database, opportunity
service/API, existing React command center, tests and CI. Target version pending
authenticated remote tag/release verification (new feature requires MAJOR).

Implemented UI: edit descriptive fields, evidence entry, scenario entry preserving
missing money as UNKNOWN, mandatory ratings/risk review, score breakdown/history,
comparison for 2–5 selected records. Idempotency key retained for detail-form retries;
success requires schema-validated server response. Evidence renders as escaped text.

Executed on isolated PostgreSQL 16 and rebuilt Compose images:

- `docker compose -p step4-local -f compose.step4-test.yml up --build -d --wait`
  built both images and started test-only services. Frontend health subsequently
  verified `healthy`; HTTP and real browser/API tests succeeded independently.
- Migration chain through `20261102_0004` applied to fresh test database.
- Backend: **18 passed**, no skips. Includes FK/check constraint rejection,
  rollback, opportunity row-lock increments, budget and one-time authorization
  concurrency plus authentication, idempotency, evidence, estimates, disqualification
  and comparison regression.
- Frontend lint/typecheck/build: passed; **7 component/unit tests passed**.
- Playwright: **2 passed**, including real API flow on loopback 18005: Owner login,
  create, evidence, estimate, evaluate, score, compare, audit and unauthorized GET.
  Navigation/mobile test uses mock API responses; business-flow test uses real API.
- `npm audit --audit-level=high`: exit 0, 12 moderate dev-tool findings remain.
- `git diff --check`: passed.

Continuation: GitHub device authentication completed, push/admin permissions
verified. No main branch protection or rulesets configured. Remote v26.4.0 release
and CI succeeded and includes Policy/Finance migrations through 0003. Backend
audit found pytest vulnerability; requirement upgraded to >=9.0.3,<10 and pip-audit
now reports no known vulnerabilities. Latest source PostgreSQL suite: **19 passed**,
including four concurrent API retries resulting in one record and audit event.
Frontend lint/build/7 tests and real runtime Playwright 2 tests passed again.
Comparison now offers all three scenarios; descriptive form labels localized.
Remote CI/new release not yet verified. Status: **RELEASE_BLOCKED** pending gates.

## Final candidate review

Candidate v27.0.0 adds seven overview KPIs, sorting and list financial estimates /
last evaluation; comparison displays currency, cost, revenue, profit, ROI,
break-even, risk, confidence, validation days and automation for all three scenarios.
Detail loads the stored description, customer and monetization data. Financial
confidence remains optional. Expected Value remains UNKNOWN without probabilities.
One-month net-return ROI now includes upfront setup investment and stores the
server calculation version in assumptions; this supersedes earlier formula notes.

Latest executed source suite: **32 backend tests passed**, including eight score
boundary cases, all five risk disqualifiers, invalid URLs, overflow, transactional
rollback, FK/check constraints and concurrent idempotent requests. **9 frontend
tests passed**, including escaped untrusted HTML and rejecting mismatched mutation
responses. Lint/typecheck/build passed. Real API E2E expanded to edit, all scenarios,
severe-risk disqualification and mobile display; final rerun/CI pending.

Security review: no .env tracked, no secret token/private-key signatures found in
scoped source/docs; only explicit test credentials added. Evidence is never fetched
or executed. All new mutation APIs are Owner authenticated, idempotent and audited.
No provider call, external execution, publication, payment or ledger write exists.

Known limitations retained: domain identifiers use English enum codes; comparison
rank is advisory, not a decision. Twelve moderate development-tool dependency
findings have no available remediation in the existing compatible toolchain.
Local coverage is not a claim of exhaustive testing. Release requires final CI,
merge, unique annotated tag and verified GitHub Release; not yet RELEASED.

## Final local gates

- Backend mounted source and rebuilt test Compose: **32 passed** with PostgreSQL.
- Frontend: **10 passed**, ESLint/typecheck/production build passed.
- Real runtime Chromium: **2 passed**, including edit, all three scenarios,
  scoring, comparison, severe disqualification, mobile display and audit.
- A failing E2E exposed a stale initial list race; fixed by cancelling the in-flight
  query before refetch after creation. Added a component regression. Scenario
  form refresh now preserves user inputs instead of remounting on data updates.
- Dependency audits: pip-audit clean; npm high/critical gate clean (12 moderate
  dev-tool findings). Scoped secret-signature review and diff whitespace check passed.
- CI for earlier candidates passed; final commit CI remains required before merge.
