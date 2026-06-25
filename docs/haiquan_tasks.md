# Chi tiết Tasks — Triển khai Tab "Hải Quan"

## Phase 1: Core Backend — `haiquan_scraper.py`

### Session 1.1: Scaffold + File Naming Parser

#### Task 1.1.1: Tạo `haiquan_scraper.py` — scaffold
- [ ] Tạo file, import dependencies (pathlib, sqlite3, re, requests, openpyxl, logging)
- [ ] Constants: URL_PATTERN_REGEX, STATUS_MAP, PERIOD_MAP
- [ ] Class `HaiQuanDownloadHistory` — SQLite wrapper
  - `__init__(pdf_dir)`: connect `pdf/haiquan/_haiquan_history.db`
  - `_init_db()`: CREATE TABLE `haiquan_downloads` với schema từ plan
  - `is_downloaded(filename)`: check DB + file exists
  - `add(filename, url, ...)`: INSERT OR REPLACE
  - `count()`, `summary()`, `close()`

**Checkpoint 1.1.1**: `python -c "from haiquan_scraper import HaiQuanDownloadHistory"` — no error

#### Task 1.1.2: `parse_filename(url)` — Quy tắc đặt tên
- [ ] Implement regex parse cho URL filename PDF
- [ ] **Standard pattern**: `(?:\d+)?(\d{4})-T(\d{2})(T|K[12])-(\w+)\((VN)-(SB|CT|DC)\)\.pdf`
  - Bỏ numeric prefix (nếu có)
  - Year: group 1
  - Month: group 2 (bỏ leading zero trong output)
  - Period suffix: group 3 → T → tháng, K1/K2 giữ nguyên
  - Report code: group 4
  - Report type: group 6 (SB/CT/DC)
  - Output: `{type}_{year}T{month}{K1|K2|}_{code}.pdf`
- [ ] **Quarter pattern**: `(\w+)-[NX]KQ(\d+)-(final|SB|CT)\.pdf`
  - Report code: group 1 (e.g. PTVT)
  - Quarter: group 2
  - Status: `final` → `CT`
  - Year: extract từ URL path `/TONG_CUC/{YYYY}/` trừ 1
  - Output: `{type}_{year}Q{quarter}_{code}.pdf`
- [ ] **Fallback**: Nếu không match → return None, log warning

**Checkpoint 1.1.2**: Test parse_filename với TẤT CẢ ví dụ từ user:
```python
assert parse("https://...2022/9/7/2022-T08T-5N(VN-SB).pdf") == {"filename": "SB_2022T8_5N.pdf", ...}
assert parse("https://...2022/4/29/2021-T07K1-1N(VN-CT).pdf") == {"filename": "CT_2021T7K1_1N.pdf", ...}
assert parse("https://...2022/4/29/6542021-T08K2-1N(VN-CT).pdf") == {"filename": "CT_2021T8K2_1N.pdf", ...}
assert parse("https://...2022/4/29/2021-T07T-2X(VN-CT).pdf") == {"filename": "CT_2021T7_2X.pdf", ...}
assert parse("https://...2022/6/10/PTVT-NKQ2-final.pdf") == {"filename": "CT_2021Q2_PTVT.pdf", ...}
assert parse("https://...2022/4/29/2452021-T08K2-1X(VN-CT).pdf") == {"filename": "CT_2021T8K2_1X.pdf", ...}
```

### Session 1.2: URL Import + PDF Download

#### Task 1.2.1: `load_legacy_urls(xlsx_path)`
- [ ] Đọc `docs/haiquan/haiquan.xlsx` bằng openpyxl
- [ ] Extract URLs từ cột LinkSB và LinkCT
- [ ] Cho mỗi URL: gọi `parse_filename()` → metadata
- [ ] Deduplicate (cùng URL chỉ giữ 1)
- [ ] Return list[dict] với keys: url, filename, report_type, year, month, period, report_code, source

**Checkpoint 1.2.1**: Print tổng URLs loaded, expected ~2.653

#### Task 1.2.2: `download_pdf(url, dest_path, ...)`
- [ ] requests.get() với timeout=30, retry 3 lần, exponential backoff
- [ ] Verify Content-Type: application/pdf
- [ ] Verify file size > 1KB (tránh empty/error pages)
- [ ] Resume partial download (Range header) nếu file đã tồn tại partial
- [ ] Return: 'downloaded' | 'skipped' | 'failed'
- [ ] Ghi history vào DB sau khi download thành công

**Checkpoint 1.2.2**: Test download 3 PDFs thật (chọn 3 URLs khác nhau từ xlsx), verify files tồn tại + tên đúng

---

## Phase 2: Server Integration

### Session 2.1: API Endpoints + Background Jobs

#### Task 2.1.1: `HaiQuanScrapeJob` class trong `server.py`
- [ ] Clone pattern từ `ScrapeJob` hiện tại
- [ ] Instance riêng: `haiquan_scrape_job = HaiQuanScrapeJob()`
- [ ] `start(config, loop)`: launch background thread, chạy `haiquan_scraper`
- [ ] `stop()`: set `should_stop = True`
- [ ] `_broadcast_sync(data)`: WS broadcast với `type: "haiquan_progress"`
- [ ] Config params: `source` (xlsx/web/all), `year_from`, `year_to`, `report_types`

**Checkpoint 2.1.1**: POST `/api/haiquan/scrape` → response `{"status": "started"}`, không crash server

#### Task 2.1.2: API Routes `/api/haiquan/*`
- [ ] `POST /api/haiquan/scrape` — start job
- [ ] `GET /api/haiquan/scrape/status` — trạng thái 
- [ ] `POST /api/haiquan/scrape/stop` — dừng job
- [ ] `GET /api/haiquan/history` — query history (filter: year, month, period, report_type, report_code, drive_synced; sort + pagination)
- [ ] `GET /api/haiquan/history/filters` — distinct values cho dropdowns
- [ ] `DELETE /api/haiquan/history/cleanup` — xóa records + files
- [ ] `GET /api/haiquan/stats` — thống kê (by year, by report_type, by report_code)

**Checkpoint 2.1.2**: Curl test mỗi endpoint, verify response format đúng

#### Task 2.1.3: `HaiQuanSyncJob` class + sync API
- [ ] Clone pattern từ `SyncJob` hiện tại
- [ ] Instance riêng: `haiquan_sync_job = HaiQuanSyncJob()`
- [ ] Dùng `HQ_GOOGLE_DRIVE_FOLDER_ID` env var
- [ ] `POST /api/haiquan/gdrive/sync` — start sync
- [ ] `GET /api/haiquan/sync/status` — sync status
- [ ] WS broadcast với `type: "haiquan_sync_progress"`

**Checkpoint 2.1.3**: POST `/api/haiquan/gdrive/sync` → response started (hoặc error nếu chưa config Drive)

---

## Phase 3: Frontend UI

### Session 3.1: Header Navigation + HTML

#### Task 3.1.1: Header Tab Navigation
- [ ] Thêm nav tabs vào header: `CafeF CBTT` | `Hải Quan`
- [ ] CSS cho `.nav-tabs` (pill style, active indicator)
- [ ] Click handler: toggle `display` giữa `#cafef-main` và `#haiquan-main`
- [ ] Wrap `<main>` hiện tại vào `<main id="cafef-main">`

**Checkpoint 3.1.1**: Mở browser → thấy 2 tabs, click chuyển đổi đúng, CafeF vẫn hiển thị mặc định

#### Task 3.1.2: HTML cho tab Hải Quan
- [ ] `<main id="haiquan-main" style="display:none">`
- [ ] Filter panel: Năm (2009-2025), Tháng (1-12), Kỳ (T/K1/K2/Q), Loại (SB/CT/DC), Mã BC
- [ ] Action buttons: Bắt đầu tải / Dừng / Sync Drive
- [ ] Progress card (với prefix `hq-`)
- [ ] Sync status card (với prefix `hq-`)
- [ ] Stats section
- [ ] History table: Mã BC, Năm, Tháng/Quý, Kỳ, Loại, Dung lượng, Đồng bộ, Ngày tải
- [ ] Pagination

**Checkpoint 3.1.2**: Mở tab Hải Quan → thấy filter panel, empty table, buttons đúng

### Session 3.2: Frontend Logic

#### Task 3.2.1: Tạo `haiquan_app.js`
- [ ] State management: `hqState = { ... }`
- [ ] API helper reuse: copy `api()`, `getHeaders()`, `formatSize()`, `formatDate()`, `toast()` 
  (hoặc extract sang `utils.js`)
- [ ] `hq_loadHistory()`, `hq_loadStats()`, `hq_applyFilters()`
- [ ] `hq_startScrape()`, `hq_stopScrape()`
- [ ] `hq_syncDrive()`
- [ ] WebSocket handler: filter messages by type `haiquan_progress` / `haiquan_sync_progress`
- [ ] `hq_handleProgress(data)`, `hq_handleSyncProgress(data)`
- [ ] Init on DOMContentLoaded: chỉ init khi tab Hải Quan được click lần đầu (lazy init)

**Checkpoint 3.2.1**: 
- Click tab Hải Quan → history table loads (trống nếu chưa có data)
- Click "Bắt đầu tải" → progress card hiện, server bắt đầu download
- Click "Sync Drive" → sync hoạt động

---

## Phase 4: Google Drive Sync

### Session 4.1: Clone Drive Sync

#### Task 4.1.1: Tạo `haiquan_sync.py`
- [ ] Clone `GoogleDriveSync` → `HaiQuanDriveSync`
- [ ] PDF dir: `pdf/haiquan/`
- [ ] Drive folder ID: `HQ_GOOGLE_DRIVE_FOLDER_ID`
- [ ] Reuse credentials từ `google_sync._get_credentials()`
- [ ] Upload flat (không subfolders, khác CafeF có ICB subfolders)
- [ ] `upload_all(progress_callback, phase_callback)` → incremental upload

**Checkpoint 4.1.1**: Upload 3 test PDFs lên Drive folder riêng, verify trên web Drive

---

## Phase 5: Integration Test

### Session 5.1: End-to-End Verification

#### Task 5.1.1: Isolation Test
- [ ] ✅ CafeF tab: start scrape → chạy bình thường
- [ ] ✅ Hải Quan tab: start scrape → chạy bình thường  
- [ ] ✅ Chạy đồng thời cả 2 → không conflict
- [ ] ✅ Stop CafeF → Hải Quan vẫn chạy (và ngược lại)
- [ ] ✅ Drive sync CafeF → vào folder CafeF, Drive sync HQ → vào folder HQ
- [ ] ✅ DB riêng biệt: `pdf/_download_history.db` vs `pdf/haiquan/_haiquan_history.db`

**Checkpoint 5.1.1**: All isolation checks pass

#### Task 5.1.2: File Naming Verification
- [ ] Download 10+ PDFs từ xlsx URLs
- [ ] Verify mỗi file được đặt tên đúng theo quy tắc
- [ ] Verify edge cases: numeric prefix, quarter pattern, year fallback

**Checkpoint 5.1.2**: Tất cả files có tên đúng theo quy tắc

---

## Phase 6: Documentation

### Session 6.1: Docs Update

#### Task 6.1.1: Cập nhật `.env.example`
- [ ] Thêm `HQ_*` env vars với comments

#### Task 6.1.2: Cập nhật `CHANGELOG.md`
- [ ] Ghi nhận feature mới

#### Task 6.1.3: Cập nhật `README.md`
- [ ] Hướng dẫn cấu hình Hải Quan

---

## Tổng kết

| Phase | Sessions | Tasks | Estimated |
|---|---|---|---|
| 1. Core Backend | 2 | 4 | 1-2 sessions |
| 2. Server Integration | 1 | 3 | 1 session |
| 3. Frontend UI | 2 | 3 | 1-2 sessions |
| 4. Drive Sync | 1 | 1 | 0.5 session |
| 5. Integration Test | 1 | 2 | 0.5 session |
| 6. Documentation | 1 | 3 | 0.5 session |
| **Tổng** | **8** | **16** | **~5-6 sessions** |
