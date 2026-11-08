# AUTO MONEY AI

Owner guide (Vietnamese): [docs/USER_GUIDE.md](docs/USER_GUIDE.md). It covers
sign-in, provider/price/agent setup, running the seven AI stages, promotion and
cost reconciliation.

## v30.0.0 — Step 7A AI Content & Affiliate Factory (Level B)

- **Campaigns** turn an evaluated opportunity into an affiliate campaign with its own
  verified sources, program terms, products and https affiliate links on allowed hosts.
- **Content batches** freeze the campaign data and run the `content` agent on the
  existing one-approval auto-run, under consent, policy, cost-limit and budget checks.
  The model only sees `{{AFFILIATE_LINK}}`; output with any web address is rejected.
- **Level B review**: rule checks (link, disclosure, claim evidence, prices, restricted
  phrases, other links, duplicates) plus Owner-confirmed media-rights and ads/tax checks,
  versioned Owner edits, approve/reject with a note, export with the real link, and the
  Owner's publish records. The app never posts, pays or contacts anyone.
- Migrations `20261107_0020`–`20261107_0022` (forward only). See CHANGELOG and
  docs/USER_GUIDE.md §6.1–6.3.

## v29.2.0 — one-approval auto-run

- Research workflows: **Approve & run automatically** approves the whole plan once;
  the worker then runs every stage in dependency order. Every AI call still checks
  consent, policy, the research cost limit and its budget reservation; any change,
  failure or budget denial stops the run. Per-task approval remains available.

## v29.1.0 — sign-in and AI stage approval

- Full-screen sign-in page with Enter-to-submit and "Remember me". Remembered
  sessions persist in this browser until expiry or sign-out; otherwise they last
  for the current tab. Sessions expire after 12 hours (`SESSION_TTL_MINUTES=720`).
- The Workflow page now requests approval for AI stages under the enabled
  `AI_INFERENCE` policy, so the seven AI stages can be approved and run from the UI.

## AI Brain & Research Agents — Step 6 (v29.0.0)

The Owner can run a seven-stage AI research pipeline on Owner-entered evidence:
research plan → market research and competitor analysis → opportunity generation
→ financial analysis and risk review → final report. The report can be promoted
to a DRAFT opportunity for the existing, Owner-driven scoring.

Controls (all fail closed):

- **Providers:** OpenAI (Responses API), Anthropic (Messages API) and Google Gemini
  (`generateContent`) on their official endpoints only. Custom base URLs and
  `OPENAI_COMPATIBLE` are stored but never receive a credential or prompt.
  Keys are encrypted with `AI_CREDENTIALS_KEY` (Fernet, from the deployment secret
  manager); losing or changing it makes stored keys unreadable.
- **Consent:** a default-off global consent enabled only through the Approval Center.
- **Per task:** each AI stage needs its own one-time approval of the exact
  server-built request, model, prompt version, price version and cost ceiling,
  plus a PostgreSQL budget reservation. Global consent does not approve a task.
- **Dispatch:** one request per approval, pinned public HTTPS address, total
  deadline, no redirects, no tools, no automatic retry or fallback. A request that
  may have been billed is never sent again automatically.
- **Evidence:** sources are never fetched. The Owner verifies or rejects each
  excerpt; only verified sources may support a `FACT`, rejected ones are never sent.
  Model output is validated against a strict schema and stays labelled unverified.
- **Cost:** token-based cost is an estimate. Unknown outcomes keep their budget
  hold. The Owner reconciles each invocation against the provider invoice on the
  **AI usage** page (settle or release); only then is a cost confirmed.

Owner workflow: *Settings* → add provider and key, set model prices, assign
agent profiles (research, ceo, finance, auditor), request and enable global
consent, optionally *Test connection*. *AI research* → create draft, add and
verify sources, create workflow, *Add AI stages*. *Workflows* → submit/approve/start,
then approve and run each stage. *AI usage* → review and reconcile costs.

Isolated verification (test-only key and loopback port):

```sh
export STEP6_TEST_KEY=$(python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
docker compose -p step6-ci -f compose.step6-test.yml up --build -d --wait
docker compose -p step6-ci -f compose.step6-test.yml stop worker
docker compose -p step6-ci -f compose.step6-test.yml exec -T backend python -m pytest -q
docker compose -p step6-ci -f compose.step6-test.yml start worker
cd frontend && E2E_BASE_URL=http://127.0.0.1:18007 E2E_STEP6=1 npx playwright test e2e/ai-providers.spec.ts
```

Automated tests use injected fake provider transports; no test contacts a real
provider. See `docs/releases/STEP6_VERIFICATION.md`.

## Workflow orchestration — Step 5 RELEASED (v28.0.0)

The Owner can build workflows from recorded opportunities, define dependencies,
request approvals and run two allowlisted, zero-cost internal validation handlers.
PostgreSQL stores execution attempts, leases and audit events. Workflow approval
does not authorize individual tasks: each execution requires a separate approval
bound to its exact server-generated action. External execution and AI calls remain
disabled. Recovery requires a fresh approval after an expired lease.

Isolated verification (test credentials and loopback port only):

```sh
docker compose -p step5-ci -f compose.step5-test.yml up --build -d --wait
docker compose -p step5-ci -f compose.step5-test.yml stop worker
docker compose -p step5-ci -f compose.step5-test.yml exec -T backend python -m pytest -q
docker compose -p step5-ci -f compose.step5-test.yml start worker
cd frontend
E2E_BASE_URL=http://127.0.0.1:18006 E2E_STEP5=1 E2E_COMPOSE_PROJECT=step5-ci npm run test:e2e
```

Release: https://github.com/haiops18/makemoney/releases/tag/v28.0.0

## Opportunity engine — Step 4 RELEASED (v27.0.0)

[GitHub Release](https://github.com/haiops18/makemoney/releases/tag/v27.0.0)
verified at commit `5f7441c7677ebecb1e232d4be79acf0657916dca`.

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
environment. Release and tag CI passed; see `docs/releases/STEP4_VERIFICATION.md`.

Controlled autonomous-business platform. The first increment is deliberately limited to the control plane: a single-owner API, a registry of logical AI roles, audit history, idempotent configuration changes, and a small operational dashboard.

## Run locally

```bash
cp .env.example .env
# Set OWNER_API_KEY to a long random value before exposing the service.
docker compose up --build
```

The API is available at `http://localhost:8000`, OpenAPI at `/docs`, and health probes at `/health/live` and `/health/ready`. Protected `/api/v1/*` routes require an Owner bearer token. `/api/v1/auth/login` exchanges Admin credentials for a temporary in-memory Owner session.

## Current scope

The migration creates the seven logical agents from the design. `PATCH /api/v1/agents/{id}` requires `Idempotency-Key`; it writes both the change and its audit event in the same database transaction. Reusing a key with a different request is rejected.

Sprint 2 Module 1 adds owner-only Policy & Approval controls: `GET /api/v1/policies`, `POST /api/v1/policies/evaluate`, and the `/api/v1/approvals` create/list/detail/approve/reject endpoints. Approvals bind a canonical server-side action hash, policy version, expiry and one-time authorization. They do not execute any external action.

The project does not browse the web, publish anything, take payments or run untrusted code. Model execution exists only through the Step 6 approval and budget controls above.

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

Open `http://localhost:5173` and sign in using the configured Admin credentials. The Owner session token stays in browser memory; never set it in `VITE_*` or commit it. `docker compose up --build` also serves the frontend at `http://localhost:3000`, with `/api` and `/health` reverse-proxied to the backend.

The command center is Vietnamese by default and can switch to English. It presents API-backed dashboard, agent, approval, budget, opportunity, workflow and audit records. Opportunity scenarios remain explicitly estimated. The Project page remains unavailable until its backend API exists.

## Project decisions

- PostgreSQL is the system of record; Redis is present for the scheduled worker phase but is not trusted for business state.
- A deployment fails in `production` if the example owner key is still configured.
- Numeric budget accounts and atomic reservations enforce the configured internal-work budget; they do not reconcile delayed external provider invoices.
- The React command center is implemented. AI execution, payment, business publication, web research and untrusted-code sandboxing remain disabled or unimplemented.

