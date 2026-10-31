# Decisions

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-31 | Keep the existing FastAPI modular-monolith layout. | Sprint 2 must extend, not rebuild, Sprint 1. |
| 2026-10-31 | Implement Policy & Approval before all other Sprint 2 modules. | Every later protected execution depends on it. |
| 2026-10-31 | Do not enable external execution or OpenAI/Codex in Sprint 2. | Controlled autonomy requires controls to precede execution. |
| 2026-10-31 | Use explicit unavailable frontend states until APIs exist. | Mock business data must not be presented as real. |
| 2026-10-31 | Approval identity is a server-side hash of canonical JSON including policy ID/version, action payload, resource and scope. | A decision cannot be replayed against a modified action or policy revision. |
| 2026-10-31 | An approval emits one `ONCE` authorization and consumption locks that row in PostgreSQL. | Concurrent execution attempts must allow at most one protected execution. |
| 2026-10-31 | Use `NUMERIC(18,6)` and USD-only finance records in the MVP. | Monetary calculations must not use floating point or silently mix currencies. |
| 2026-10-31 | Expired reservations remain committed until explicit settlement or release records the actual amount. | A worker crash or delayed provider bill must not be treated as zero cost. |
| 2026-10-31 | Keep Owner token only in React runtime memory. | Local storage and `VITE_*` variables would expose a long-lived credential to the browser bundle. |
| 2026-10-31 | Render unavailable states for APIs absent from Sprint 2. | The command center must not turn mock or inferred values into business facts. |

