# Changelog

Tất cả thay đổi đáng chú ý của dự án được ghi nhận tại đây.

## [1.2.2] - 2026-02-27

### 🚀 Tính năng mới

#### HQ Auto Drive Sync (`server.py`, `haiquan_sync.py`)
- **Real-time sync**: mỗi file HQ tải xong → tự động upload lên Google Drive (giống CafeF)
  - Khởi tạo `HaiQuanDriveSync` nếu `HQ_GOOGLE_DRIVE_FOLDER_ID` có trong `.env`
  - `on_download` callback gọi `upload_single()` ngay sau khi tải
  - Đánh dấu `drive_synced=1` + lưu `drive_file_id` vào SQLite
- **`upload_single(pdf_path)`** [NEW]: upload đơn lẻ lên Drive, trả file ID
- **`_find_file_id()`** [NEW]: check file đã tồn tại trên Drive (skip duplicate)
- **Frontend**: hiển thị `☁ N` (số file đã sync) cạnh `✅ downloaded` / `❌ failed`

### 🐛 Bugfixes

#### SSL Certificate Error (`haiquan_scraper.py`)
- **Nguyên nhân**: SSL cert trên `files.customs.gov.vn` hết hạn → `SSLError` mọi download
- **Fix**: `verify=False` cho requests đến domain này + `urllib3.disable_warnings()`

### 🔧 Cải tiến

#### Filename Parsing (`haiquan_scraper.py`)
- **3 regex patterns** mới: `RE_STANDARD`, `RE_QUARTER`, `RE_QUARTER_ROMAN`
- **Default status**: prefix không có CT/SB/DC → mặc định `CT` (vd: `EN-PR` → `CT`)
- **Roman numerals**: `QIV→Q4`, `QIII→Q3`, `QII→Q2`, `QI→Q1`
- **NK/XK direction**: `PTVT-XKQ1-2022.pdf` → `CT_2022Q1_PTVT-XK.pdf`
- **Year suffix**: `PTVT-NKQ1-2022.pdf` → `CT_2022Q1_PTVT.pdf`
- **Year fallback**: filename thiếu năm → dùng năm từ URL + 1

#### Error Reporting (`haiquan_scraper.py`, `server.py`, `haiquan_app.js`)
- `download_pdf()` trả tuple `(result, error_msg)` với chi tiết lỗi cụ thể
- Skip retry cho HTTP 404/403/410 (URL không hợp lệ)
- `error_details[]` + `last_error` broadcast qua WebSocket
- Frontend: `#hqProgressNotes` hiển thị lỗi gần nhất (tối đa 5 chi tiết)

---

## [1.2.1] - 2026-02-25

### 🚀 Tính năng mới

#### HQ History Filter Bar Redesign (`index.html`, `haiquan_app.js`)
- **Search input**: tìm theo tên file (debounce 300ms)
- **3 filter dropdowns**: Loại BC (SB/CT/DC), Mã BC (dynamic từ API), Trạng thái đồng bộ
- **Count badge**: hiện tổng records
- **Nút Dọn dẹp**: cleanup records + files theo filter (có xác nhận)
- **Sort arrows**: visual indicator trên các cột sortable
- Responsive: match layout CafeF tab

#### HQ Sheet Sync (`haiquan_sync.py`) [NEW]
- **`HaiQuanSheetSync`**: sync metadata Hải Quan lên Google Sheets
  - Sheet: `"HAI QUAN"`, tab: `"DATA"`
  - Columns: FILENAME (hyperlink → Drive) | YEAR | PERIOD | TYPE | CODE | SIZE | DATE
  - Hash-based incremental: skip nếu data không thay đổi
- **API**: `POST /api/haiquan/gsheet/sync`
- **UI**: nút **Sync Sheet** cạnh Sync Drive trong HQ tab

### 🐛 Bugfixes

#### CafeF Sheet thiếu Drive hyperlinks (`google_sync.py`)
- **Nguyên nhân**: `upload_all()` đánh dấu `drive_synced=1` nhưng không lưu `drive_file_id` vào SQLite
- **Fix**: sau batch upload, re-scan tất cả files trên Drive → map `filename → file_id` → batch UPDATE `drive_file_id`
- Áp dụng cùng fix cho HQ Drive sync (`haiquan_sync.py`)

### 🔧 Cải tiến

#### Server (`server.py`)
- `GET /api/haiquan/history`: thêm `search` param (LIKE filename), thêm `filename` vào allowed sorts
- `DELETE /api/haiquan/history/cleanup`: chuyển sang JSON body (phù hợp frontend)
- `POST /api/haiquan/gsheet/sync`: endpoint mới cho HQ Sheet sync

#### HQ Action Buttons (`haiquan_app.js`)
- **Centralized disable**: `hqBgTask { scrape, drive, sheet }` + `hq_updateActionButtons()` quản lý 4 nút (Scrape/Stop/Sync Drive/Sync Sheet) — mutual disable khi bất kỳ task nào chạy nền

#### Footer
- Đổi `"CafeF CBTT Report Manager v1.0"` → `"Report Manager v1.0"` 
- Thêm footer vào tab Hải Quan (giống CafeF)

---

## [1.2.0] - 2026-02-25

### 🚀 Tính năng mới

#### Tab Hải Quan — Clone & Isolate từ CafeF CBTT

Thêm tab **"Hải Quan"** hoàn toàn tách biệt với CafeF CBTT, tải và đồng bộ báo cáo thống kê hải quan (PDF) từ `customs.gov.vn`.

##### Kiến trúc tách biệt (6 layers)

| Layer | CafeF | Hải Quan |
|-------|-------|----------|
| Scraper | `cafef_scraper.py` | `haiquan_scraper.py` [NEW] |
| Database | `pdf/_download_history.db` | `pdf/haiquan/_haiquan_history.db` |
| PDF Dir | `pdf/{ICB}/` (subfolders) | `pdf/haiquan/` (flat) |
| Server Jobs | `ScrapeJob`, `SyncJob` | `HaiQuanScrapeJob`, `HaiQuanSyncJob` |
| API Prefix | `/api/*` | `/api/haiquan/*` |
| WS Types | `progress`, `sync_progress` | `haiquan_progress`, `haiquan_sync_progress` |
| Frontend | `app.js` | `haiquan_app.js` [NEW] |
| Drive Folder | `GOOGLE_DRIVE_FOLDER_ID` | `HQ_GOOGLE_DRIVE_FOLDER_ID` |

##### Core Backend (`haiquan_scraper.py`) [NEW]
- **`parse_filename(url)`**: phân tích URL → tên file chuẩn `{LOẠI_BC}_{KỲ_BC}_{MÃ_BC}.pdf`
  - LOẠI_BC: `SB` (Sơ bộ), `CT` (Chính thức/Final), `DC` (Điều chỉnh)
  - KỲ_BC: `{YYYY}T{M}` (tháng), `{YYYY}T{M}K1/K2` (nửa tháng), `{YYYY}Q{N}` (quý)
  - Edge cases: numeric prefix trong filename, year fallback cho quarter reports
- **`HaiQuanDownloadHistory`**: SQLite riêng (`_haiquan_history.db`) với schema riêng (year, month, quarter, period, report_code, report_type, drive_synced, drive_file_id)
- **`download_pdf()`**: retry logic, resume support, history check
- **`load_legacy_urls()`**: import URLs từ `docs/haiquan/haiquan.xlsx`
- **`HaiQuanScraper`**: orchestrator chính

##### Drive Sync (`haiquan_sync.py`) [NEW]
- **`HaiQuanDriveSync`**: upload flat structure lên Drive folder riêng
- Reuse OAuth credentials, incremental (skip nếu file đã tồn tại + cùng size)
- Non-resumable cho files < 5MB, resumable cho lớn hơn

##### Server Integration (`server.py`)
- **`HaiQuanScrapeJob`**: background thread tách biệt, broadcast `haiquan_progress`
- **`HaiQuanSyncJob`**: background thread tách biệt, broadcast `haiquan_sync_progress`
- **9 API endpoints**:

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/api/haiquan/scrape` | Bắt đầu tải HQ |
| `GET` | `/api/haiquan/scrape/status` | Trạng thái job |
| `POST` | `/api/haiquan/scrape/stop` | Dừng job |
| `GET` | `/api/haiquan/history` | Lịch sử tải (phân trang, filter, sort) |
| `GET` | `/api/haiquan/history/filters` | Filter options (years, report_types, report_codes, periods) |
| `DELETE` | `/api/haiquan/history/cleanup` | Xóa records + files theo filter |
| `GET` | `/api/haiquan/stats` | Thống kê theo năm/loại/mã BC |
| `POST` | `/api/haiquan/gdrive/sync` | Upload HQ PDFs lên Drive |
| `GET` | `/api/haiquan/sync/status` | Trạng thái sync |

##### Frontend (`index.html`, `haiquan_app.js`, `style.css`, `app.js`)
- **Header Tab Navigation**: `CafeF CBTT` | `Hải Quan` — chuyển flow qua `switchFlow()`
- **HQ Filter Panel**: nguồn dữ liệu (XLSX/Web/All), năm từ-đến, loại BC
- **Action Buttons**: Bắt đầu tải / Dừng / Sync Drive — mutual disable
- **Progress Card**: realtime progress qua WebSocket (`haiquan_progress`)
- **Sync Card**: Drive sync progress qua WebSocket (`haiquan_sync_progress`)
- **Stats Grid**: tổng files, số năm, mã BC, dung lượng
- **History Table**: sortable, filterable (năm, loại, mã BC, sync status), pagination

##### Environment Variables (`.env`)
- `HQ_PDF_DIR=./pdf/haiquan` — thư mục lưu PDF Hải quan
- `HQ_GOOGLE_DRIVE_FOLDER_ID` — Google Drive folder riêng cho Hải quan
- `HQ_HEADLESS=true` — chế độ headless
- `HQ_DOWNLOAD_DELAY=1.0` — delay giữa các downloads

---

## [1.1.4] - 2026-02-25

### 🐛 Bugfixes

#### Page Crash Recovery (`cafef_scraper.py`)
- **Fix "Page crashed"**: Chromium headless tích lũy memory qua hàng trăm tickers → crash `Page.wait_for_selector: Page crashed`
  - **Periodic browser restart**: tự động restart browser mỗi `BROWSER_RESTART_INTERVAL` tickers (mặc định 50) để giải phóng memory
  - **Crash detection**: `_is_page_crashed()` detect "page crashed", "target closed", "context or browser has been closed"
  - **Auto-recovery**: khi detect crash → restart browser → retry ticker bị crash 1 lần
- **Fix multi-ticker dừng sớm**: vòng lặp multi-ticker không có try/catch per-ticker → 1 crash dừng toàn bộ
  - **Per-ticker error isolation**: mỗi ticker bọc trong `try/except` riêng — 1 lỗi chỉ skip ticker đó, không ảnh hưởng phần còn lại
  - **Error tracking**: `crashed_tickers[]`, `skipped_tickers[]`, `browser_restarts` counter

### 🔧 Cải tiến

#### Chromium Stability (`cafef_scraper.py`)
- **Launch flags**: `--disable-dev-shm-usage`, `--disable-gpu`, `--no-sandbox`, `--disable-extensions`, `--disable-background-timer-throttling`, `--disable-renderer-backgrounding`
- **Refactor**: tách `_create_browser()`, `_load_cbtt_page()` từ `run()` — cho phép restart browser bất kỳ lúc nào

#### Scrape Progress (`server.py`)
- **Thêm fields** vào WebSocket progress: `crashed_tickers`, `skipped_tickers`, `browser_restarts`
- Tracking áp dụng cho tất cả trạng thái: `completed`, `stopped`, `error`

#### Report JSON (`cafef_scraper.py`)
- **Enhanced report**: `_scraper_report.json` bổ sung `crashed_tickers`, `skipped_tickers`, `browser_restarts`
- **Tổng kết log**: hiển thị chi tiết crash/skip/restart counts khi kết thúc

---

## [1.1.3] - 2026-02-25

### 🚀 Tính năng mới

#### Google Sign-In (`server.py`, `app.js`, `index.html`)
- **Thay thế login hardcoded** (`tns/123colEn`) bằng Google Sign-In (GIS)
- Endpoints: `GET /api/auth/config`, `POST /api/auth/google`
- Email whitelist qua `ALLOWED_EMAILS` trong `.env`
- Hiển thị Google avatar + email trong user menu

#### Dọn dẹp theo Filter (`server.py`, `app.js`, `index.html`)
- **Nút "🗑 Dọn dẹp"**: xuất hiện khi có ít nhất 1 filter active trong bảng Lịch sử
- Xóa files PDF local + records DB theo filter hiện tại (exchange, ICB, sync status, mã CK)
- Dialog xác nhận hiển thị chi tiết filter + số lượng records
- Tự dọn thư mục ICB rỗng sau khi xóa
- Endpoint: `DELETE /api/history/cleanup`

#### TICKER Hyperlink (`google_sync.py`, `app.js`)
- **Bảng Lịch sử**: TICKER hiển thị link xanh đến file trên Google Drive (khi đã sync)
- **Google Sheet CAFEF**: TICKER dùng `=HYPERLINK()` formula link đến Drive

#### Mutual Button Disable (`app.js`)
- **Khoá chéo 3 nút**: Bắt đầu tải / Sync Drive / Sync Sheet — khi bất kỳ task nào chạy nền, cả 3 nút đều bị vô hiệu hoá
- State tracker `bgTaskRunning { scrape, drive, sheet }` + helper `updateActionButtons()` quản lý tập trung
- Enable lại chỉ khi **tất cả** task kết thúc (completed/stopped/error)

### 🔧 Cải tiến

#### Google Sheet CAFEF (`google_sync.py`)
- Fix Sheet trống: đổi `valueInputOption` → `USER_ENTERED` (hỗ trợ formula)
- Thêm cột **DATE** (ngày tải)
- Hash moved G1 → H1 (offset do thêm cột)
- Logging khi data rỗng

#### Drive File ID Tracking (`google_sync.py`, `cafef_scraper.py`, `server.py`)
- `upload_single()` trả file ID (str) thay vì bool
- `_file_exists()` → `_find_file_id()` (trả Drive ID)
- Cột `drive_file_id TEXT` trong DB (auto-migration)
- `on_download()` lưu `drive_file_id` vào DB

#### Background Scrape UX (`index.html`, `style.css`)
- Banner "Quá trình tải chạy nền — đóng trình duyệt không ảnh hưởng"
- WS reconnect + poll fallback đã có sẵn

---

## [1.1.2] - 2026-02-24

### 🚀 Tính năng mới

#### Sync Status Panel (`server.py`, `google_sync.py`, `app.js`)
- **Dedicated sync panel**: tách hoàn toàn khỏi khung scrape progress
- **Drive sync phases**: `scanning` → `listing` → `uploading` — hiện folder, filename, stats (↑/⏭/✖), ETA
- **Sheet sync phases**: `reading_db` → `computing_hash` → `writing_sheet` — shimmer progress bar
- **Badges**: trạng thái `running` (pulse animation) / `completed` (xanh) / `error` (đỏ)
- **Auto-hide**: tự ẩn panel sau 10s khi sync hoàn tất
- **Phase callbacks**: `upload_all(phase_callback=...)`, `sync(progress_callback=...)` broadcast qua WebSocket

#### Lịch sử tải — Filter & Sort (`server.py`, `app.js`, `index.html`)
- **Cột "Đồng bộ"**: hiện ✔ xanh (đã sync Drive) / ✖ đỏ (chưa sync) — sau cột Dung lượng
- **Filter theo Sàn**: dropdown populate từ DB (`/api/history/filters`)
- **Filter theo Ngành ICB**: dropdown populate từ DB
- **Filter theo Đồng bộ**: Tất cả / Đã đồng bộ / Chưa đồng bộ
- **Sort Ticker**: click header, mặc định A→Z
- **Sort Thời gian**: click header, mặc định mới→cũ
- **Sort Ngày tải**: click header, mặc định mới→cũ (active)
- **Endpoint mới**: `GET /api/history/filters` — distinct exchanges + ICB codes

### 🔧 Cải tiến

#### Database (`cafef_scraper.py`)
- **Cột `drive_synced`**: `INTEGER DEFAULT 0`, auto-migration
- **Index**: thêm `idx_exchange` cho filter performance

#### Drive Sync Marking (`google_sync.py`, `server.py`)
- **Batch marking**: sau `upload_all()`, đánh dấu tất cả files đã xử lý là `drive_synced=1`
- **Real-time marking**: khi scrape có Drive sync, mỗi file upload thành công → `drive_synced=1` ngay

#### API `/api/history` (`server.py`)
- Thêm query params: `exchange`, `drive_synced`, `sort_by`, `sort_dir`
- Sort validation: chỉ cho phép `stock_code`, `quarter_year`, `downloaded_at`

---

## [1.1.1] - 2026-02-24

### 🚀 Tính năng mới

#### OAuth Web Flow (production)
- **Redirect production**: OAuth flow dùng `https://stockreport.tnsai.vn/oauth2callback` thay localhost
- **Endpoints**:
  - `GET /api/oauth2/start` — trả URL redirect đến Google consent (yêu cầu admin)
  - `GET /oauth2callback` — nhận code từ Google, lưu token, redirect về `/?oauth=success`
  - `GET /api/oauth2/status` — kiểm tra đã có token chưa
  - `GET /api/oauth2/debug` — debug: client_id + redirect_uri (so khớp Google Cloud Console)
- **Env**: `OAUTH_REDIRECT_URI` (mặc định `https://stockreport.tnsai.vn/oauth2callback`)
- **UI**: Sync Drive/Sheet kiểm tra token trước; nếu chưa có → redirect OAuth flow; xử lý `?oauth=success|error` khi quay về

### 🐛 Bugfixes

#### OAuth Scope Error
- **Lỗi**: "Scope has changed from ... to ..." khi token trả về nhiều scopes hơn yêu cầu
- **Nguyên nhân**: OAuth client dùng chung với app khác (pdf2vid/YouTube), `include_granted_scopes="true"` gây conflict
- **Fix**: Bỏ `include_granted_scopes` trong `authorization_url` — chỉ request đúng scopes drive + spreadsheets

---

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
- **OAuth2 only**: bỏ Service Account, chỉ dùng OAuth (user quota)
  - `google_oauth_credentials.json` (web type) — bắt buộc
  - Lần đầu: mở browser consent → token lưu `_google_token.json`
  - Env: `GOOGLE_OAUTH_CREDENTIALS`, `GOOGLE_DRIVE_FOLDER_ID`
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
