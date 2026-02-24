# CafeF CBTT PDF Scraper

Xây dựng ứng dụng Python scrape danh sách Công bố thông tin (CBTT) từ CafeF và tải các file PDF báo cáo tài chính về `d:\FLOW\Crawl\pdf`.

## Bối cảnh kỹ thuật

- **Trang nguồn**: `https://m.cafef.vn/du-lieu/cong-bo-thong-tin.chn`
- **Đặc điểm**: Dữ liệu được load động qua AJAX/JavaScript → Không thể scrape bằng `requests` + `BeautifulSoup` thuần
- **Giải pháp**: Sử dụng **Playwright (Python)** để:
  1. Render page đầy đủ (headless browser)
  2. Intercept network requests → tìm API endpoint thực sự
  3. Tương tác với form filter / pagination
  4. Trích xuất link PDF và download

## Proposed Changes

### Scraper Application

#### [NEW] [requirements.txt](file:///d:/FLOW/Crawl/requirements.txt)
- `playwright` - headless browser automation
- `requests` - HTTP download PDFs
- `python-dotenv` - quản lý cấu hình qua `.env`

---

#### [NEW] [.env](file:///d:/FLOW/Crawl/.env)
Cấu hình filter:
- `STOCK_CODE` - Mã chứng khoán (mặc định: rỗng = tất cả)
- `MAX_PAGES` - Số trang tối đa cần crawl (mặc định: 3)
- `PDF_DIR` - Thư mục lưu PDF (mặc định: `./pdf`)
- `HEADLESS` - Chạy browser ẩn hay hiện (mặc định: `true`)

---

#### [NEW] [cafef_scraper.py](file:///d:/FLOW/Crawl/cafef_scraper.py)

**Chiến lược 2 phase:**

**Phase 1 - Network Intercept (tự động):**
- Dùng Playwright mở trang CBTT
- Bật `page.on("response")` để bắt tất cả XHR/fetch requests
- Tìm request trả về danh sách CBTT (thường là HTML fragment hoặc JSON)
- Log endpoint URL + params để sử dụng lại

**Phase 2 - Scrape & Download:**
- Parse HTML/JSON response → extract danh sách entries gồm:
  - Mã CK, tên doanh nghiệp, ngày, loại báo cáo
  - Link đến trang chi tiết hoặc link PDF trực tiếp
- Nếu link là trang chi tiết → navigate đến đó và tìm link PDF (thường có pattern `*.pdf` hoặc nằm trong thẻ `<a>` với text "Tải về")
- Download PDF qua `requests` (không cần browser) → lưu vào `d:\FLOW\Crawl\pdf`
- Naming convention: `{MaCK}_{NgayBaoCao}_{LoaiBaoCao}.pdf`

**Xử lý pagination:**
- Sau khi load trang đầu, click "Trang tiếp" hoặc page numbers
- Intercept thêm responses → lặp lại parse + download
- Dừng khi hết trang hoặc đạt `MAX_PAGES`

**Error handling:**
- Retry download thất bại (max 3 lần)
- Skip file đã tồn tại (tránh download lại)
- Log chi tiết vào console + file log

## Verification Plan

### Automated Test
```bash
cd d:\FLOW\Crawl
pip install -r requirements.txt
playwright install chromium
python cafef_scraper.py
```
- Xác nhận script chạy không lỗi
- Kiểm tra thư mục `pdf/` có file PDF mới
- Mở 1-2 file PDF để verify nội dung đúng báo cáo tài chính

### Manual Verification  
- Kiểm tra file PDF trong `d:\FLOW\Crawl\pdf` đã đúng tên và nội dung
- So sánh số lượng file tải về với số lượng hiển thị trên trang CafeF
