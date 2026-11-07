# Step 7A — AI Content & Affiliate Factory: kiến trúc

Trạng thái: **ĐÃ DUYỆT, đang làm PR1** (2026-11-07). Chưa có code. Phạm vi lấy từ
`docs/memory/PRODUCT_DIRECTION.md` và đặc tả Step 7A của Owner.
Phiên bản dự kiến: **v30.0.0** (MAJOR, tính năng mới). Tag mới nhất đã kiểm tra là v29.2.0 tại `75f21ec`.

## 1. Khảo sát repository (2026-11-07)

| Hạng mục | Hiện trạng | Dùng lại ở 7A |
|---|---|---|
| Working tree | `main` sạch, trùng `origin/main`. Migration head `20261106_0019` | Nhánh mới `feat/step7a-content-factory` |
| Opportunity Engine | `opportunities` (DRAFT/RESEARCHING/EVALUATED/DISQUALIFIED/ARCHIVED), evidence, estimates, scoring | Campaign chỉ tạo được từ opportunity **EVALUATED** |
| AI Brain | `ai_research_runs` + `ai_research_sources` (Owner xác minh), prompt có phiên bản, adapter Anthropic/OpenAI/Gemini, `ai_invocations` gắn `research_run_id` NOT NULL, budget reservation, đối soát chi phí | Mỗi **lô nội dung** là một research run loại CONTENT, nên tái dùng toàn bộ chuỗi gọi AI, trần chi phí và đối soát |
| Workflow | Một workflow cho mỗi research run, chạy theo DAG, worker có lease. v29.2: một lần duyệt chạy cả workflow, có thể dừng | Lô nội dung chạy bằng workflow + auto-run sẵn có |
| Agents | Có sẵn vai trò `content` và `marketing`, chưa dùng | Vai trò `content` soạn bài, `auditor` kiểm tra |
| Điểm cần mở rộng | Hợp đồng đầu ra AI đang cố định là `ResearchOutput` (`openai_contract.research_output_schema`, `adapters`) | Tạo **registry hợp đồng đầu ra** chọn theo nhóm prompt |

**Không xây lại** Opportunity Engine, Workflow hay AI Brain. 7A chỉ thêm module `app/campaigns/`,
các bảng mới, hai nhóm prompt mới và một hook sau khi chạy xong.

## 2. Luồng Level B

```
Opportunity EVALUATED ─► CAMPAIGN (Owner tạo)
   ├─ Sản phẩm, merchant, chương trình affiliate + điều khoản có nguồn ─► Owner xác minh nguồn
   ├─ Link affiliate (Owner dán, server kiểm tra tên miền và tham số)
   └─ LÔ NỘI DUNG (Owner chọn loại, số lượng, trần chi phí)
         workflow: VALIDATE → AI_CONTENT_DRAFT (content) → AI_CONTENT_REVIEW (auditor)
         1 lần duyệt auto-run (v29.2) → worker chạy → server tạo content_items + version 1
              ▼
   DRAFT ─► CHECKED / CHECK_FAILED  (kiểm tra theo luật + AI; chưa đủ bằng chứng = NEEDS_OWNER)
         ─► IN_REVIEW ─► APPROVED ─► READY_TO_PUBLISH (server ghép link + câu công bố)
                    └─► REJECTED              ─► PUBLISHED (Owner ghi URL bài đã tự đăng)
   Owner sửa ở bất kỳ trạng thái nào trước PUBLISHED ⇒ version mới ⇒ về DRAFT, phải kiểm tra lại
```

App **không** đăng bài, **không** tải web, **không** gọi API của sàn. Thứ duy nhất ra bên
ngoài là lời gọi AI, và lời gọi đó đã nằm trong cơ chế phê duyệt + ngân sách hiện có.

## 3. Dữ liệu (migration `20261107_0020_campaigns`, chỉ tiến)

| Bảng | Cột chính | Ràng buộc |
|---|---|---|
| `campaigns` | opportunity_id, name, business_model, niche, target_audience, goal, language (`vi`/`en`), status DRAFT/ACTIVE/PAUSED/ARCHIVED, max_cost_usd, version | max_cost_usd > 0 và ≤ 45; opportunity phải EVALUATED |
| `campaign_products` | campaign_id, name, merchant, product_url, price_text, price_source_id | Giá chỉ hiển thị khi có nguồn |
| `affiliate_programs` | campaign_id, network (SHOPEE/TIKTOK_SHOP/ACCESSTRADE/ECOMOBI/OTHER), name, join_url | |
| `affiliate_program_terms` | program_id, term (COMMISSION_MODEL/RATE/COOKIE_DAYS/ATTRIBUTION/PAYOUT/REFUND_CANCEL/JOIN_CONDITIONS), value_text, value_numeric (NUMERIC), source_id, captured_at, confidence | Chỉ điều khoản có nguồn **VERIFIED** mới được AI dùng như sự thật |
| `campaign_sources` | campaign_id, source_name, source_url, excerpt, captured_at, verification_status, verified_by/at | Cùng quy tắc với `ai_research_sources` |
| `affiliate_links` | campaign_id, program_id, product_id, original_url, tracking_params (JSON), final_url, status ACTIVE/RETIRED | Tên miền trong allowlist của network; chỉ thêm tham số được phép; URL gốc giữ nguyên |
| `ai_research_runs` (+cột) | `kind` RESEARCH/CONTENT, `campaign_id` | Lô CONTENT bắt buộc có campaign; dữ liệu cũ mặc định RESEARCH |
| `content_items` | campaign_id, batch_run_id, product_id, affiliate_link_id, content_type, language, target_audience, status, current_version_id | `content_type`: REVIEW_ARTICLE, COMPARISON, VIDEO_SCRIPT, SHORT_CAPTION, SOCIAL_POST, CTA_LANDING |
| `content_versions` | content_id, version_no, title, body, hashtags, cta, claims (JSON), source_ids, author (AI invocation hoặc Owner), base_version_id | Không sửa được sau khi tạo; UNIQUE(content_id, version_no); UNIQUE(source_invocation_id, item_index) để chạy lại không tạo trùng |
| `content_checks` | version_id, check, result PASS/FAIL/NEEDS_OWNER, method RULE/AI/OWNER, note, evidence | `check`: DISCLOSURE, CLAIM_EVIDENCE, PRICE_CLAIM, PLATFORM_POLICY, DUPLICATE, MEDIA_RIGHTS, LEGAL_ADS_TAX |
| `content_publish_records` | content_id, channel, published_url, published_at, recorded_by | UNIQUE(content_id, published_url) |

Mọi thao tác thay đổi dữ liệu dùng `Idempotency-Key` và ghi `audit_events`, như các module hiện có.

## 4. AI

1. **Registry hợp đồng đầu ra.** Hiện adapter luôn dùng `research_output_schema()` và
   `validate_output()`. Sẽ đổi thành `contract_for(prompt.name)`, trả về schema và validator.
   Nhóm research giữ đúng schema cũ; có test hồi quy chứng minh request và kết quả không đổi.
2. **Nhóm prompt mới** `content_draft` và `content_review`, seed bằng migration với
   `tools: []`, `external_actions: false`, `source_access: false`.
3. **Đầu vào nội dung** (`ContentRequest`): mô tả campaign, sản phẩm, điều khoản (kèm nhãn đã
   hoặc chưa xác minh), nguồn đã xác minh và loại nội dung cần viết. Link **không** đưa cho AI.
   AI chỉ viết chỗ giữ `{{AFFILIATE_LINK}}`; khi xuất bài, server tự thay bằng link thật, nên
   AI không thể bịa hay sửa link.
4. **Đầu ra `ContentDraftOutput`**: tối đa 10 bài. Mỗi bài có loại, tiêu đề, nội dung, hashtag,
   CTA và danh sách `claims`, mỗi claim gồm phát biểu, phân loại và source_ids. Server từ chối nếu:
   - claim dẫn nguồn không có trong lô;
   - claim là FACT nhưng nguồn chưa xác minh;
   - không có `{{AFFILIATE_LINK}}`;
   - vượt giới hạn độ dài của loại nội dung.
5. **`AI_CONTENT_REVIEW`** (vai trò auditor) đối chiếu claim với nguồn và gợi ý vi phạm. Kết quả
   chỉ là **gợi ý**: AI không bao giờ tự đặt PASS cho kiểm tra cần bằng chứng hoặc cần con người.
6. **Hook sau khi chạy xong.** Khi `AI_CONTENT_DRAFT` thành công, server tạo `content_items` và
   version 1 trong cùng transaction với bước finalize. Ràng buộc UNIQUE bảo đảm chạy lại, hồi
   phục lease hay worker khởi động lại đều không tạo bản trùng.
7. **Chi phí** theo campaign và theo agent: `ai_invocations` → `ai_research_runs.campaign_id`, nhóm
   theo `agent_role`. Mỗi lô vẫn có trần riêng; tổng của campaign không vượt `campaigns.max_cost_usd`
   (kiểm tra khi tạo lô); ngân sách tháng giữ nguyên cơ chế giữ chỗ.

## 5. Kiểm tra chất lượng và tuân thủ

| Kiểm tra | Cách làm | Khi nào PASS |
|---|---|---|
| DISCLOSURE | Luật: nếu campaign có câu công bố do Owner nhập, server chèn vào bản xuất nếu thiếu. Không có câu mặc định | PASS khi có câu công bố của campaign; nếu campaign chưa có thì NEEDS_OWNER |
| CLAIM_EVIDENCE | Luật + AI: mọi claim FACT phải có nguồn VERIFIED; ESTIMATE/HYPOTHESIS phải viết rõ là ước tính | Không còn claim thiếu nguồn |
| PRICE_CLAIM | Luật: số tiền/% trong bài phải khớp giá hoặc điều khoản đã có nguồn | Khớp, hoặc Owner xác nhận |
| PLATFORM_POLICY | Luật: danh sách cụm từ cấm (cam kết chắc chắn, "100%", chữa bệnh, làm giàu nhanh...) + gợi ý AI | Không trúng luật; gợi ý AI thì Owner xem |
| DUPLICATE | Luật: so độ giống (shingle Jaccard) với các version khác trong campaign | Dưới ngưỡng 0,8 |
| MEDIA_RIGHTS | Chỉ Owner: xác nhận có quyền dùng hình ảnh/tài liệu | **Luôn NEEDS_OWNER** cho đến khi Owner xác nhận |
| LEGAL_ADS_TAX | Chỉ Owner, có checklist (quảng cáo, TMĐT, thuế khấu trừ hoa hồng) | **Luôn NEEDS_OWNER** cho đến khi Owner xác nhận |

Chỉ duyệt được khi **không có FAIL**; mọi NEEDS_OWNER phải được Owner xác nhận ngay trong
bước duyệt, kèm ghi chú. Hệ thống không bao giờ tự gắn nhãn "compliant".

## 6. API (`/api/v1/campaigns`)

- CRUD campaign; tạo từ `opportunity_id`.
- Products, programs, terms, sources (thêm/xác minh/từ chối), links (thêm/ngừng dùng).
- `POST /{id}/content-batches` với `{content_types, count, max_cost_usd}`: tạo run CONTENT, chụp lại
  bản sao nguồn đã xác minh vào lô, tạo workflow. Sau đó dùng auto-run sẵn có
  (`/workflows/{id}/auto-run-action` và `/auto-run`).
- `GET /{id}/content`, `GET /content/{cid}` (kèm các version và kết quả kiểm tra).
- `POST /content/{cid}/versions` (Owner sửa), `/checks/run`, `/checks/{check}/attest`, `/approve`, `/reject`.
- `GET /content/{cid}/export?format=text|markdown`: chỉ cho trạng thái APPROVED trở đi; ghép link
  thật và câu công bố; chuyển sang READY_TO_PUBLISH.
- `POST /content/{cid}/publish-record` với `{channel, published_url, published_at}`.
- `GET /{id}/usage`: chi phí theo lô và theo agent.

## 7. Giao diện

Trang mới **Chiến dịch**, dùng lại layout, panel và toolbar hiện có:
- Danh sách và tạo campaign từ opportunity đã đánh giá.
- Chi tiết theo tab:
  - Tổng quan
  - Sản phẩm & chương trình (điều khoản có nhãn "đã xác minh" hoặc "chưa xác minh")
  - Nguồn
  - Link
  - **Nội dung**: hàng đợi duyệt
  - Chi phí
- **Màn duyệt nội dung** dùng tốt trên điện thoại:
  - nội dung, sửa trực tiếp, lịch sử version có so sánh;
  - bảng kiểm tra kèm lý do và ô xác nhận của Owner;
  - nút Duyệt / Từ chối;
  - "Sao chép để đăng" và tải file;
  - form "Đã đăng".
- Mỗi trạng thái đều có giao diện cho: đang tải, trống, lỗi, bị khoá, thành công. Có hỗ trợ bàn
  phím và aria; selector ổn định cho E2E.

## 8. Chia PR (từng phần, mỗi PR đều có test xanh)

1. **PR1. Nền dữ liệu, chưa có AI.** Migration 0020; CRUD campaign, product, program, terms,
   sources, links; trang Chiến dịch bản cơ bản.
2. **PR2. Phần AI.** Registry hợp đồng đầu ra (có test hồi quy cho research); prompt
   `content_draft`/`content_review`; tạo lô nội dung; hook tạo nội dung; chi phí theo campaign.
3. **PR3. Level B.** Kiểm tra, sửa và version, duyệt/từ chối, xuất bài, ghi nhận đã đăng; màn duyệt.
4. **PR4. Hoàn thiện.** E2E đầy đủ, USER_GUIDE, CHANGELOG, Project Memory, rà soát bảo mật, release v30.0.0.

## 9. Kiểm thử theo tiêu chí nghiệm thu

| # | Tiêu chí | Test |
|---|---|---|
| 1 | Tạo campaign từ opportunity đã chọn | API + E2E; từ chối opportunity chưa EVALUATED hoặc đã DISQUALIFIED |
| 2 | Sản phẩm và chương trình có nguồn xác thực | Điều khoản không nguồn hoặc chưa xác minh không vào ContentRequest như sự thật |
| 3 | Nhiều loại nội dung | Provider giả trả về 6 loại; kiểm tra schema và độ dài |
| 4 | Có nguồn và link | Claim dẫn nguồn lạ hoặc FACT chưa xác minh bị từ chối; bản xuất chứa đúng link đã gắn |
| 5 | Kiểm tra chất lượng và công bố | Từng luật có test trúng/trượt; MEDIA_RIGHTS/LEGAL không bao giờ tự PASS |
| 6 | Xem, sửa, duyệt, từ chối | Chuyển trạng thái hợp lệ và không hợp lệ; sửa thì về DRAFT |
| 7 | Xuất để tự đăng | Chỉ xuất khi APPROVED; có câu công bố |
| 8 | Audit và lịch sử version | Version không sửa được; mỗi thao tác có audit_event |
| 9 | Chi phí theo campaign và agent | Tổng khớp `ai_invocations`; vượt trần campaign thì không tạo được lô |
| 10 | Không đăng bài hay thanh toán | Không có client HTTP nào ngoài adapter AI; test xác nhận module campaigns không mở kết nối mạng |
| 11 | Chạy lại không tạo trùng | Trùng Idempotency-Key, finalize lại, hồi phục lease → không trùng content/version/publish record |
| 12 | Các gate | lint, typecheck, unit, integration PostgreSQL, Playwright, build, npm audit, pip-audit, CI |

## 10. Quyết định của Owner (2026-11-07)

1. Vá bảo mật cổng 3000/8000 và giới hạn đăng nhập: **để sau**, chưa làm trong 7A (vẫn ghi ở KNOWN_ISSUES).
2. Campaign nghiệm thu đầu tiên: **Shopee Affiliate thời trang nữ, kênh Facebook/Reels**.
3. **Không có câu công bố mặc định**. Mỗi campaign có trường `disclosure_text` tuỳ chọn do Owner nhập.

## 11. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Đổi hợp đồng đầu ra làm hỏng pipeline research | Registry giữ nguyên schema research; test hồi quy so request và kết quả trước/sau |
| AI bịa thông số sản phẩm hoặc hoa hồng | Claim FACT bắt buộc có nguồn VERIFIED; AI không thấy link; kiểm tra PRICE_CLAIM |
| Nội dung vi phạm quảng cáo hoặc bản quyền | Kiểm tra theo luật + Owner bắt buộc xác nhận MEDIA_RIGHTS/LEGAL; không tự đăng |
| Chi phí AI | Trần theo lô và campaign + giữ chỗ ngân sách tháng 50 USD; auto-run dừng khi bị từ chối |
| Phạm vi phình to | Một campaign end-to-end trước; giao diện chỉ những gì tiêu chí 1–12 cần |
