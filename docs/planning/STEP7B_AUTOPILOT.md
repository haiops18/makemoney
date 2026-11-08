# Step 7B — Autopilot (Owner direction 2026-11-08)

Owner goal (verbatim intent): "Anh cung cấp token, sinhloi.online tự đi tìm các hướng kiếm
tiền, đánh giá khả năng thành công và thu nhập, anh phê duyệt rồi app tự động làm."

Owner decisions 2026-11-08:
1. The Owner chooses the search source and enters its token (Tavily or Brave Search).
2. The Owner already has the accounts. The app offers one screen to enter them once,
   stored encrypted in the Owner profile (Integrations).
3. Content that passes every check is *proposed* for approval. After approval, posting
   follows a schedule automatically (Facebook Page). Nothing posts without that approval.

Unchanged: budget 50 USD/month (5 USD reserve), fail closed, secrets encrypted and never
returned, every action idempotent and audited, Owner is the only decision maker.

## Flow

1. **Discover** (PR-B): the Owner picks a field and clicks "Tìm cơ hội". The app runs a
   bounded set of web searches through the Owner's search integration, stores each result
   as an AI-collected source (title, URL, snippet), and runs the existing research pipeline
   on one approval (auto-run). Output: a ranked list with estimated monthly income
   (low/base/high), cost, time to first income, success likelihood, risks and citations.
2. **Approve** (PR-B/C): "Duyệt & triển khai" creates the opportunity and an affiliate
   campaign. With ACCESSTRADE, the app pulls approved campaigns and top products and
   creates tracking links (PR-C).
3. **Produce** (PR-C): content batches run automatically; items that pass every rule check
   are queued as "Đề xuất" for the Owner (media rights and ads/tax confirmed once per
   campaign by the Owner).
4. **Post on schedule** (PR-D): approved items get slots (posts per day, hours). A worker
   publishes to the Facebook Page via Graph API at the slot time and stores the publish
   record. Pause/stop at any time; any error stops the queue.
5. **Track** (PR-E): pull ACCESSTRADE orders (pub_commission, status) by utm_content and
   compare real income with the estimate.

## PRs

- **PR-A Integrations profile**: `integrations` table (kind, label, non-secret config,
  encrypted secret), API `/api/v1/integrations` (write-only secret, connection test),
  UI page "Kết nối". Kinds: SEARCH_TAVILY, SEARCH_BRAVE, ACCESSTRADE, FACEBOOK_PAGE.
  Fixed hosts: api.tavily.com, api.search.brave.com, api.accesstrade.vn, graph.facebook.com.
- **PR-B Discovery**: search runs, AI-collected sources, auto-run, ranking page.
- **PR-C ACCESSTRADE products and links, proposal queue.**
- **PR-D Scheduled Facebook posting** (Level C, after approval only).
- **PR-E Revenue tracking.**

Verified API facts (2026-11-08):
- ACCESSTRADE: `Authorization: Token <key>`; `GET https://api.accesstrade.vn/v1/campaigns`,
  `POST /v1/product_link/create`, `GET /v1/top_products`, `GET /v1/order-list`
  (10 req/min).
- Facebook: `POST https://graph.facebook.com/v26.0/{page_id}/feed` with a Page token
  (pages_manage_posts), `message`, `link`.
- Tavily: `POST https://api.tavily.com/search`, `Authorization: Bearer`. Brave:
  `GET https://api.search.brave.com/res/v1/web/search`, `X-Subscription-Token`.
- Shopee Affiliate Open API for Vietnam: no official documentation was found, so it is
  deferred. ACCESSTRADE covers Shopee campaigns.

Version: v31.0.0 (MAJOR) when PR-A–PR-D are released; check tags first.
