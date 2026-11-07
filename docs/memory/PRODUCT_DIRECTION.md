# Product direction — sinhloi.online (Owner decision 2026-11-07)

Repository: `haiops18/makemoney` · Product: **sinhloi.online** · Tagline: *Your Personal Money-Making Assistant*.
This file records the Owner's decision. It supersedes the roadmap numbering after Step 6;
it does not change Steps 4–6, which stay as released.

## A. Product direction

- **Single Owner.** Only the Owner uses the app and decides which business model is deployed.
- **Multi-business.** The app is not limited to affiliate marketing. AI researches, compares
  and proposes opportunities across many fields.
- **First priority:** Affiliate Marketing, in the Vietnam market, for the first validation
  phase. Other models go into research and backlog and must not pull resources away from it.
- **Autonomy:**
  - **Level B first.** AI researches and writes content. The Owner reviews and approves each
    item, then posts it manually.
  - **Level C later.** It opens only once Level B is stable, and only on channels the Owner
    has connected and authorised. It has per-channel daily post limits, an approval policy,
    an audit log, idempotency and an Emergency Stop. Level C is never on by default, not at
    install and not when an account is connected.
- **Domain.** The Owner is buying `sinhloi.online`. The app will be renamed and served on it
  for remote access.

## B. Core operating cycle

1. **Find opportunities.** AI researches and discovers opportunities.
2. **Choose.** Score capital, payback, risk, tax and commercial conditions. The Owner decides.
3. **Execute.** Content creation and rollout, Level B first.
4. **Measure.** Real clicks, orders, commission, cost and profit.
5. **Review & repeat.** Propose expanding or stopping, then return to step 1.

## C. Safety and financial policy (unchanged)

- Monthly budget USD 50, with a USD 5 reserve. No spending beyond the budget.
- No payments, transfers or real financial transactions by the app. Every real payment needs
  Owner approval.
- On error: stop the task, keep full logs, never run anything twice.
- Every research run follows its selected approval policy.
- Level B: the Owner approves each content item before it is used. Level C: the Owner
  approves the auto-post scope and quota. Emergency Stop blocks every later auto-post.
- API keys are encrypted in the backend and never appear in the frontend, logs or GitHub.
  A stored key does not permit paid calls by itself.
- Nothing is sent to customers, published, or allowed to affect real assets without permission.

## D. Roadmap after Step 6

| Step | Scope | Status |
|---|---|---|
| 4 Opportunity Engine | | RELEASED v27.0.0 |
| 5 Workflow Orchestration | | RELEASED v28.0.0 |
| 6 AI Brain & Research Agents | Plus v29.1.0 sign-in and v29.2.0 one-approval auto-run | RELEASED v29.0.0–v29.2.0 (verified 2026-11-07; v29.2.0 at `75f21ec`) |
| **7A AI Content & Affiliate Factory** | Campaigns, affiliate research and links, content, checks, Level B review | **NEXT** — see `docs/planning/STEP7A_ARCHITECTURE.md` |
| 7B Channel Integration & Controlled Auto-posting | Level C | After 7A |
| 8 Monetization & Tracking | | Planned |
| 9 Financial Reconciliation | | Planned |
| 10 Autonomous Optimization & Production | | Planned |

## E. Success metrics

Success is measured by:
- quality of the opportunities found;
- research and test cost;
- content the Owner approves;
- real clicks and conversions;
- confirmed orders and commission;
- money actually received;
- operating cost;
- reconciled net profit.

Counts of agents, workflows, content items or tokens are **not** success metrics on their own.
