# CafeF CBTT PDF Scraper

## Tasks
- [x] Nghiên cứu cấu trúc trang https://m.cafef.vn/du-lieu/cong-bo-thong-tin.chn
- [x] Thiết kế giải pháp và viết implementation plan
- [x] Cài đặt dependencies (playwright, requests, etc.)
- [x] Xây dựng script scraper
  - [x] Module 1: Sử dụng Playwright render page & intercept network requests để tìm API endpoint
  - [x] Module 2: Parse danh sách CBTT entries (mã CK, tên DN, ngày, loại báo cáo, link)
  - [x] Module 3: Truy cập từng entry → tìm link PDF
  - [x] Module 4: Download PDF về `d:\FLOW\Crawl\pdf`
- [x] Cấu hình (.env cho các tham số filter)
- [x] Test & verify (18 PDFs downloaded, naming: ACB_2025Q2_BCTC.pdf)
