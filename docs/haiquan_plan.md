# Kế hoạch Triển khai Tab "Hải Quan" — Clone & Isolate từ CafeF CBTT

## 1. Mục tiêu

- **Cô lập (isolate)** flow "CafeF CBTT" hiện tại thành module độc lập
- **Nhân bản (clone)** sang flow "Hải Quan" mới, **hoàn toàn tách biệt**
- Tải toàn bộ báo cáo hải quan (PDF) về local (VPS) và đồng bộ lên Google Drive
- **Tuyệt đối không ảnh hưởng** đến hoạt động và độ ổn định của "CafeF CBTT"

---

## 2. Kết quả Nghiên cứu (tóm tắt)

### 2.1. Nguồn dữ liệu PDF

| Giai đoạn | URL Pattern | Nguồn |
|---|---|---|
| 2009-2013 | `files.customs.gov.vn/TONG_CUC/DocLib/.../{filename}.pdf` | `haiquan.xlsx` |
| 2013-2021 | `files.customs.gov.vn/TONG_CUC/Lists/ThongKeHaiQuanLichCongBo/Attachments/{ID}/{filename}.pdf` | `haiquan.xlsx` |
| 2022-nay | `files.customs.gov.vn/CustomsCMS/TONG_CUC/{YYYY}/{M}/{D}/{filename}.pdf` | `haiquan.xlsx` + Web crawl |

**Tổng URLs từ haiquan.xlsx**: ~2.653 URLs (1.680 dòng, 01/2009 → 09/2022)

### 2.2. Quy ước đặt tên file PDF (output)

**Tên file đầu ra**: `{LOẠI_BC}_{KỲ_BC}_{MÃ_BC}.pdf`

#### LOẠI BÁO CÁO

| Trong URL | Ký hiệu | Ý nghĩa |
|---|---|---|
| `VN-SB` | `SB` | Sơ bộ (Preliminary) |
| `VN-CT` hoặc `final` | `CT` | Chính thức (Official/Final) |
| `VN-DC` | `DC` | Điều chỉnh (Adjusted) |

#### KỲ BÁO CÁO (từ filename trong URL)

| Pattern URL | KỲ_BC output | Ý nghĩa |
|---|---|---|
| `T08T` | `{YYYY}T8` | Tháng 8 trọn (bỏ suffix `T`, bỏ leading zero) |
| `T07K1` | `{YYYY}T7K1` | Kỳ 1 tháng 7 (ngày 1-15) |
| `T08K2` | `{YYYY}T8K2` | Kỳ 2 tháng 8 (ngày 16-cuối tháng) |
| `NKQ2` / `XKQ2` | `{YYYY}Q2` | Quý 2 |

#### MÃ BÁO CÁO

Giữ nguyên mã từ filename: `1X`, `1N`, `2X`, `2N`, `3X`, `3N`, `5X`, `5N`, `PTVT`, etc.

#### Ví dụ đầy đủ

| URL filename | → Output | Giải thích |
|---|---|---|
| `2022-T08T-5N(VN-SB).pdf` | `SB_2022T8_5N.pdf` | T08T → T8 |
| `2021-T07K1-1N(VN-CT).pdf` | `CT_2021T7K1_1N.pdf` | K1 giữ nguyên |
| `6542021-T08K2-1N(VN-CT).pdf` | `CT_2021T8K2_1N.pdf` | Prefix `654` bỏ |
| `2021-T07T-2X(VN-CT).pdf` | `CT_2021T7_2X.pdf` | T07T → T7 |
| `PTVT-NKQ2-final.pdf` | `CT_2021Q2_PTVT.pdf` | Final→CT, Year=URL_year-1 |
| `2452021-T08K2-1X(VN-CT).pdf` | `CT_2021T8K2_1X.pdf` | Prefix `245` bỏ |

#### Trường hợp ngoại lệ

- **Numeric prefix**: `6542021-T08K2...` → bỏ prefix, parse phần `{YYYY}-T{MM}...` bình thường
- **Year không xác định từ filename**: Lấy `YYYY` từ URL path `/TONG_CUC/{YYYY}/...` **trừ đi 1**
- **Pattern quý**: `PTVT-NKQ2-final.pdf` → Mã BC = `PTVT`, kỳ = `Q2`, loại = `CT` (final)

---

## 3. Chiến lược Isolation

| Layer | CafeF CBTT | Hải Quan | Shared |
|---|---|---|---|
| **Scraper** | `cafef_scraper.py` | `haiquan_scraper.py` | Không |
| **SQLite DB** | `pdf/_download_history.db` | `pdf/haiquan/_haiquan_history.db` | Không |
| **PDF Dir** | `pdf/{ICB_CODE}/` | `pdf/haiquan/` | Không |
| **Server Jobs** | `scrape_job`, `sync_job` | `haiquan_scrape_job`, `haiquan_sync_job` | Không |
| **API Prefix** | `/api/scrape`, `/api/history` | `/api/haiquan/*` | Auth, OAuth, Settings |
| **WS Message Type** | `progress`, `sync_progress` | `haiquan_progress`, `haiquan_sync_progress` | WebSocket conn |
| **JS File** | `app.js` | `haiquan_app.js` | `index.html`, `style.css` |
| **GDrive Folder** | `GOOGLE_DRIVE_FOLDER_ID` | `HQ_GOOGLE_DRIVE_FOLDER_ID` | OAuth credentials |

---

## 4. Kiến trúc Triển khai

### 4.1. Files mới tạo

| File | Mô tả |
|---|---|
| `haiquan_scraper.py` | Core scraper: parse URL, download PDF, manage DB |
| `haiquan_sync.py` | Google Drive sync cho hải quan |
| `static/haiquan_app.js` | Frontend logic cho tab Hải Quan |

### 4.2. Files cần sửa

| File | Thay đổi |
|---|---|
| `static/index.html` | Thêm header nav tabs + `<main id="haiquan-main">` |
| `static/style.css` | Styles cho nav tabs |
| `server.py` | Thêm API endpoints `/api/haiquan/*` + HaiQuanScrapeJob/SyncJob |
| `.env` | Thêm `HQ_*` env vars |

### 4.3. Cấu trúc lưu trữ

```
pdf/haiquan/
├── _haiquan_history.db          ← SQLite DB riêng
├── SB_2022T8_5N.pdf             ← Flat, tên chuẩn hóa
├── CT_2021T7_2X.pdf
├── CT_2021T7K1_1N.pdf
└── ...
```

### 4.4. Server API mới

```
POST /api/haiquan/scrape           → Start scrape
GET  /api/haiquan/scrape/status    → Scrape status
POST /api/haiquan/scrape/stop      → Stop scrape
GET  /api/haiquan/history          → Download history
GET  /api/haiquan/history/filters  → Filter options
DELETE /api/haiquan/history/cleanup → Cleanup
GET  /api/haiquan/stats            → Statistics
POST /api/haiquan/gdrive/sync      → Drive sync
GET  /api/haiquan/sync/status      → Sync status
```

### 4.5. Database Schema

Bảng `haiquan_downloads` (trong `_haiquan_history.db`):

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto increment |
| `filename` | TEXT UNIQUE | Tên file chuẩn hóa (SB_2022T8_5N.pdf) |
| `url` | TEXT | URL gốc |
| `original_filename` | TEXT | Tên file gốc từ URL |
| `year` | INTEGER | Năm báo cáo |
| `month` | INTEGER | Tháng (NULL nếu quý) |
| `quarter` | INTEGER | Quý (NULL nếu tháng) |
| `period` | TEXT | T, K1, K2, Q |
| `report_code` | TEXT | 1X, 1N, 2X, PTVT... |
| `report_type` | TEXT | SB, CT, DC |
| `file_size` | INTEGER | Bytes |
| `downloaded_at` | TEXT | ISO timestamp |
| `source` | TEXT | xlsx_legacy / web_crawl |
| `drive_synced` | INTEGER | 0 / 1 |
| `drive_file_id` | TEXT | Google Drive file ID |

---

## 5. Rủi ro & Giải pháp

| Rủi ro | Giải pháp |
|---|---|
| URL broken (404) | Retry 3x, log warning, skip |
| Network timeout tới customs.gov.vn | Expo backoff, concurrent limit, resume |
| Duplicate filename (nhiều URL → cùng output name) | Check DB trước khi download, skip nếu đã có |
| PDF không parse được filename | Log warning, skip hoặc download với tên gốc |
| Impact CafeF CBTT | ✅ Hoàn toàn isolated (xem bảng §3) |
| Dung lượng storage | ~2.653 PDFs × ~200KB ≈ 530MB — acceptable |
