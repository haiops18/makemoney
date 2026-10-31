# Original requirements and current progress

The project is a controlled, owner-operated AI business platform. It must fail closed for missing permission or budget, preserve an audit trail, prevent duplicate execution, and not perform external AI, publication, payment or customer actions without approval.

Sprint 2 must be delivered sequentially: Policy & Approval, Finance & Budget Reservation, Opportunity Discovery & Scoring, then Workflow Orchestration. A React command center is a later, API-backed interface and must never present mock data as production facts.

Current implemented checkpoint: Policy & Approval Engine (S2-M1). The next active module is Finance & Budget Reservation (S2-M2). See `PROJECT_STATUS.md` and `CODE_GRAPH.md` for verified state and code relationships.
