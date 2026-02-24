# Changelog

Tất cả thay đổi đáng chú ý của dự án được ghi nhận tại đây.

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
