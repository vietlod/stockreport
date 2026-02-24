# CafeF CBTT Report Manager — Walkthrough

## Summary

Built a complete scraper management system with **4 modules**:

| Module | File | Status |
|---|---|---|
| Stock Registry | `stock_data.py` | ✅ 3179 tickers, 5 sàn, 36 ICB |
| Scraper | `cafef_scraper.py` | ✅ New naming, ICB dirs, rate limiting |
| Google Sync | `google_sync.py` | ✅ OAuth2 Drive + Sheets |
| Web UI | `server.py` + `static/` | ✅ FastAPI + dark-mode UI |

---

## Changes Made

### Phase 1: `stock_data.py` (NEW)
- `StockRegistry` class loads `stock_exchange.xlsx`, `stock_industry.xlsx`, `stock_index.xlsx`
- Lookup methods: `get_exchange()`, `get_icb_code()`, `get_icb_name()`, `get_indexes()`
- Group methods: `tickers_by_exchange()`, `tickers_by_icb_code()`, `tickers_by_index()`
- `to_json()` for frontend API

### Phase 2: `cafef_scraper.py` (MODIFIED)
- **Naming**: `[ICB_CODE]_[TICKER]_[YEARQ]_[TYPE].pdf` (e.g. `8350_ACB_2024Q4_BCTC.pdf`)
- **Directories**: `pdf/[ICB_CODE]/` subdirectories
- **SQLite**: Added `icb_code`, `exchange` columns with migration
- **Rate limiting**: Adaptive `PAGE_DELAY` + `DOWNLOAD_DELAY`, exponential backoff every 20 pages
- **MAX_PAGES=0**: Fetches all available pages

### Phase 3: `google_sync.py` (NEW)
- **OAuth2 flow**: Uses `google_oauth_credentials.json` (web type), saves token locally
- `GoogleDriveSync`: Uploads PDFs with ICB subfolder mirroring, skips existing files
- `GoogleSheetSync`: Syncs to "CAFEF" sheet with columns: TICKER, TIME, TYPE, EXC, IND, INDEX

### Phase 4: Web UI
- **[server.py](file:///d:/FLOW/Crawl/server.py)**: FastAPI with REST API + WebSocket
- **[index.html](file:///d:/FLOW/Crawl/static/index.html)**: Filter panel (ticker/exchange/ICB/index), time range, progress, stats, history
- **[style.css](file:///d:/FLOW/Crawl/static/style.css)**: Dark mode premium design (deep slate + violet accents)
- **[app.js](file:///d:/FLOW/Crawl/static/app.js)**: Autocomplete, WebSocket progress, pagination

---

## Verification Results

### API Endpoints (all ✅ 200 OK)

| Endpoint | Result |
|---|---|
| `GET /api/stock-data` | 5 exchanges, 36 industries, 5 indexes |
| `GET /api/tickers?search=FPT` | 77 tickers found |
| `GET /api/stats` | 80 files, 46 stocks, 878.6 MB |
| `GET /api/history` | 80 records with ICB/exchange data |
| `GET /` | 9777 bytes HTML |

### Scraper Test
- 50 entries across 3 pages, 30 new PDFs downloaded
- Files correctly organized: `pdf/1730/`, `pdf/2350/`, `pdf/7570/`, etc.

---

## How to Test

```bash
# Start server
python server.py

# Open in browser
http://localhost:8000
```

### Google OAuth (first time)
Click **Sync Drive** or **Sync Sheet** → browser opens for Google consent → authorize → token saved to `_google_token.json` for future use.

### `.env` Configuration

```env
STOCK_CODE=           # filter by ticker (empty = all)
MAX_PAGES=3           # 0 = fetch all pages
PDF_DIR=./pdf
HEADLESS=true
PAGE_DELAY=1.5
DOWNLOAD_DELAY=0.5
GOOGLE_SERVICE_ACCOUNT_KEY=./google_oauth_credentials.json
GOOGLE_DRIVE_FOLDER_ID=1ovUT6Qatvq2jsUuYLV757NEOIasLJEqh
GOOGLE_SHEET_FOLDER_ID=1ovUT6Qatvq2jsUuYLV757NEOIasLJEqh
```
