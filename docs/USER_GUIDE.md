# Hướng dẫn sử dụng sinhloi.online (v30.0.0)

Tài liệu dành cho Owner (người vận hành hệ thống). Hướng dẫn đi từ lúc đăng nhập đến khi chạy xong một lượt
nghiên cứu AI 7 giai đoạn, tạo cơ hội kinh doanh và đối soát chi phí. Tên nút và tên trang trong tài liệu
được ghi đúng như trên giao diện tiếng Việt (bấm nút ngôn ngữ trên thanh trên cùng để đổi VI/EN).

> Không ghi mật khẩu, API key hay secret vào tài liệu này hoặc bất kỳ file nào trong Git.

## Mục lục

1. [Nguyên tắc hoạt động](#1-nguyên-tắc-hoạt-động)
2. [Truy cập và đăng nhập](#2-truy-cập-và-đăng-nhập)
3. [Chuẩn bị trước khi dùng AI](#3-chuẩn-bị-trước-khi-dùng-ai)
4. [Cài đặt một lần](#4-cài-đặt-một-lần)
5. [Chạy một lượt nghiên cứu AI](#5-chạy-một-lượt-nghiên-cứu-ai)
6. [Tạo cơ hội từ báo cáo](#6-tạo-cơ-hội-từ-báo-cáo)
7. [Theo dõi và đối soát chi phí](#7-theo-dõi-và-đối-soát-chi-phí)
8. [Các trang khác](#8-các-trang-khác)
9. [Xử lý lỗi thường gặp](#9-xử-lý-lỗi-thường-gặp)
10. [Vận hành server](#10-vận-hành-server)
11. [Hạn chế đã biết](#11-hạn-chế-đã-biết)

---

## 1. Nguyên tắc hoạt động

Hệ thống được thiết kế để **không bao giờ tự tiêu tiền hoặc tự hành động**. Mỗi lần gọi AI trả phí cần đủ:

| Điều kiện | Ở đâu |
| --- | --- |
| Quyền AI toàn cục đang bật | Cài đặt → Quyền AI toàn cục |
| Provider đã bật, có API key, endpoint chính thức | Cài đặt → Quản lý AI provider |
| Giá model do Owner nhập và đã có hiệu lực | Cài đặt → Cấu hình giá |
| Cấu hình model cho agent của giai đoạn đó đã bật | Cài đặt → Model theo agent |
| Một phê duyệt **chạy tự động** cho cả workflow, hoặc phê duyệt riêng cho từng task (dùng một lần) | Workflow → **Phê duyệt & chạy tự động** (hoặc Yêu cầu duyệt task) |
| Ngân sách tháng còn đủ để giữ chỗ | Tự động (Tài chính & Ngân sách) |

Thêm vào đó:

- Hệ thống **không tự lên mạng tìm nguồn**. AI chỉ đọc nguồn và trích đoạn do Owner nhập.
- Mỗi task AI chỉ gửi **một** request tới provider, không tự retry, không đổi provider dự phòng.
- Kết quả AI là **phân tích chưa xác minh**. Một FACT chỉ được coi là có căn cứ khi trích dẫn nguồn Owner đã xác minh.
- Chi phí tính theo token chỉ là **ước tính**. Chi phí xác nhận là số Owner đối soát với hóa đơn provider.
- Ngân sách mặc định: **50 USD/tháng**, giữ lại **5 USD** dự phòng (dùng tối đa 45 USD). Tài khoản ngân sách
  của tháng mới được tạo tự động.

## 2. Truy cập và đăng nhập

| Cách truy cập | Địa chỉ |
| --- | --- |
| Trên chính server | `http://localhost:3000` |
| Từ máy khác trong mạng được phép | `http://<IP-server>:3000` |
| API backend (tài liệu API) | `http://<IP-server>:8000/docs` |

Mở địa chỉ trên, màn hình **Đăng nhập Owner** hiện ra:

1. Nhập **Tên đăng nhập Admin** và **Mật khẩu Admin**.
2. Tích **Ghi nhớ đăng nhập** nếu đang dùng máy cá nhân.
3. Nhấn **Enter** (hoặc bấm **Đăng nhập**).

| Tùy chọn | Hành vi |
| --- | --- |
| Có tích **Ghi nhớ đăng nhập** | Giữ đăng nhập trên trình duyệt này kể cả khi tải lại trang, mở tab mới hoặc tắt trình duyệt, cho đến khi hết hạn hoặc bấm **Đăng xuất**. Lần sau tên đăng nhập được điền sẵn |
| Không tích | Giữ đăng nhập khi tải lại trang (F5) trong cùng tab; đóng tab hoặc mở tab mới phải đăng nhập lại |

- Phiên đăng nhập hết hạn sau **12 giờ** (`SESSION_TTL_MINUTES=720` trong `.env`). Khi hết hạn, hoặc khi server từ
  chối phiên (ví dụ sau khi đổi `SESSION_SECRET`), hệ thống tự quay về màn hình đăng nhập.
- User và mật khẩu lấy từ `ADMIN_USERNAME` / `ADMIN_PASSWORD` trong file `.env` trên server
  (xem bằng `grep ADMIN_ /đường-dẫn/makemoney/.env`).
- Chỉ dùng **Ghi nhớ đăng nhập** trên máy cá nhân. Trên máy dùng chung, không tích và bấm **Đăng xuất** khi xong.

## 3. Chuẩn bị trước khi dùng AI

Chuẩn bị sẵn:

1. **API key** của ít nhất một provider: OpenAI, Anthropic hoặc Google Gemini. Nên tạo key riêng cho hệ thống
   này và đặt **giới hạn chi tiêu** ngay trên trang quản lý của provider, như một lớp bảo vệ thứ hai.
2. **Model ID** chính xác, ví dụ `gpt-4.1-mini`, `claude-sonnet-4-5`, `gemini-2.5-flash`. Kiểm tra tên trên
   trang tài liệu của provider.
3. **Giá model**: USD cho 1 triệu token input và 1 triệu token output, cùng link trang giá chính thức.
4. **Nguồn nghiên cứu**: các đoạn văn bản (báo cáo, bài viết, số liệu) mà anh/chị muốn AI phân tích, kèm tên nguồn.

## 4. Cài đặt một lần

Tất cả các bước trong phần này nằm ở trang **Cài đặt** (menu bên trái), trừ bước phê duyệt.

### 4.1. Thêm AI provider

Phần **Quản lý AI provider** → khung **Thêm provider**:

| Ô | Nhập gì |
| --- | --- |
| Tên | Tên tùy ý, ví dụ `OpenAI chính` |
| Provider | `OPENAI`, `ANTHROPIC` hoặc `GEMINI` |
| Model ID | Model mặc định, ví dụ `gpt-4.1-mini` |
| Base URL | **Để trống** (dùng endpoint chính thức) |
| API key | Dán API key |

Bấm **Lưu**. Dòng provider phải hiện **Đã lưu khóa** và **Adapter đã xác minh**.

- **Không** chọn `OPENAI_COMPATIBLE` và **không** nhập Base URL tùy chỉnh: hệ thống chặn các cấu hình này khi chạy
  (dòng provider sẽ hiện **Không hỗ trợ thực thi**).
- API key được mã hóa bằng `AI_CREDENTIALS_KEY` trong `.env` và không bao giờ hiển thị lại. Muốn đổi key thì bấm
  **Sửa** rồi nhập key mới; muốn xóa thì bấm **Thu hồi khóa**.

Sau đó trên dòng provider:

1. Bấm **Bật cấu hình** (provider bị tắt thì không task nào chạy được).
2. Nếu có nhiều provider, bấm **Chọn mặc định** cho provider chính.

### 4.2. Nhập giá model

Trên dòng provider, bấm **Cấu hình giá**. Khung **Giá model do Owner nhập** mở ra:

| Ô | Nhập gì |
| --- | --- |
| Model ID của giá | **Trùng chính xác** Model ID sẽ dùng cho agent |
| Phiên bản giá | Ví dụ `2026-11` |
| USD / 1 triệu input token | Theo trang giá provider, ví dụ `0.40` |
| USD / 1 triệu output token | Theo trang giá provider, ví dụ `1.60` |
| Hiệu lực từ (giờ thiết bị) | Một thời điểm **trước hiện tại** |
| Ghi chú nguồn giá | Link trang giá chính thức |

Bấm **Lưu giá**. Mỗi lần lưu tạo một phiên bản giá mới; giá cũ không bị sửa. Nếu dùng nhiều model khác nhau cho
các agent, nhập giá cho **từng** model.

> Giá được **ghim** vào từng giai đoạn AI lúc bấm **Thêm giai đoạn AI** (mục 5.3). Nhập giá trước bước đó.

### 4.3. Cấu hình model cho agent

Phần **Model theo agent**. Một lượt nghiên cứu dùng 4 agent:

| Agent | Vai trò | Giai đoạn đảm nhận |
| --- | --- | --- |
| Research Agent | `research` | Kế hoạch nghiên cứu, Nghiên cứu thị trường, Phân tích đối thủ |
| AI CEO | `ceo` | Đề xuất cơ hội, Báo cáo cuối |
| Finance Agent | `finance` | Phân tích tài chính |
| Auditor Agent | `auditor` | Rà soát rủi ro |

Làm lần lượt cho **cả 4 agent**:

| Ô | Nhập gì |
| --- | --- |
| Agent | Chọn agent |
| Provider | Chọn provider đã thêm |
| Model ID của agent | Model sẽ dùng (phải có giá ở mục 4.2) |
| Token đầu ra tối đa | Ví dụ `4000` |
| Temperature | **Để trống** (nếu nhập, task sẽ bị chặn) |
| Timeout (giây) | Ví dụ `120` |
| Chi phí tối đa mỗi lần (USD) | Ví dụ `0.50` (tối đa `45`) |
| Bật cấu hình agent | **Tích chọn** |

Bấm **Lưu cấu hình agent**.

- "Chi phí tối đa mỗi lần" là trần cho **một** lần gọi. Trước khi chạy, hệ thống ước tính chi phí tối đa (kích thước
  request + token đầu ra tối đa × giá). Nếu ước tính vượt trần, task bị từ chối thay vì chạy.

### 4.4. Bật quyền AI toàn cục

Phần **Quyền AI toàn cục**:

1. Bấm **Yêu cầu phê duyệt quyền AI** và xác nhận.
2. Vào trang **Phê duyệt**, mở yêu cầu "Owner xem xét quyền AI toàn cục", nhập lý do và bấm **Phê duyệt**.
3. Quay lại **Cài đặt**, bấm **Bật quyền AI** và xác nhận. Trạng thái **Thực thi AI** chuyển sang
   "Có thể yêu cầu theo từng task".

Bật quyền toàn cục **không** tự chạy gì cả và không cấp ngân sách; từng task vẫn cần phê duyệt riêng. Muốn dừng toàn
bộ AI ngay lập tức, bấm **Tắt quyền AI** (các yêu cầu cũ cũng bị vô hiệu).

### 4.5. Kiểm tra kết nối (tùy chọn, miễn phí)

Sau khi bật quyền AI, trên dòng provider bấm **Kiểm tra kết nối**. Hệ thống gửi key tới endpoint chính thức để
**liệt kê model**, không gửi prompt và không phát sinh chi phí suy luận. Kết quả hiển thị ở **Kiểm tra gần nhất**:

| Kết quả | Ý nghĩa |
| --- | --- |
| `OK` | Key hợp lệ |
| `OK · model không có trong danh sách` | Key hợp lệ nhưng Model ID sai hoặc tài khoản chưa có quyền dùng model đó |
| `AUTH_FAILED` | Key sai hoặc đã bị thu hồi |
| `RATE_LIMITED` | Provider đang giới hạn tần suất, thử lại sau |
| `UNREACHABLE` | Server không kết nối được tới provider (mạng, DNS, tường lửa) |
| `PROVIDER_ERROR` / `INVALID_RESPONSE` | Lỗi phía provider, thử lại sau |

## 5. Chạy một lượt nghiên cứu AI

### 5.1. Tạo yêu cầu nghiên cứu

Trang **Nghiên cứu AI** → **Tạo yêu cầu nghiên cứu**:

| Ô | Nhập gì |
| --- | --- |
| Mục tiêu nghiên cứu | Câu hỏi cụ thể, ví dụ "Đánh giá cơ hội bán khóa học tiếng Anh online cho người đi làm tại Hà Nội" |
| Danh mục | Ví dụ `Giáo dục` |
| Thị trường mục tiêu | Ví dụ `Việt Nam` |
| Khách hàng mục tiêu | Ví dụ `Nhân viên văn phòng 25–35 tuổi` |
| Chi phí tối đa (USD) | Trần cho **mỗi** lần gọi AI của lượt này, tối đa `45` |

Bấm **Tạo bản nháp**.

### 5.2. Nhập và xác minh nguồn

Chọn yêu cầu vừa tạo, ở phần **Nguồn Owner nhập**:

1. Nhập **Tên nguồn** và **Trích đoạn** (đoạn văn bản thật từ nguồn), bấm **Thêm nguồn**. Tối đa 20 nguồn.
2. Với từng nguồn, nhập **Ghi chú xác minh** (ví dụ "Đã đối chiếu với báo cáo gốc") và bấm:
   - **Xác minh**: nguồn đáng tin, AI được dùng làm căn cứ cho FACT;
   - **Từ chối**: nguồn không dùng, không gửi cho AI.

Quyết định xác minh **không thể thay đổi**. Nguồn chưa xác minh vẫn được gửi cho AI nhưng chỉ làm căn cứ cho
giả thuyết, không cho FACT.

### 5.3. Tạo workflow và thêm giai đoạn AI

Vẫn ở trang **Nghiên cứu AI**:

1. Nhập **Tên workflow nghiên cứu** và bấm **Tạo workflow nghiên cứu**.
2. Ở phần **Các giai đoạn AI**, bấm **Thêm giai đoạn AI**. Hệ thống thêm 7 giai đoạn vào workflow (việc này **chưa
   chạy AI**):

| # | Giai đoạn | Agent | Chạy sau |
| --- | --- | --- | --- |
| 1 | Kế hoạch nghiên cứu | Research | — |
| 2 | Nghiên cứu thị trường | Research | 1 |
| 3 | Phân tích đối thủ | Research | 1 |
| 4 | Đề xuất cơ hội | AI CEO | 2, 3 |
| 5 | Phân tích tài chính | Finance | 4 |
| 6 | Rà soát rủi ro | Auditor | 4 |
| 7 | Báo cáo nghiên cứu | AI CEO | 5, 6 |

Nếu bước này báo lỗi, kiểm tra lại: đủ cấu hình cho 4 agent đã bật (mục 4.3) và có giá có hiệu lực cho đúng Model ID
(mục 4.2).

### 5.4. Phê duyệt một lần và chạy tự động (khuyến nghị)

Trước khi bắt đầu, bản nháp nghiên cứu phải có **ít nhất 1 nguồn** (mục 5.2) và đã **Thêm giai đoạn AI** (mục 5.3).

Bấm **Mở Workflow** (hoặc vào trang **Workflow** và chọn workflow vừa tạo):

1. Ở khung **Chạy tự động**, bấm **Phê duyệt & chạy tự động**.
2. Hộp xác nhận hiển thị:
   - số bước, trong đó bao nhiêu bước gọi AI có trả phí;
   - model sẽ dùng;
   - số nguồn;
   - **trần chi phí** của cả lượt nghiên cứu.

   Đọc kỹ rồi bấm **OK**. Đây là **lần phê duyệt duy nhất**.
3. Hệ thống tự gửi và duyệt yêu cầu workflow, bấm **Bắt đầu**, rồi bật chạy tự động. Trạng thái chuyển thành
   **đang chạy tự động**.
4. Worker tự xếp hàng từng bước theo thứ tự ở bảng trên. Bước sau chỉ chạy khi bước trước **thành công**. Bước 3 và
   bước 4 trong bảng có thể chạy gần như song song. Cả 8 bước (kể cả bước kiểm tra bản nháp) thường xong trong vài phút.

Ở **mỗi bước**, các kiểm soát vẫn áp dụng như khi chạy tay: quyền AI toàn cục, chính sách AI, giữ chỗ ngân sách, trần
chi phí của lượt nghiên cứu và trần chi phí mỗi lần của agent. Chạy tự động **tự dừng** và không chạy bước tiếp theo
khi:

- có bước bị lỗi (workflow chuyển `FAILED`). Hệ thống **không tự chạy lại** request trả phí;
- sau khi duyệt, anh/chị thêm hoặc xác minh nguồn, sửa model, giá, provider, API key hoặc chính sách. Khi đó cần bấm
  **Phê duyệt & chạy tự động** lại;
- chạm trần chi phí hoặc ngân sách tháng;
- workflow bị hủy, hoặc đã quá **12 giờ** kể từ lúc duyệt;
- anh/chị bấm **Dừng chạy tự động**. Bước đang chạy (nếu có) vẫn hoàn tất.

Lý do dừng hiện ngay ở khung **Chạy tự động**. **Tạm dừng** workflow sẽ ngưng xếp hàng bước mới; **Tiếp tục** thì
chạy tiếp.

### 5.4b. Phê duyệt và chạy từng task (thủ công)

Dùng khi muốn xem từng bước trước khi chạy bước sau:

1. Ở ô **Chính sách**, chọn `owner-controlled-internal`.
2. Bấm **Gửi phê duyệt**, rồi vào trang **Phê duyệt** để duyệt yêu cầu workflow.
3. Quay lại workflow, bấm **Bắt đầu**.
4. Với từng giai đoạn ở trạng thái `READY` (theo thứ tự ở bảng trên):
   1. Bấm **Yêu cầu duyệt task** và xác nhận. Với giai đoạn AI, hệ thống tự dùng chính sách
      `ai-inference-controlled` (hiện dòng **Chính sách AI** ngay dưới task); ô **Chính sách** ở trên chỉ áp dụng
      cho task nội bộ.
   2. Vào **Phê duyệt**, kiểm tra **Chi phí ước tính** và nội dung yêu cầu, nhập lý do, bấm **Phê duyệt**.
      Phê duyệt có hạn **15 phút** và chỉ dùng được một lần.
   3. Quay lại, bấm **Chạy task**. Worker gửi đúng một request tới provider. Kết quả hiện trong
      **Lịch sử thực thi** và ở phần **Các giai đoạn AI** của trang Nghiên cứu AI.

Giai đoạn sau chỉ chạy được khi giai đoạn trước đã **thành công**. Nếu một giai đoạn thất bại hoặc không rõ kết quả,
các giai đoạn phụ thuộc bị chặn; xem chi phí của lần gọi đó ở trang **Chi phí AI** và đối soát (mục 7).

### 5.5. Đọc kết quả

Phần **Các giai đoạn AI** (trang Nghiên cứu AI) hiển thị từng giai đoạn với tóm tắt, các phát hiện được gắn nhãn
`FACT` / `ESTIMATE` / `HYPOTHESIS` / `UNKNOWN`, giả định và nguồn trích dẫn, cùng chi phí **Ước tính**,
**Theo token** và **Đã xác nhận**.

Cách đọc:

- `FACT` chỉ đáng tin khi trích dẫn nguồn anh/chị đã **Xác minh**.
- `ESTIMATE` phải đi kèm giả định; luôn đọc giả định trước khi dùng con số.
- Kết quả của giai đoạn trước là do AI tạo ra, **không phải bằng chứng**.

## 6. Tạo cơ hội từ báo cáo

Khi workflow ở trạng thái `COMPLETED` và đã có báo cáo cuối, phần **Tạo cơ hội từ báo cáo** xuất hiện:

1. Nhập **Tiêu đề cơ hội** và **Mô hình kinh doanh**.
2. Bấm **Tạo cơ hội**, rồi **Mở cơ hội**.

Mỗi lượt nghiên cứu chỉ tạo được **một** cơ hội. Cơ hội được tạo ở trạng thái **bản nháp**, gắn nhãn nguồn gốc AI kèm
cảnh báo. Các nguồn không bị từ chối trở thành bằng chứng của cơ hội. Việc chấm điểm và quyết định vẫn do Owner thực
hiện ở trang **Cơ hội**.

### 6.1. Chiến dịch affiliate

Trang **Chiến dịch** biến một cơ hội đã đánh giá thành chiến dịch affiliate. Ở bước này
app chỉ **lưu và chuẩn bị** dữ liệu: không tự đăng bài, không mở link, không thanh toán.
AI soạn nội dung ở mục 6.2, duyệt và xuất bài (Level B) ở mục 6.3.

1. **Tạo chiến dịch.** Chọn một cơ hội ở trạng thái *đã đánh giá* (cơ hội bị loại hoặc
   chưa chấm điểm không dùng được), nhập tên, ngách, khách hàng mục tiêu, mục tiêu và trần
   chi phí AI (tối đa 45 USD).
2. **Tổng quan.**
   - Nhập **câu công bố affiliate** nếu muốn. Mặc định không có sẵn câu nào.
   - Đổi trạng thái: Kích hoạt / Tạm dừng / Lưu trữ. Chiến dịch đã lưu trữ chỉ xem được.
3. **Nguồn.**
   - Thêm nguồn kèm đoạn trích và ngày thu thập.
   - Xác minh hoặc từ chối từng nguồn, kèm ghi chú. Quyết định này không đổi được.
4. **Chương trình & điều khoản.**
   - Thêm chương trình (Shopee, TikTok Shop, ACCESSTRADE...) cùng **tên miền link được
     phép**, ví dụ `s.shopee.vn, shope.ee`, và các **tham số theo dõi** app được thêm vào
     link, ví dụ `sub_id`.
   - Ghi các điều khoản như hoa hồng, trần hoa hồng, cookie, thời điểm trả tiền, điều
     kiện huỷ đơn hay thuế khấu trừ. Nên chọn nguồn cho từng điều khoản.
   - Mỗi điều khoản có nhãn *Nguồn đã xác minh* / *chưa xác minh* / *Chưa có nguồn*.
     Chỉ điều khoản có nguồn đã xác minh mới được dùng như sự thật.
5. **Sản phẩm.** Nếu nhập giá thì bắt buộc chọn nguồn của giá.
6. **Link affiliate.**
   - Dán link anh/chị lấy từ trang của sàn. Link phải là `https` và có tên miền nằm trong
     danh sách được phép.
   - App giữ nguyên link gốc, chỉ thêm các tham số được phép.
   - Link không dùng nữa thì bấm *Ngừng dùng*.

### 6.2. AI soạn nội dung cho chiến dịch

**Chuẩn bị một lần:** ở *Cài đặt → cấu hình model cho agent*, bật profile cho agent
**content** (Content Agent). Cách làm giống mục 4.3, và agent cần có giá model đang hiệu lực.

1. Kích hoạt chiến dịch ở tab **Tổng quan**. Chiến dịch cần ít nhất 1 nguồn không bị từ
   chối và 1 link đang dùng.
2. Ở tab **Nội dung**, tạo lô:
   - chọn link affiliate;
   - chọn loại nội dung: bài mạng xã hội, caption video ngắn, kịch bản video, bài đánh
     giá, bài so sánh, CTA/landing;
   - chọn số bài mỗi loại (tối đa 10 bài một lô);
   - nhập trần chi phí của lô. Tổng trần các lô không được vượt trần của chiến dịch.
3. Bấm **Phê duyệt & chạy tự động** ở lô vừa tạo. Bước duyệt giống mục 5.4.
4. Bản nháp hiện ở mục *Bản nháp nội dung*. Mỗi khẳng định được gắn nhãn **FACT** (có
   nguồn đã xác minh), **ESTIMATE** hoặc **HYPOTHESIS**.

Lưu ý:
- Lô nội dung dùng một **bản chụp** dữ liệu của chiến dịch lúc tạo lô: nguồn, điều khoản
  mới nhất, sản phẩm và link. Sửa chiến dịch sau đó không làm thay đổi lô đã tạo.
- AI **không thấy link thật**. AI chỉ viết `{{AFFILIATE_LINK}}`; link thật được ghép khi
  xuất bài ở bản sau. Nếu AI tự viết bất kỳ địa chỉ web nào, cả lô bị từ chối và không
  tạo bản nháp nào. Chi phí của lần gọi đó vẫn được ghi lại để đối soát.
- Link thật chỉ được ghép khi xuất bài (mục 6.3).

### 6.3. Duyệt nội dung và tự đăng (Level B)

Bấm vào một bản nháp ở tab **Nội dung** để mở phần duyệt.

1. **Chạy kiểm tra.** Hệ thống kiểm tra theo các luật cố định:
   - nội dung còn chỗ giữ link;
   - có câu công bố affiliate;
   - khẳng định FACT có nguồn đã xác minh;
   - giá và % khớp với dữ liệu đã xác minh;
   - không có cụm từ bị hạn chế (*cam kết, đảm bảo, tốt nhất, số 1, 100%, chữa khỏi…*);
   - không có địa chỉ web khác;
   - không trùng gần như hoàn toàn với bài khác trong chiến dịch.
2. **Xử lý kết quả.**
   - **Không đạt**: sửa nội dung rồi chạy kiểm tra lại, hoặc từ chối.
   - **Chờ Owner**: anh/chị tự xác nhận kèm ghi chú. Hai mục *Quyền dùng hình ảnh/tài
     liệu* và *Quảng cáo, TMĐT và thuế* luôn cần anh/chị xác nhận.
   - Hệ thống không bao giờ tự kết luận một nội dung là "đạt chuẩn".
3. **Sửa.**
   - Mỗi lần sửa tạo một phiên bản mới; các bản cũ vẫn xem được trong *Lịch sử phiên bản*.
   - Sau khi sửa phải chạy kiểm tra lại.
   - Giữ nguyên `{{AFFILIATE_LINK}}` ở chỗ cần đặt link.
4. **Duyệt hoặc từ chối**, kèm ghi chú. Nút Duyệt chỉ bật khi mọi mục kiểm tra đã đạt.
5. **Xuất để tự đăng.**
   - Bản xuất có link affiliate thật và câu công bố của chiến dịch, dạng văn bản hoặc
     Markdown. Bấm *Sao chép* rồi dán vào ứng dụng mạng xã hội.
   - App **không tự đăng**.
   - Nếu link đã ngừng dùng thì không xuất được.
6. **Ghi nhận đã đăng.** Nhập kênh, link bài đăng và thời điểm đăng. Một nội dung có thể
   ghi nhận nhiều kênh.

Các luật kiểm tra chỉ là công cụ hỗ trợ, không phải tư vấn pháp lý. Quyết định cuối cùng là
của anh/chị.

## 7. Theo dõi và đối soát chi phí

Trang **Chi phí AI** hiển thị:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Lượt gọi | Số lần gọi AI, theo trạng thái |
| Ước tính | Trần chi phí đã giữ trước khi chạy |
| Ước tính theo token | Tính từ token provider báo về × giá Owner nhập |
| Đã xác nhận | Số tiền Owner đã đối soát với hóa đơn |
| Đang giữ ngân sách | Số tiền còn bị giữ, chưa đối soát |
| Cần đối soát | Số lượt gọi đã kết thúc nhưng còn giữ ngân sách |

Bảng phân tích **Theo agent** và **Theo model** giúp thấy chi phí đi đâu.

**Đối soát** (nên làm sau khi provider cập nhật hóa đơn hoặc trang usage):

1. Ở dòng có nhãn **Cần đối soát**, nhập **Chi phí thực tế (USD)** theo hóa đơn/usage của provider và
   **Lý do / nguồn hóa đơn**.
2. Bấm **Xác nhận chi phí** (ghi nhận số thực tế) hoặc **Giải phóng phần dư** (trả phần không dùng về ngân sách).
   Thao tác **không thể hoàn tác**.

Lượt gọi có trạng thái `USAGE_UNKNOWN` (ví dụ mất kết nối giữa chừng) **vẫn giữ toàn bộ ngân sách** cho đến khi Owner
đối soát, vì provider có thể đã tính phí. Tổng ngân sách tháng xem ở trang **Tài chính & Ngân sách**.

## 8. Các trang khác

| Trang | Dùng để |
| --- | --- |
| Tổng quan | Số agent, phê duyệt đang chờ, ngân sách tháng, trạng thái kiểm soát |
| AI Workforce | Bật/tắt agent. Agent bị tắt thì giai đoạn của nó không chạy được |
| Cơ hội | Quản lý cơ hội kinh doanh: bằng chứng, ước tính, chấm điểm, so sánh |
| Workflow | Tạo, phê duyệt, chạy, tạm dừng, hủy workflow và task |
| Phê duyệt | Duyệt hoặc từ chối mọi yêu cầu; mỗi quyết định gắn với một action hash cụ thể |
| Tài chính & Ngân sách | Hạn mức tháng, đã cam kết, còn khả dụng, chi phí đã quyết toán |
| Nhật ký audit | Mọi thao tác đều được ghi lại, không sửa/xóa được |
| Dự án | Chưa triển khai |

## 9. Xử lý lỗi thường gặp

Khi bấm **Yêu cầu duyệt task** hoặc **Chạy task** bị từ chối, thông báo cho biết lý do:

| Thông báo | Cách xử lý |
| --- | --- |
| Agent AI profile is unavailable | Cấu hình model cho agent đó chưa có hoặc chưa tích **Bật cấu hình agent** (4.3) |
| Provider configuration or credential is unavailable | Provider chưa **Bật cấu hình**, đã lưu trữ hoặc chưa có API key (4.1) |
| Provider adapter has not been verified for this endpoint | Đang dùng `OPENAI_COMPATIBLE` hoặc Base URL tùy chỉnh; sửa provider, để trống Base URL |
| Model temperature capability has not been verified | Xóa giá trị **Temperature** trong cấu hình agent |
| Model price version is unavailable or not effective | Giá chưa có hoặc "Hiệu lực từ" ở tương lai (4.2). Nhập giá rồi tạo workflow mới và **Thêm giai đoạn AI** lại |
| AI task pricing and prompt versions are required | Task không được tạo bằng **Thêm giai đoạn AI**; tạo lại theo 5.3 |
| Estimated inference cost exceeds an approved run limit or is unverified | Ước tính vượt **Chi phí tối đa mỗi lần** của agent hoặc **Chi phí tối đa** của lượt nghiên cứu; tăng trần hoặc giảm **Token đầu ra tối đa** |
| Research context exceeds the source limit | Quá nhiều nguồn; tối đa 20 nguồn, từ chối bớt nguồn không cần |
| AI budget account is unavailable or overcommitted | Ngân sách tháng không đủ; đối soát các lượt gọi đang giữ ngân sách (mục 7) |
| Task role is not allowed for this AI handler | Vai trò task bị sửa tay; tạo lại giai đoạn AI |
| Global AI consent ... / execution disabled | Quyền AI toàn cục đang tắt (4.4) |

Các vấn đề khác:

| Hiện tượng | Nguyên nhân / cách xử lý |
| --- | --- |
| Tự quay về màn hình đăng nhập | Phiên đã hết 12 giờ, đã đăng xuất, hoặc server đổi `SESSION_SECRET`; đăng nhập lại |
| Mở tab mới phải đăng nhập lại | Lần đăng nhập trước không tích **Ghi nhớ đăng nhập** |
| Dưới task AI báo "Chưa có chính sách AI được bật" | Chính sách `ai-inference-controlled` bị tắt; liên hệ người quản trị để bật lại |
| "Đăng nhập Owner" / "Vui lòng đăng nhập Owner" | Chưa đăng nhập hoặc phiên đã hết hạn |
| Nút **Chạy task** bị mờ | Task chưa có phê duyệt `APPROVED` còn hạn, hoặc giai đoạn trước chưa xong |
| Không thấy nút **Yêu cầu duyệt task** | Workflow đang **chạy tự động**: task tự được xếp hàng, không cần duyệt riêng |
| "Bản nháp nghiên cứu chưa có nguồn nào" khi bấm **Phê duyệt & chạy tự động** | Thêm ít nhất 1 nguồn (5.2) rồi bấm lại |
| Chạy tự động "đã dừng · Dữ liệu, nguồn hoặc cấu hình AI đã thay đổi sau khi duyệt" | Có thay đổi sau lúc duyệt; kiểm tra rồi bấm **Phê duyệt & chạy tự động** lại |
| Chạy tự động "đã dừng · Một task bị lỗi" | Xem **Lịch sử thực thi** và trang **Chi phí AI**; lỗi kiểm tra bản nháp thường do thiếu nguồn hoặc thiếu thị trường mục tiêu |
| Trang báo lỗi 502 vài chục giây | Backend đang khởi động lại, chờ khoảng 30–60 giây |

## 10. Vận hành server

Các lệnh chạy trong thư mục dự án trên server.

| Việc | Lệnh |
| --- | --- |
| Xem trạng thái | `docker compose -p makemoney ps` |
| Xem log backend / worker | `docker compose -p makemoney logs --tail 100 backend worker` |
| Khởi động lại backend sau khi sửa `.env` | `docker compose -p makemoney up -d --no-deps --no-build backend` |
| Sao lưu database | `docker compose -p makemoney exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup.dump` |

Cấu hình trong `.env` (quyền file `600`, không commit lên Git):

| Biến | Ghi chú |
| --- | --- |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Tài khoản đăng nhập web. Đổi xong phải khởi động lại backend |
| `OWNER_API_KEY` | Key cho script/công cụ gọi API trực tiếp |
| `SESSION_SECRET` | Đổi giá trị này để đăng xuất mọi phiên đang mở |
| `AI_CREDENTIALS_KEY` | Khóa mã hóa API key của provider. **Sao lưu riêng ở nơi an toàn**: mất khóa này thì các API key đã lưu không giải mã được và phải nhập lại |

Khi `ENVIRONMENT=production`, backend từ chối khởi động nếu các secret còn là giá trị mẫu của `.env.example`.

Bảo mật mạng: cổng 3000 (web) và 8000 (API) mở trên mọi địa chỉ. Nếu server có IP công khai, nên giới hạn bằng
tường lửa chỉ cho các dải IP tin cậy, hoặc truy cập qua SSH tunnel
(`ssh -L 3000:localhost:3000 <user>@<IP-server>`).

## 11. Hạn chế đã biết

- Các bài kiểm thử tự động dùng provider giả lập. Lần chạy với provider thật đầu tiên nên chạy từng giai đoạn và đối
  chiếu chi phí với trang usage của provider.
- Hệ thống không tự thu thập nguồn từ Internet; mọi nguồn do Owner nhập.
- Ngân sách là kiểm soát nội bộ. Nó không thể ngăn hóa đơn trễ hoặc chi phí phát sinh ngoài hệ thống; hãy đặt thêm
  giới hạn chi tiêu trên trang của provider.
- Level B: app không tự đăng bài, không theo dõi click/đơn hàng/hoa hồng. Đăng bài tự động có kiểm soát
  (Step 7B) và theo dõi doanh thu (Step 8) chưa có.
- Luật kiểm tra nội dung chỉ dựa trên mẫu cố định (cụm từ, số, địa chỉ web); không thay thế việc anh/chị đọc lại.
- Phiên được ghi nhớ nằm trong bộ nhớ trình duyệt (localStorage). Muốn thu hồi mọi phiên ngay, đổi `SESSION_SECRET`
  trong `.env` rồi khởi động lại backend.
