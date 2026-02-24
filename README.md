# CafeF CBTT Report Manager

Hệ thống scraping, quản lý và đồng bộ báo cáo Công bố thông tin (CBTT) từ CafeF với giao diện web hiện đại.

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
├── cafef_scraper.py       # Scraper chính (Playwright)
├── stock_data.py          # StockRegistry — lookup ticker metadata
├── google_sync.py         # Google Drive + Sheets sync (OAuth2)
├── cleanup.py             # Auto-delete files theo retention period
├── server.py              # FastAPI web server
├── .env                   # Cấu hình (xem bên dưới)
├── requirements.txt       # Python dependencies
├── google_oauth_credentials.json  # Google OAuth2 credentials
│
├── static/                # Frontend UI
│   ├── index.html         # Single-page app
│   ├── style.css          # Dark-mode design
│   └── app.js             # Client-side logic
│
├── pdf/                   # PDF output (theo ICB code)
│   ├── 8350/              # Ngân hàng
│   ├── 2350/              # Xây dựng
│   └── .../
│
├── stock_exchange.xlsx    # Dữ liệu sàn GD
├── stock_industry.xlsx    # Dữ liệu ngành ICB
└── stock_index.xlsx       # Dữ liệu chỉ số
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

# Google Sign-In (optional)
GOOGLE_CLIENT_ID=
ALLOWED_EMAILS=user@example.com
JWT_SECRET=<random-string>

# Google Integration (OAuth2 only)
GOOGLE_OAUTH_CREDENTIALS=./google_oauth_credentials.json
OAUTH_REDIRECT_URI=https://stockreport.khoviet.com/oauth2callback
GOOGLE_DRIVE_FOLDER_ID=<your-folder-id>
GOOGLE_SHEET_FOLDER_ID=<your-folder-id>
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
- **Lọc** theo mã CK, sàn, ngành ICB, chỉ số, khoảng thời gian
- **Scrape** với progress realtime qua WebSocket
- **Thống kê** download theo sàn/ngành/chỉ số
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
| `GET` | `/api/oauth2/start` | OAuth: trả URL redirect đến Google (yêu cầu admin) |
| `GET` | `/oauth2callback` | OAuth callback: nhận code, lưu token, redirect về / |
| `GET` | `/api/oauth2/status` | Kiểm tra đã có token chưa |
| `GET` | `/api/oauth2/debug` | Debug: client_id + redirect_uri (troubleshooting) |
| `POST` | `/api/gsheet/sync` | Sync metadata lên Google Sheets (background, incremental) |
| `GET` | `/api/sync/status` | Trạng thái sync hiện tại |
| `GET` | `/api/settings` | Lấy cài đặt + retention options |
| `POST` | `/api/settings` | Cập nhật cài đặt `{"retention": "1q"}` |
| `POST` | `/api/cleanup/run` | Chạy cleanup thủ công (xóa files hết hạn) |
| `DELETE` | `/api/history/cleanup` | Xóa records + files theo filter (exchange, icb_code, drive_synced) |
| `WS` | `/ws/progress` | WebSocket realtime events (scrape + sync progress) |

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

## License

Private — Internal use only.
