# AUTO MONEY AI

## Opportunity engine (Step 4 candidate)

Owner-authenticated `/api/v1/opportunities` supports opportunity records, evidence,
three financial scenarios, versioned scoring, risk disqualification, history,
rankings and comparison. The existing Command Center now includes create/edit,
evidence capture, scenario forms, evaluation and comparison of 2–5 opportunities.
See [engine definitions](docs/architecture/OPPORTUNITIES.md). Estimates are not
ledger transactions. Research remains manual; external execution is disabled.

Isolated runtime tests (no production volume):

```sh
docker compose -p step4-test -f compose.step4-test.yml up --build -d --wait
docker compose -p step4-test -f compose.step4-test.yml exec -T backend python -m pytest -q
cd frontend
E2E_BASE_URL=http://127.0.0.1:18005 npm run test:e2e
```

Test-only credentials in that Compose file must only be used on this loopback test
environment. Step 4 is not RELEASED until GitHub release and CI are verified.

Controlled autonomous-business platform. The first increment is deliberately limited to the control plane: a single-owner API, a registry of logical AI roles, audit history, idempotent configuration changes, and a small operational dashboard.

## Run locally

```bash
cp .env.example .env
# Set OWNER_API_KEY to a long random value before exposing the service.
docker compose up --build
```

The API is available at `http://localhost:8000`, OpenAPI at `/docs`, and health probes at `/health/live` and `/health/ready`. All `/api/v1/*` routes require `Authorization: Bearer $OWNER_API_KEY`.

## Current scope

The migration creates the seven logical agents from the design. `PATCH /api/v1/agents/{id}` requires `Idempotency-Key`; it writes both the change and its audit event in the same database transaction. Reusing a key with a different request is rejected.

Sprint 2 Module 1 adds owner-only Policy & Approval controls: `GET /api/v1/policies`, `POST /api/v1/policies/evaluate`, and the `/api/v1/approvals` create/list/detail/approve/reject endpoints. Approvals bind a canonical server-side action hash, policy version, expiry and one-time authorization. They do not execute any external action.

The project intentionally does not execute models, browse the web, charge providers, publish anything, or run untrusted code yet. Those are later gated workflows, not safe defaults.

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

Frontend quality gates:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Docker runtime smoke (preserves named database volumes):

```bash
./scripts/docker-smoke.sh
```

## Command Center (local only)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Enter the Owner token only into the in-memory session field; never set it in `VITE_*` or commit it. `docker compose up --build` also serves the frontend at `http://localhost:3000`, with `/api` and `/health` reverse-proxied to the backend.

The command center is Vietnamese by default and can switch to English. It presents only API-verified dashboard, agent, approval, budget, cost, usage and audit data. Opportunity, Project and Workflow pages remain explicitly unavailable until their backend APIs exist.

## Project decisions

- PostgreSQL is the system of record; Redis is present for the scheduled worker phase but is not trusted for business state.
- A deployment fails in `production` if the example owner key is still configured.
- Monetary limits remain policy configuration until the finance/budget-reservation migration is added; no endpoint claims to enforce the $50 cap yet.
- No React frontend, AI execution, payment, publication, web research, or untrusted-code sandbox is implemented yet.

