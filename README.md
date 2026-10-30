# AUTO MONEY AI

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

The project intentionally does not execute models, browse the web, charge providers, publish anything, or run untrusted code yet. Those are later gated workflows, not safe defaults.

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Project decisions

- PostgreSQL is the system of record; Redis is present for the scheduled worker phase but is not trusted for business state.
- A deployment fails in `production` if the example owner key is still configured.
- Monetary limits remain policy configuration until the finance/budget-reservation migration is added; no endpoint claims to enforce the $50 cap yet.

