# Changelog

Tất cả thay đổi đáng chú ý của dự án được ghi nhận tại đây.

## [1.1.0] - 2026-02-24

### 🚀 Tính năng mới

#### Auto-Delete Files (`cleanup.py`) [NEW]
- **Retention period** cấu hình: 1 tuần / 1 tháng / 1 quý (mặc định) / 1 năm / Không xóa
- **Background scheduler**: daemon thread kiểm tra + xóa files hết hạn mỗi 24h
- Xóa dựa trên `downloaded_at` trong DB → xóa file vật lý + record DB
- Tự dọn thư mục ICB rỗng sau khi xóa
- Settings lưu vào `_settings.json` trong thư mục PDF
- API endpoints: `GET/POST /api/settings`, `POST /api/cleanup/run`

#### Background Sync (`server.py`)
- **SyncJob class**: chạy Drive/Sheet sync trong daemon thread, độc lập browser
- **Concurrent**: Drive và Sheet chạy đồng thời, không chặn lẫn nhau
- **Auto Sheet sync**: tự động sync Sheet sau khi scraping hoàn tất (nếu có file mới)
- Endpoint trả response ngay (`{"status": "started"}`), sync tiếp tục chạy nền
- Broadcast tiến trình qua WebSocket (`type: sync_progress`)
- `GET /api/sync/status` — trả trạng thái cả Drive và Sheet

### 🔧 Cải tiến

#### Google Drive Sync (`google_sync.py`)
- **OAuth2 credentials**: chuyển từ Service Account sang OAuth2 (SA không có storage quota)
  - Ưu tiên `google_oauth_credentials.json`, fallback `service_account.json`
  - Env vars: `GOOGLE_OAUTH_CREDENTIALS` (mới) + `GOOGLE_SERVICE_ACCOUNT_KEY` (fallback)
  - Token lưu tại `_google_token.json`, tự refresh khi hết hạn
- **Batch file listing**: `_list_existing_files_recursive()` thay N+1 per-file queries
- **File size check**: detect file upload dở/corrupt → auto delete + re-upload
- **Non-resumable upload**: files < 5MB dùng non-resumable (fix empty files trên Drive)
- **Upload verification**: request `id,size` fields sau upload, log warning nếu size mismatch
- **Diagnostic endpoint**: `GET /api/gdrive/test` — test upload 1 file + trả kết quả chi tiết
- **Shared Drive support**: `supportsAllDrives=True` cho tất cả Drive API calls (list, create, delete)

#### Google Sheet Sync (`google_sync.py`)
- **Hash-based incremental**: MD5 hash data → lưu vào G1 → skip nếu data không đổi

#### UI Updates
- **Login screen**: glassmorphism, fade-in animation, purple accents
- **Header**: user avatar + dropdown menu (thay nút Logout)
- **Settings modal**: glassmorphism overlay, slide-up animation
- **Toast stacking**: fix toast chồng lên nhau — dùng `#toastContainer` flexbox, max 3 visible
- **Progress notes**: tách Lỗi/Lọc ra mục ghi chú riêng (màu đỏ, in nghiêng) dưới khung tiến trình
  - Chi tiết lỗi: hiển ticker + filename + thông tin lỗi cụ thể
  - Diễn giải bộ lọc thời gian: hiển số entries bị lọc + khoảng thời gian
- **Drive sync progress**: hiển thị trực tiếp trên progress bar
  - Sub-folder + filename đang sync: `☁ Drive sync: [0570] report.pdf`
  - Counts + ETA: `45/200 — ↑12 ⏭33 | ETA: 2m30s`
  - Lỗi upload hiện trong progressNotes section

### 🐛 Bugfixes

#### Google Drive Upload (`google_sync.py`)
- **Fix empty folders**: sub-folders tạo được nhưng files bên trong rỗng
  - Root cause: Service Account không có storage quota (HTTP 403 storageQuotaExceeded)
  - Fix: chuyển sang OAuth2 credentials → upload dùng quota của user đã đăng nhập
  - Bổ sung: `resumable=False` cho files < 5MB, progress callback cho MỌI file

#### Multi-Ticker Scraper (`cafef_scraper.py`)
- **Fix HHV contamination**: ticker lạ (HHV) xuất hiện ở đầu mỗi group vì DOM chưa update sau search
  - DOM polling: đợi bảng CBTT hiển thị đúng ticker (max 10s) trước khi extract
  - Pre-filter entries tại `_scrape_pages()`: loại bỏ stale entries không khớp `current_ticker`
  - Filter `_process_entry()`: so khớp `self.current_ticker` thay vì toàn bộ group list
- Cải thiện hiển thị "Lọc bỏ" — chỉ hiện filter counts khác 0

---

## [1.0.0] - 2026-02-24

### 🚀 Tính năng mới

#### Stock Data Module (`stock_data.py`)
- **StockRegistry** — singleton class load dữ liệu từ 3 file Excel:
  - `stock_exchange.xlsx`: 3179 tickers, 5 sàn (HSX, HNX, UPCOM, BOND, DELISTED)
  - `stock_industry.xlsx`: 1584 tickers, 36 ngành ICB
  - `stock_index.xlsx`: 412 mappings, 5 chỉ số (VN30, VN100, VNMID, VNSML, VNALL)
- Lookup methods: `get_exchange()`, `get_icb_code()`, `get_icb_name()`, `get_indexes()`
- Group methods: `tickers_by_exchange()`, `tickers_by_icb_code()`, `tickers_by_index()`
- `to_json()` export toàn bộ dữ liệu cho REST API

#### Scraper Refactor (`cafef_scraper.py`)
- **Quy ước đặt tên mới**: `[ICB_CODE]_[TICKER]_[YEARQ]_[TYPE].pdf`
  - Ví dụ: `8350_ACB_2024Q4_BCTC.pdf`, `2350_CTD_2025Q1_BCTC.pdf`
- **Tổ chức thư mục ICB**: PDF lưu vào `pdf/[ICB_CODE]/` (ví dụ `pdf/8350/`, `pdf/2350/`)
- **SQLite schema mới**: thêm cột `icb_code`, `exchange` với migration tự động
- **MAX_PAGES=0**: mặc định fetch tất cả trang (trước đó giới hạn 3)
- **Adaptive rate limiting**:
  - `PAGE_DELAY` (mặc định 1.5s) giữa các trang, tăng 0.5s mỗi 20 trang
  - `DOWNLOAD_DELAY` (mặc định 0.5s) giữa các PDF download
- **StockRegistry integration**: tự động lookup ICB code và sàn cho mỗi ticker
- **Pagination JS-based**: sử dụng `IformationDisclosure.handleChangePage(N)` thay vì click link

#### Google Integration (`google_sync.py`)
- **OAuth2 flow**: sử dụng `google_oauth_credentials.json` (web type)
  - Lần đầu mở browser consent → token lưu vào `_google_token.json`
  - Các lần sau tự refresh token
- **GoogleDriveSync**:
  - Upload PDF với ICB subfolder mirroring
  - Skip file đã tồn tại trên Drive
  - Resumable upload cho file lớn
- **GoogleSheetSync**:
  - Tạo/cập nhật sheet "CAFEF"
  - Columns: TICKER, TIME, TYPE, EXC, IND, INDEX
  - Sort theo TICKER → TIME
  - Clear và ghi lại toàn bộ dữ liệu mỗi lần sync

#### Web UI (`server.py` + `static/`)
- **FastAPI server** với REST API + WebSocket realtime
- **Endpoints**:
  | Method | Path | Mô tả |
  |--------|------|-------|
  | GET | `/api/stock-data` | Danh sách exchanges, industries, indexes |
  | GET | `/api/tickers` | Filter tickers theo exchange/icb/index/search |
  | GET | `/api/history` | Query download history (phân trang) |
  | GET | `/api/stats` | Thống kê theo sàn/ngành/chỉ số |
  | POST | `/api/scrape` | Bắt đầu scrape job (async) |
  | GET | `/api/scrape/status` | Trạng thái job hiện tại |
  | POST | `/api/scrape/stop` | Dừng job |
  | POST | `/api/gdrive/sync` | Upload lên Google Drive |
  | POST | `/api/gsheet/sync` | Sync lên Google Sheets |
  | WS | `/ws/progress` | WebSocket realtime progress |
- **Dark-mode UI**:
  - Bộ lọc 4 tab: Mã CK (autocomplete), Sàn GD, Ngành ICB, Chỉ số
  - Chọn khoảng thời gian (năm/quý)
  - Thanh progress realtime qua WebSocket
  - Bảng thống kê theo sàn/ngành/chỉ số
  - Bảng lịch sử tải có phân trang
  - Toast notification
  - **Responsive**: 3 breakpoints (768px tablet, 480px phone, 360px small phone)
  - Touch targets ≥ 44px

### 🔧 Cải tiến
- Chuyển download history từ JSON → SQLite
- `download_pdf()` trả về `'skipped'|'downloaded'|'failed'` thay vì `bool`
- Loại bỏ `_extract_links_fallback()` gây lấy nhầm link tin tức
- Thêm `_wait_for_cbtt_module()` đợi JS module sẵn sàng

### 📦 Dependencies mới
- `fastapi`, `uvicorn[standard]`, `websockets`
- `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
- `openpyxl`
