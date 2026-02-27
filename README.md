# Report Manager (CafeF CBTT & Hải Quan)

Hệ thống scraping, quản lý và đồng bộ báo cáo từ CafeF (CBTT) và Hải Quan (thống kê xuất nhập khẩu) với giao diện web hiện đại.

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Scraper** | Playwright (Chromium) | Latest |
| **Backend** | FastAPI + Uvicorn | Python 3.12 |
| **Frontend** | Vanilla JS + CSS | ES6+ |
| **Database** | SQLite | Built-in |
| **Data** | openpyxl | Excel reader |
| **Google** | Google API Client | OAuth2 |
| **Realtime** | WebSocket | Native |

## Cấu trúc project

```
Crawl/
├── cafef_scraper.py       # CafeF Scraper (Playwright)
├── haiquan_scraper.py     # Hải Quan Scraper (requests) [NEW]
├── stock_data.py          # StockRegistry — lookup ticker metadata
├── google_sync.py         # CafeF: Google Drive + Sheets sync (OAuth2)
├── haiquan_sync.py        # HQ: Google Drive sync (OAuth2) [NEW]
├── cleanup.py             # Auto-delete files theo retention period
├── server.py              # FastAPI web server (CafeF + HQ routes)
├── .env                   # Cấu hình (xem bên dưới)
├── requirements.txt       # Python dependencies
├── google_oauth_credentials.json  # Google OAuth2 credentials
│
├── static/                # Frontend UI
│   ├── index.html         # Single-page app (2 tabs: CafeF | Hải Quan)
│   ├── style.css          # Dark-mode design
│   ├── app.js             # CafeF client-side logic
│   └── haiquan_app.js     # HQ client-side logic (isolated) [NEW]
│
├── pdf/                   # CafeF PDF output (theo ICB code)
│   ├── 8350/              # Ngân hàng
│   ├── 2350/              # Xây dựng
│   └── .../
│
├── pdf/haiquan/           # HQ PDF output (flat) [NEW]
│   └── SB_2022T8_5N.pdf   # Ví dụ
│
├── stock_exchange.xlsx    # Dữ liệu sàn GD
├── stock_industry.xlsx    # Dữ liệu ngành ICB
├── stock_index.xlsx       # Dữ liệu chỉ số
└── docs/haiquan/haiquan.xlsx  # URLs Hải quan legacy (2009-2022)
```

## Cài đặt

### 1. Clone và cài dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Cấu hình `.env`

```env
# Scraper
STOCK_CODE=               # Lọc theo mã CK (rỗng = tất cả)
MAX_PAGES=3               # 0 = fetch tất cả trang
PDF_DIR=./pdf
HEADLESS=true
PAGE_DELAY=1.5            # Delay giữa các trang (giây)
DOWNLOAD_DELAY=0.5        # Delay giữa các PDF (giây)
BROWSER_RESTART_INTERVAL=50  # Restart browser mỗi N tickers (chống memory leak)

# Google Sign-In (optional)
GOOGLE_CLIENT_ID=
ALLOWED_EMAILS=user@example.com
JWT_SECRET=<random-string>

# Google Integration (OAuth2 only)
GOOGLE_OAUTH_CREDENTIALS=./google_oauth_credentials.json
OAUTH_REDIRECT_URI=https://stockreport.khoviet.com/oauth2callback
GOOGLE_DRIVE_FOLDER_ID=<your-folder-id>
GOOGLE_SHEET_FOLDER_ID=<your-folder-id>

# Hải Quan (tách biệt hoàn toàn với CafeF)
HQ_PDF_DIR=./pdf/haiquan
HQ_GOOGLE_DRIVE_FOLDER_ID=<your-hq-folder-id>
HQ_HEADLESS=true
HQ_DOWNLOAD_DELAY=1.0
```

### 3. Google OAuth (tuỳ chọn)

File `google_oauth_credentials.json` là OAuth2 Client credentials (web type).

**Flow lần đầu (production):**
1. Mở https://stockreport.khoviet.com → đăng nhập admin
2. Bấm **Sync Drive** → redirect đến Google consent
3. Đăng nhập Google account có quyền truy cập Drive folder
4. Cho phép (Allow) → redirect về app, token lưu `_google_token.json`
5. Lần sau không cần consent (token tự refresh)

**Redirect URI** trong Google Cloud Console: `https://stockreport.khoviet.com/oauth2callback`

**Lưu ý**: Nếu OAuth client dùng chung với app khác (vd. pdf2vid), không dùng `include_granted_scopes` — gây lỗi "Scope has changed".

## Chạy ứng dụng

### Web UI (khuyến nghị)

```bash
python server.py
# → http://localhost:8000
```

Giao diện cho phép:
- **Tab CafeF CBTT**: Lọc mã CK/sàn/ngành/chỉ số → Scrape → Sync Drive/Sheet
- **Tab Hải Quan**: Lọc nguồn/năm/loại BC → Tải PDF → Sync Drive/Sheet
  - Filter bar: search + Loại BC + Mã BC + Trạng thái + count + Dọn dẹp
- **Thống kê** download theo sàn/ngành/chỉ số (CafeF) hoặc năm/loại/mã BC (HQ)
- **Sync** lên Google Drive và Google Sheets (chạy nền, không cần giữ tab)
- **Dọn dẹp** files theo filter (sàn, ngành, sync status) với xác nhận
- **Cài đặt** tự động xóa files theo retention period

### CLI (chạy trực tiếp)

```bash
# Scrape tất cả (3 trang đầu)
python cafef_scraper.py

# Scrape mã cụ thể
STOCK_CODE=ACB python cafef_scraper.py

# Scrape tất cả trang
MAX_PAGES=0 python cafef_scraper.py
```

## API Reference

### CafeF CBTT

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/api/stock-data` | Toàn bộ exchanges, industries, indexes |
| `GET` | `/api/tickers?search=FPT` | Tìm ticker (filter: `exchange`, `icb_code`, `index_code`) |
| `GET` | `/api/history?stock_code=ACB&limit=50` | Lịch sử download (phân trang) |
| `GET` | `/api/stats` | Thống kê theo sàn/ngành/chỉ số |
| `POST` | `/api/scrape` | Bắt đầu job `{"stock_code":"ACB","max_pages":0}` |
| `GET` | `/api/scrape/status` | Trạng thái job |
| `POST` | `/api/scrape/stop` | Dừng job |
| `POST` | `/api/gdrive/sync` | Upload PDF lên Google Drive (background) |
| `GET` | `/api/gdrive/test` | Test upload 1 file → xác nhận Drive hoạt động |
| `POST` | `/api/gsheet/sync` | Sync metadata lên Google Sheets (background, incremental) |
| `GET` | `/api/sync/status` | Trạng thái sync hiện tại |

### Hải Quan

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/api/haiquan/scrape` | Bắt đầu tải HQ `{"source":"xlsx","year_from":2009}` |
| `GET` | `/api/haiquan/scrape/status` | Trạng thái job |
| `POST` | `/api/haiquan/scrape/stop` | Dừng job |
| `GET` | `/api/haiquan/history` | Lịch sử tải (filter: search, report_type, report_code, drive_synced; sort: filename, year, file_size, downloaded_at) |
| `GET` | `/api/haiquan/history/filters` | Filter options (years, types, codes, periods) |
| `DELETE` | `/api/haiquan/history/cleanup` | Xóa records + files theo filter (JSON body) |
| `GET` | `/api/haiquan/stats` | Thống kê theo năm/loại/mã BC |
| `POST` | `/api/haiquan/gdrive/sync` | Upload HQ PDFs lên Drive |
| `POST` | `/api/haiquan/gsheet/sync` | Sync HQ metadata lên Google Sheets |
| `GET` | `/api/haiquan/sync/status` | Trạng thái sync |

### Chung

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/api/oauth2/start` | OAuth: trả URL redirect đến Google (yêu cầu admin) |
| `GET` | `/oauth2callback` | OAuth callback: nhận code, lưu token, redirect về / |
| `GET` | `/api/oauth2/status` | Kiểm tra đã có token chưa |
| `GET` | `/api/oauth2/debug` | Debug: client_id + redirect_uri (troubleshooting) |
| `GET` | `/api/settings` | Lấy cài đặt + retention options |
| `POST` | `/api/settings` | Cập nhật cài đặt `{"retention": "1q"}` |
| `POST` | `/api/cleanup/run` | Chạy cleanup thủ công (xóa files hết hạn) |
| `DELETE` | `/api/history/cleanup` | Xóa records + files theo filter (exchange, icb_code, drive_synced) |
| `WS` | `/ws/progress` | WebSocket realtime events (CafeF + HQ progress + sync) |

## Quy ước đặt tên file

```
[ICB_CODE]_[TICKER]_[YEARQ]_[TYPE].pdf
```

| Field | Ví dụ | Mô tả |
|-------|-------|-------|
| ICB_CODE | `8350` | Mã ngành ICB (4 số) |
| TICKER | `ACB` | Mã chứng khoán |
| YEARQ | `2024Q4` | Năm + Quý |
| TYPE | `BCTC` | Loại báo cáo |

Ví dụ: `8350_ACB_2024Q4_BCTC.pdf` → ICB 8350 (Ngân hàng), mã ACB, quý 4/2024, báo cáo tài chính.

## Database

SQLite tại `pdf/_download_history.db`:

| Column | Type | Mô tả |
|--------|------|-------|
| filename | TEXT | Tên file PDF |
| url | TEXT | URL gốc |
| stock_code | TEXT | Mã CK |
| report_type | TEXT | Loại báo cáo |
| quarter_year | TEXT | Năm/Quý |
| icb_code | TEXT | Mã ngành ICB |
| exchange | TEXT | Sàn GD |
| file_size | INTEGER | Dung lượng (bytes) |
| downloaded_at | TEXT | Thời gian tải (ISO) |
| drive_synced | INTEGER | 0/1 — đã sync lên Drive |
| drive_file_id | TEXT | Google Drive file ID |

## Auto-Delete (Cleanup)

Module `cleanup.py` tự động xóa files PDF hết hạn retention.

| Retention | Thời gian | Mặc định |
|-----------|-----------|----------|
| `1w` | 7 ngày | |
| `1m` | 30 ngày | |
| `1q` | 90 ngày | ✅ |
| `1y` | 365 ngày | |
| `never` | Không xóa | |

- **Settings**: lưu vào `pdf/_settings.json`
- **Scheduler**: daemon thread chạy mỗi 24h (tự start cùng server)
- **Cleanup thủ công**: nút "Dọn dẹp ngay" trong Settings modal hoặc `POST /api/cleanup/run`
- **Logic**: query `downloaded_at` < cutoff → xóa file + DB record → xóa thư mục ICB rỗng

## Background Sync

Sync Drive/Sheet chạy trong background thread (daemon), **không phụ thuộc browser tab**:

- **Concurrent**: Drive và Sheet chạy đồng thời, không chặn lẫn nhau
- **Auto Sheet sync**: tự động sync Sheet sau khi scraping hoàn tất (nếu có file mới)
- **OAuth2 only**: dùng quota của user đã đăng nhập, token lưu `_google_token.json`
- **Drive**: batch listing, so sánh file size detect corrupt, non-resumable cho < 5MB
- **Sheet**: hash-based incremental — skip nếu data không thay đổi
- **Sheet columns**: TICKER (hyperlink đến Drive), TIME, TYPE, EXC, IND, INDEX, DATE
- **Tiến trình chi tiết**: broadcast qua WebSocket (`type: sync_progress`)
  - Hiển thị sub-folder + filename đang sync: `☁ Drive sync: [0570] report.pdf`
  - Counts + ETA: `45/200 — ↑12 ⏭33 | ETA: 2m30s`
  - Lỗi upload hiện trong progressNotes section
- **Status API**: `GET /api/sync/status` trả trạng thái cả Drive và Sheet
- **Diagnostic**: `GET /api/gdrive/test` — test upload 1 file PDF, trả kết quả chi tiết
- **OAuth web flow**: production dùng redirect `https://stockreport.khoviet.com/oauth2callback`; `GET /api/oauth2/debug` để verify client_id + redirect_uri khớp Google Cloud Console

## Multi-Ticker Scraping

Scraper hỗ trợ 3 chế độ:

| Chế độ | `STOCK_CODE` | Hành vi |
|--------|-------------|---------|
| Tất cả | _(rỗng)_ | Scrape toàn bộ CBTT mặc định |
| Single | `ACB` | Search 1 mã → scrape tất cả trang |
| Multi | `BSR,OIL,PLX` | Lần lượt search từng mã → scrape |

**Cơ chế search**: Sử dụng CafeF `IformationDisclosure` JS API:
```javascript
IformationDisclosure.refInputAC.value = "BSR";
IformationDisclosure.handleFindDisclosure();
```

**Bảo vệ 3 lớp** chống dữ liệu lạ (stale DOM):
1. **DOM Polling**: Sau khi search, polling bảng HTML mỗi 500ms (max 10s) đợi dòng đầu hiển thị đúng ticker
2. **Pre-filter**: Entries extracted được lọc — chỉ giữ `stock_code == current_ticker`
3. **Safety net**: `_process_entry()` so khớp chính xác `self.current_ticker`

**Crash Recovery** (300-1000+ tickers):
- **Periodic restart**: browser tự restart mỗi `BROWSER_RESTART_INTERVAL` tickers (default 50) để giải phóng memory Chromium
- **Per-ticker isolation**: mỗi ticker xử lý trong `try/except` riêng — 1 lỗi không dừng toàn bộ
- **Auto-recovery**: detect "Page crashed" → restart browser → retry ticker 1 lần
- **Chromium flags**: `--disable-dev-shm-usage`, `--disable-gpu`, `--no-sandbox` tăng stability
- **Tracking**: `crashed_tickers`, `skipped_tickers`, `browser_restarts` trong report JSON + WebSocket progress

## Hải Quan

Module tải báo cáo thống kê xuất nhập khẩu từ Tổng cục Hải quan (`customs.gov.vn`), **hoàn toàn tách biệt** với CafeF CBTT.

### Quy ước đặt tên file HQ

```
{LOẠI_BC}_{KỲ_BC}_{MÃ_BC}.pdf
```

| Field | Giá trị | Mô tả |
|-------|---------|-------|
| LOẠI_BC | `SB`, `CT`, `DC` | Sơ bộ / Chính thức / Điều chỉnh |
| KỲ_BC | `2022T8`, `2021T7K1`, `2021Q2` | Tháng / Nửa tháng / Quý |
| MÃ_BC | `5N`, `1X`, `PTVT` | Mã báo cáo trích từ URL |

Ví dụ:
- `SB_2022T8_5N.pdf` → Sơ bộ, tháng 8/2022, mã 5N
- `CT_2021T7K1_1N.pdf` → Chính thức, kỳ 1 tháng 7/2021, mã 1N
- `CT_2021Q2_PTVT.pdf` → Chính thức, quý 2/2021, mã PTVT
- `CT_2022Q1_PTVT-XK.pdf` → Chính thức, quý 1/2022, xuất khẩu PTVT
- `CT_2021Q4_HTX.pdf` → Từ `Bieu HTX_QIV_2021.pdf` (Roman numeral QIV→Q4)

**Parsing đặc biệt:**
- Prefix không có CT/SB/DC → mặc định `CT` (vd: `EN-PR` → `CT`)
- Roman numerals: `QIV→Q4`, `QIII→Q3`, `QII→Q2`, `QI→Q1`
- NK/XK direction: `-XK` suffix cho xuất khẩu (vd: `PTVT-XKQ1` → `PTVT-XK`)
- Year fallback: filename thiếu năm → dùng năm từ URL path + 1

### HQ Database

SQLite tại `pdf/haiquan/_haiquan_history.db`:

| Column | Type | Mô tả |
|--------|------|-------|
| filename | TEXT | Tên file chuẩn (SB_2022T8_5N.pdf) |
| original_filename | TEXT | Tên file gốc từ URL |
| source_url | TEXT | URL gốc |
| year | INTEGER | Năm |
| month | INTEGER | Tháng |
| quarter | INTEGER | Quý |
| period | TEXT | Kỳ báo cáo (2022T8, 2021T7K1) |
| report_code | TEXT | Mã báo cáo |
| report_type | TEXT | SB / CT / DC |
| file_size | INTEGER | Dung lượng (bytes) |
| downloaded_at | TEXT | Thời gian tải (ISO) |
| drive_synced | INTEGER | 0/1 — đã sync lên Drive |
| drive_file_id | TEXT | Google Drive file ID |
| source | TEXT | xlsx / web |

### HQ Drive Sync

- **Real-time auto sync**: mỗi file tải xong → tự động upload lên Drive (giống CafeF)
  - `upload_single(pdf_path)` gọi ngay trong `on_download` callback
  - Đánh dấu `drive_synced=1` + `drive_file_id` vào SQLite
  - Frontend hiển thị `☁ N` (số file đã sync) cùng progress stats
- Upload flat structure lên folder riêng (`HQ_GOOGLE_DRIVE_FOLDER_ID`)
- Reuse OAuth credentials (chung token với CafeF)
- Incremental: batch-list files trên Drive, skip nếu đã tồn tại + cùng size
- Sau upload: re-scan Drive → populate `drive_file_id` vào SQLite (cho Sheet hyperlinks)
- Progress realtime qua WebSocket (`haiquan_sync_progress`)

### HQ Sheet Sync

- **`HaiQuanSheetSync`** (`haiquan_sync.py`): sync metadata lên Google Sheets
  - Sheet: `"HAI QUAN"`, tab: `"DATA"`
  - Columns: FILENAME (hyperlink → Drive) | YEAR | PERIOD | TYPE | CODE | SIZE | DATE
  - Hash-based incremental: skip nếu data không thay đổi
  - Reuse OAuth credentials + `SHEET_FOLDER_ID` (chung folder với CafeF Sheet)
- API: `POST /api/haiquan/gsheet/sync`

## License

Private — Internal use only.
