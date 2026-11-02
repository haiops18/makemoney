# AUTO MONEY AI — yêu cầu gốc và hiện trạng

> Cập nhật: 2026-10-31 (Asia/Ho_Chi_Minh). Tài liệu này phản ánh code và Docker stack đang có, không phải roadmap giả định.

## 1. Mục đích gốc

AUTO MONEY AI là nền tảng kinh doanh AI tự chủ có kiểm soát cho một Owner. Hệ thống được phép tự nghiên cứu, phân tích, tạo mã và thử nghiệm trong sandbox. Mọi hành động có thể phát sinh chi phí ngoài hạn mức, giao tiếp khách hàng, xuất bản công khai, thanh toán hoặc tác động tới tài sản thật phải bị chặn cho đến khi policy, ngân sách và phê duyệt của Owner xác nhận.

Mục tiêu là đo được chất lượng cơ hội, chi phí thử nghiệm, khách hàng thật và doanh thu/lợi nhuận đã đối soát; không dùng số lượng agent, sản phẩm hay token làm thước đo thành công.

### Mục tiêu 90 ngày

1. Ngày 1–30: hoàn thiện nền tảng và ghi nhận ít nhất 30 cơ hội kèm dữ liệu đánh giá.
2. Ngày 31–60: có 1–3 thử nghiệm/sản phẩm được Owner phê duyệt để công khai.
3. Ngày 61–90: đo traffic, conversion, chi phí và doanh thu thật để quyết định tiếp tục hoặc dừng.

Đây là mục tiêu vận hành và đo lường, không phải cam kết lợi nhuận.

## 2. Yêu cầu kiến trúc và kiểm soát gốc

- Backend FastAPI theo mô hình modular monolith trước; PostgreSQL là nguồn dữ liệu chuẩn; Redis/Celery dành cho queue MVP.
- UI React + TypeScript, song ngữ Việt/Anh; Docker Compose trên Linux trước, Kubernetes khi mở rộng.
- Mỗi hành động phải truy vết được từ cơ hội → kế hoạch → phê duyệt → thực thi → kết quả; retry không được tạo giao dịch hoặc chi phí trùng.
- Least privilege và fail closed: không rõ quyền, ngân sách hay approval thì từ chối thực thi.
- Bảy vai trò logic: AI CEO, Research, Finance, Developer, Content, Marketing, Auditor. Chúng không phải bảy model chạy liên tục.
- Mỗi tháng giới hạn ngân sách $50 theo `Asia/Ho_Chi_Minh`, cảnh báo tại 50/75/90%, giữ dự phòng $5, chặn chi phí tránh được ở 100%. Hard cap thực sự cần budget reservation nguyên tử trong PostgreSQL và đối soát hóa đơn nhà cung cấp.
- Tài chính phải phân biệt projected/pending/confirmed revenue, received cash, refund và operating cost. Tiền dùng `NUMERIC`; ledger bất biến; không xem AI output hoặc số dư ví là doanh thu đã xác minh.
- Risk pháp lý, bản quyền hay chính sách nền tảng nghiêm trọng là điều kiện loại trực tiếp cho cơ hội.
- Public action, publication và payment phải yêu cầu Owner approval; approval phải gắn với hash chính xác của hành động.

## 3. Các module mục tiêu

| Chặng | Module chính | Trạng thái |
| --- | --- | --- |
| Sprint 1 | Foundation: infrastructure, auth, audit, agent registry, dashboard cơ bản, CI | Đã làm phần control plane tối thiểu |
| Sprint 2 | Opportunity Discovery, Finance/Budget Reservation, Approval Center, orchestration | Chưa triển khai |
| Sprint 3 | Codex Developer Agent, sandbox, build/test/security scan, preview | Chưa triển khai |
| Sprint 4 | Content/marketing, payment/affiliate được phép, analytics, reconciliation | Chưa triển khai |
| Sprint 5 | Production hardening, backup/recovery, metrics/alerts, cost optimization | Chưa triển khai |

## 4. Hiện trạng code đã đối chiếu

Phần này được đối chiếu bằng `rg` trên route, model, migration, Docker Compose và test vào ngày cập nhật.

### Đã có

- FastAPI chạy tại cổng `8000`; `/` chuyển hướng `307` sang `/docs`.
- Health endpoints: `GET /health/live` và `GET /health/ready`.
- Toàn bộ `/api/v1/*` dùng bearer token của Owner. Production từ chối hai giá trị API key mẫu.
- API hiện hữu:
  - `GET /api/v1/dashboard`: tổng agent, agent enabled, audit 24 giờ, ngân sách cấu hình, timezone.
  - `GET /api/v1/agents`: danh sách agent.
  - `PATCH /api/v1/agents/{id}`: bật/tắt agent, bắt buộc `Idempotency-Key`, có audit event và chặn dùng lại key cho request khác.
  - `GET /api/v1/audit-events`: lịch sử audit giới hạn 1–100 mục.
  - `GET /api/v1/settings`: khẳng định external execution đang bị tắt.
- PostgreSQL migration `20261030_0001` tạo ba bảng: `agents`, `audit_events`, `idempotency_records`; seed 7 agent theo yêu cầu gốc.
- Docker Compose chạy `postgres:16-alpine`, `redis:7-alpine` và backend; backend đợi dependency healthy và `restart: on-failure:5` để chịu lỗi khởi động database ngắn hạn.
- CI GitHub Actions chạy `pytest` từ thư mục `backend`.
- Test hiện có kiểm tra: auth bắt buộc, redirect root, audit + idempotency, từ chối reuse idempotency key và từ chối API key mẫu trong production.

### Trạng thái runtime đã kiểm tra

Khi cập nhật tài liệu này:

- `makemoney-backend-1` đang chạy và publish `0.0.0.0:8000`.
- PostgreSQL và Redis đang healthy.
- `/health/ready` trả `200`.
- Dashboard được xác thực trả 7 tổng agent, 7 enabled, $50 cấu hình và `external_execution_enabled: false`.

## 5. Chưa có — không được hiểu là đã hỗ trợ

- Không có OpenAI API, Codex, tool calling, agent runs, scheduler hay Celery worker đang hoạt động.
- Không có Opportunity Engine, nguồn bằng chứng, scoring, ROI scenario hoặc discovery tự động.
- Không có policy engine, approval request, workflow state machine, task queue, retry/cancellation hoặc recovery workflow.
- Không có budget account/reservation, usage record, ledger, financial transaction, reconciliation hay enforcement $50.
- Không có sandbox cô lập, code execution, security scan, preview product, payment, affiliate, publication, email hay giao tiếp khách hàng.
- Không có React dashboard, i18n UI, Prometheus/Grafana, tracing, alert hoặc Kubernetes manifests.
- Không có authentication nhiều người dùng/RBAC; implementation hiện tại là một Owner bearer token.

Vì các module trên chưa có, hệ thống hiện tại không được phép được mô tả là nền tảng tự kiếm tiền, tự xuất bản, hay có hard budget cap.

## 6. Quyết định vận hành hiện tại

1. Chỉ dùng stack hiện tại cho local development/control-plane validation.
2. Không đưa API ra Internet khi còn dùng `.env.example`; bắt buộc tạo `.env` và thay `OWNER_API_KEY`, password PostgreSQL trước khi expose.
3. Không thêm AI execution trước khi hoàn tất theo thứ tự: Policy + Approval → Budget Reservation → Opportunity/Finance → Orchestrator.
4. Giữ PostgreSQL là record chuẩn cho mọi dữ liệu kinh doanh; Redis không được dùng làm nguồn sự thật.

## 7. Việc kế tiếp nhỏ nhất, đúng yêu cầu

Sprint tiếp theo nên chỉ xây bốn module control bắt buộc trước external execution:

1. `policies` và `approvals`: action hash, expiry, approve/reject, audit.
2. `finance`: budget account, reservation nguyên tử bằng transaction PostgreSQL, usage/cost record.
3. `opportunities`: opportunity, evidence, estimate/scenario và scoring có rule loại trực tiếp.
4. `orchestration`: workflow/task state machine chỉ tạo công việc nội bộ, fail closed khi thiếu approval hoặc budget.

Sau khi bốn phần trên có migration, API và test đồng thời, mới xem xét OpenAI/Codex và sandbox.

## 8. FE-P2 Command Center quality — 2026-10-31

- Frontend control-plane was enhanced with complete Vietnamese/English copy, responsive UI states, confirmation dialogs, filtering/search and API-backed finance cost/usage presentation.
- The unavailable Opportunity, Project and Workflow states remain explicit because their backend APIs are still absent.
- Verified locally: lint, typecheck, production build, four component tests, 13 backend tests (two PostgreSQL integration tests skipped), Docker `/health/ready` and frontend HTTP response.
- Release remains blocked: browser E2E could not be run because no browser session is available, and GitHub CLI has no authenticated account; no tag or release was created.

# Step 4 release candidate — 2026-11-02

Opportunity engine candidate v27.0.0 is on PR #2. Local gates: 32 backend,
10 frontend and 2 Playwright tests passed; isolated PostgreSQL migration,
constraints/concurrency and Docker runtime verified. Dependency audits and
scoped secret/diff checks passed (12 moderate frontend dev-tool findings remain).
Final remote CI/merge/tag/release pending. This is not a COMPLETED claim.

