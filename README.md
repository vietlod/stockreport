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

# Google Integration
GOOGLE_SERVICE_ACCOUNT_KEY=./google_oauth_credentials.json
GOOGLE_DRIVE_FOLDER_ID=<your-folder-id>
GOOGLE_SHEET_FOLDER_ID=<your-folder-id>
```

### 3. Google OAuth (tuỳ chọn)

File `google_oauth_credentials.json` là OAuth2 Client credentials (web type).

Lần đầu sử dụng Sync Drive/Sheet:
1. Browser mở trang Google consent
2. Đăng nhập và cấp quyền
3. Token lưu tự động vào `_google_token.json`

> **Lưu ý**: Nếu muốn dùng Service Account, tạo key từ Google Cloud Console
> và thay đổi code trong `google_sync.py` (sử dụng `from_service_account_file`).

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
- **Sync** lên Google Drive và Google Sheets

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
| `POST` | `/api/gdrive/sync` | Upload PDF lên Google Drive |
| `POST` | `/api/gsheet/sync` | Sync metadata lên Google Sheets |
| `WS` | `/ws/progress` | WebSocket realtime events |

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

## License

Private — Internal use only.
