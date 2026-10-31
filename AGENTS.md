# AUTO MONEY AI development rules

## Non-negotiable controls

- Preserve the modular-monolith architecture and existing `/api/v1` contracts.
- The Owner is the sole decision maker. Every protected state change is authenticated, idempotent where applicable, and audited.
- Fail closed: an unverified policy, approval, budget, authorization or identity blocks execution.
- Do not add OpenAI/Codex calls, untrusted code execution, public publication, payments, customer communications or any external execution in Sprint 2.
- PostgreSQL is the source of truth. Do not use floating-point values for money.
- Do not reset volumes or run destructive database commands. Add only forward Alembic migrations.
- Do not commit secrets. Frontend code must never contain an Owner token or pretend missing backend data is real.

## Working protocol

Follow `ANALYZE → PLAN → IMPLEMENT → TEST → REVIEW → DOCUMENT → HANDOFF`. Before a module, read `docs/memory/`; after it, update its status, decisions, known issues and session history. Do not overwrite pre-existing memory.

For a frontend screen whose API does not exist, present an explicit unavailable state rather than mock business data. For any protected action, validate policy, approval, authorization and budget again at the execution boundary.

## Frontend controls

- The React command center uses only `VITE_API_BASE_URL` for a public API base URL. An Owner bearer token is entered per browser session and is never persisted, logged or compiled into the bundle.
- API mutations must provide an `Idempotency-Key`; the UI must wait for backend confirmation before displaying a changed state.
- Screens for unavailable backend modules must state that they are unavailable, not present synthetic business results.

## Release controls

- A release requires all documented quality gates, a clean scoped change, a unique semantic tag and successful CI. Never force-push, overwrite tags/releases or bypass a failed gate.
- Versioning is MAJOR.MINOR.PATCH: accepted feature or breaking change increments MAJOR; enhancement increments MINOR; bug/security fix increments PATCH.
- Before GitHub release, verify branch, remote, tags, permissions, tests, migrations, secrets and dependency audit. If any required check is not verified, record `RELEASE_BLOCKED` and do not tag or release.

