# Current task

**Task ID:** S2-M3

Latest: advanced UI and real PostgreSQL/Compose E2E implemented and locally
verified (18 backend, 7 frontend, 2 Playwright passed). Awaiting supported GitHub
device authentication; remote gates and remaining acceptance limits are in
`docs/releases/STEP4_VERIFICATION.md`. Not RELEASED.

Continuation: backend core and basic real-data UI implemented; release blocked.
Next: finish advanced UI/forms and feature component/E2E coverage, then verify
isolated PostgreSQL migration/concurrency/runtime and restore GitHub authentication.

Implement Opportunity Discovery & Scoring without enabling crawlers, web research or agent execution.

S2-M1 and S2-M2 checkpoints are complete: policy/approval controls plus numeric, atomic budget reservations are verified.

Next acceptance target: opportunity CRUD, evidence, scenario estimates, versioned scoring and direct disqualification for severe risk. No crawler, online search or AI execution is in scope.

## Completed adjacent frontend task — FE-P2

FE-P2 Command Center quality is implemented and locally verified. It did not change the S2-M3 backend priority. Its release is blocked until browser E2E can be run and GitHub authentication/CI permission is available.

