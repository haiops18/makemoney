# Known issues

- The local Docker stack currently uses `.env.example`; its Owner key and PostgreSQL password must be replaced before any network exposure.
- `GET /health/ready` currently reports process readiness rather than a live database probe.
- Frontend has no browser/E2E/component test coverage yet; build and lint only are verified.
- Local Node 18 emits dependency engine warnings from the current ESLint dependency tree; build/lint still passed. Use Node 20+ for the supported frontend toolchain.
- The frontend language control is present but full English translations are not yet authored; current screen copy is Vietnamese-first.
- `npm audit --audit-level=critical` reports 2 critical and 2 high development dependency vulnerabilities; updating requires breaking upgrades and must be reviewed before release.
- The policy engine is intentionally limited to the seeded internal policy and `ONCE` scope. Additional policy authoring and scopes require a separate reviewed migration/API.
- Opportunity and workflow modules are not yet implemented; therefore no executable workflow can consume approvals or reserve budget yet.
- Budget enforcement is an internal control for recorded work only. It cannot guarantee a provider's delayed invoice or an externally created subscription never exceeds USD 50.

