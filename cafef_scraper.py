"""
CafeF CBTT (Công bố thông tin) PDF Scraper
==========================================
Scrape danh sách CBTT từ CafeF và tải PDF báo cáo tài chính.

Sử dụng Playwright để render trang động, intercept network requests,
parse entries và download PDF files.

Usage:
    python cafef_scraper.py
"""

import os
import re
import sys
import time
import json
import sqlite3
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_data import registry as stock_registry

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

STOCK_CODE = os.getenv("STOCK_CODE", "").strip()
MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))  # 0 = fetch all pages
PDF_DIR = Path(os.getenv("PDF_DIR", "./pdf"))
# Lọc thời gian (từ config API, mặc định None = không lọc)
TIME_FROM_YEAR = None
TIME_FROM_QUARTER = ""
TIME_TO_YEAR = None
TIME_TO_QUARTER = ""
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
PAGE_DELAY = float(os.getenv("PAGE_DELAY", "1.5"))  # delay giữa các trang (giây)
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "0.5"))  # delay giữa các PDF

BASE_URL = "https://cafef.vn"
CBTT_URL = "https://cafef.vn/du-lieu/cong-bo-thong-tin.chn"
MOBILE_CBTT_URL = "https://m.cafef.vn/du-lieu/cong-bo-thong-tin.chn"

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("cafef_scraper")

# ── Helpers ─────────────────────────────────────────────────────────────────

# Mapping loại báo cáo → viết tắt chuẩn
REPORT_TYPE_MAP = {
    "kết quả kinh doanh": "KQKD",
    "kết quả hoạt động kinh doanh": "KQKD",
    "báo cáo kết quả": "KQKD",
    "lãi lỗ": "KQKD",
    "income statement": "KQKD",
    "cân đối kế toán": "CDKT",
    "bảng cân đối": "CDKT",
    "balance sheet": "CDKT",
    "tài sản": "CDKT",
    "lưu chuyển tiền tệ": "LCTT",
    "dòng tiền": "LCTT",
    "cash flow": "LCTT",
    "báo cáo thường niên": "BCTN",
    "thường niên": "BCTN",
    "annual report": "BCTN",
    "thuyết minh báo cáo": "TMBC",
    "thuyết minh": "TMBC",
    "thuyết minh bctc": "TMBC",
    "báo cáo tài chính": "BCTC",
    "tài chính": "BCTC",
    "financial statement": "BCTC",
    "báo cáo tài chính hợp nhất": "BCTC_HN",
    "hợp nhất": "BCTC_HN",
    "báo cáo tài chính công ty mẹ": "BCTC_ME",
    "công ty mẹ": "BCTC_ME",
    "báo cáo quản trị": "BCQT",
    "quản trị": "BCQT",
    "nghị quyết": "NQ",
    "đại hội đồng cổ đông": "DHCD",
    "điều lệ": "DL",
}


def normalize_report_type(raw_type: str) -> str:
    """Chuyển tên báo cáo đầy đủ thành mã viết tắt chuẩn."""
    if not raw_type:
        return "BCTC"
    lower = raw_type.strip().lower()
    # Exact / substring match
    for keyword, abbr in REPORT_TYPE_MAP.items():
        if keyword in lower:
            return abbr
    # Nếu bản thân đã là viết tắt (VD: "KQKD", "CDKT")
    upper = raw_type.strip().upper()
    if upper in REPORT_TYPE_MAP.values():
        return upper
    return sanitize_filename(raw_type)[:20]


def extract_quarter_year(date_str: str, report_text: str = "") -> str:
    """Trích xuất năm + quý từ date string hoặc report text.
    
    Trả về format: 2024Q4, 2024, etc.
    """
    result_year = ""
    result_quarter = ""

    # Tìm quý từ report text trước (thường chính xác hơn)
    combined = f"{report_text} {date_str}"

    # Pattern: "quý 2 năm 2025", "Quý 4/2024", "Q4/2024", "Quý IV năm 2024"
    q_patterns = [
        # "quý 2 năm 2025" or "quý 2, năm 2025"
        r'[Qq]u[ýy]\s+(\d)\s*[,.]?\s*n[aă]m\s*(\d{4})',
        # "quý II năm 2025" or "quý IV, năm 2024"  
        r'[Qq]u[ýy]\s+(I{1,3}V?|IV)\s*[,.]?\s*n[aă]m\s*(\d{4})',
        # "quý 2 2025" (space only)
        r'[Qq]u[ýy]\s+(\d)\s+(\d{4})',
        # "Q4/2024" or "Quý 4/2024"
        r'[Qq]u?[ýy]?\s*(\d)\s*[/\-]\s*(\d{4})',
        # "Q4-2024"
        r'[Qq](\d)\s*[/\-]\s*(\d{4})',
        # "2024Q4" or "2024 Q4"
        r'(\d{4})\s*[Qq](\d)',
    ]

    roman_map = {"I": "1", "II": "2", "III": "3", "IV": "4"}

    for pat in q_patterns:
        m = re.search(pat, combined, re.IGNORECASE)
        if m:
            g1, g2 = m.group(1), m.group(2)
            # Xác định đâu là quý, đâu là năm
            if len(g2) == 4 and g2.isdigit():
                result_year = g2
                q = roman_map.get(g1.upper(), g1) if not g1.isdigit() else g1
                result_quarter = q
            elif len(g1) == 4 and g1.isdigit():
                result_year = g1
                result_quarter = g2
            break

    # Nếu chưa tìm được năm → tìm năm đơn lẻ
    if not result_year:
        year_m = re.search(r'(20\d{2})', combined)
        if year_m:
            result_year = year_m.group(1)

    # Nếu chưa tìm được quý → thử từ tháng trong date
    if not result_quarter and date_str:
        # Pattern: dd/mm/yyyy hoặc yyyy-mm-dd
        date_m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', date_str)
        if date_m:
            parts = [date_m.group(1), date_m.group(2), date_m.group(3)]
            if len(parts[2]) == 4:
                month = int(parts[1])
                result_year = result_year or parts[2]
            elif len(parts[0]) == 4:
                month = int(parts[1])
                result_year = result_year or parts[0]
            else:
                month = 0

            if month:
                result_quarter = str((month - 1) // 3 + 1)

    # Format kết quả
    if result_year and result_quarter:
        return f"{result_year}Q{result_quarter}"
    elif result_year:
        return result_year
    return ""


def _quarter_in_range(quarter_year: str) -> bool:
    """Kiểm tra quarter_year có nằm trong khoảng TIME_FROM_* .. TIME_TO_* không."""
    if not quarter_year or TIME_FROM_YEAR is None:
        return True
    qy = quarter_year.strip().upper()
    year, quarter = 0, 0
    if "Q" in qy:
        parts = qy.split("Q")
        year = int(parts[0]) if parts[0].isdigit() else 0
        quarter = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    elif qy.isdigit():
        year = int(qy)
        quarter = 0
    if year == 0:
        return True
    from_year = TIME_FROM_YEAR or 0
    to_year = TIME_TO_YEAR or 9999
    from_q = int(TIME_FROM_QUARTER.replace("Q", "")) if TIME_FROM_QUARTER else 1
    to_q = int(TIME_TO_QUARTER.replace("Q", "")) if TIME_TO_QUARTER else 4
    # So sánh: year*4 + quarter (Q1=1..Q4=4)
    entry_val = year * 4 + (quarter if quarter else 1)
    range_min = from_year * 4 + from_q
    range_max = to_year * 4 + to_q
    if quarter == 0:
        entry_val = year * 4 + 1
        return range_min <= year * 4 + 4 and range_max >= year * 4 + 1
    return range_min <= entry_val <= range_max


def sanitize_filename(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ khỏi tên file."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name.strip('_. ')
    return name[:200]  # giới hạn độ dài


# ── Download History (SQLite) ─────────────────────────────────────────────────

class DownloadHistory:
    """Quản lý lịch sử download bằng SQLite.
    
    Database: _download_history.db trong thư mục PDF.
    Bảng `downloads` lưu: filename, url, stock_code, report_type,
    quarter_year, file_size, downloaded_at.
    """

    def __init__(self, pdf_dir: Path):
        self.db_path = pdf_dir / "_download_history.db"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self):
        """Tạo bảng nếu chưa tồn tại."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                filename     TEXT UNIQUE NOT NULL,
                url          TEXT,
                stock_code   TEXT,
                report_type  TEXT,
                quarter_year TEXT,
                icb_code     TEXT,
                exchange     TEXT,
                file_size    INTEGER,
                downloaded_at TEXT
            )
        """)
        # Migration: add columns if missing
        for col, col_type in [("icb_code", "TEXT"), ("exchange", "TEXT")]:
            try:
                self.conn.execute(f"ALTER TABLE downloads ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column already exists
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_stock ON downloads(stock_code)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_quarter ON downloads(quarter_year)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_icb ON downloads(icb_code)")
        self.conn.commit()
        cnt = self.conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        if cnt:
            log.info(f"📊 Download history DB: {cnt} records đã ghi nhận")

    def is_downloaded(self, filename: str) -> bool:
        """Kiểm tra file đã download chưa.
        
        True nếu: có trong DB VÀ file vật lý tồn tại trên disk.
        Nếu file bị xóa manual → xóa record và cho tải lại.
        """
        row = self.conn.execute(
            "SELECT id FROM downloads WHERE filename = ?", (filename,)
        ).fetchone()
        if not row:
            return False

        # Tìm file trong cả thư mục gốc và sub-dirs (ICB_CODE)
        pdf_path = self.db_path.parent / filename
        if not pdf_path.exists():
            # Tìm trong sub-directories
            for sub in self.db_path.parent.iterdir():
                if sub.is_dir() and (sub / filename).exists():
                    pdf_path = sub / filename
                    break
        if pdf_path.exists():
            return True

        # File trong DB nhưng bị xóa trên disk → cho tải lại
        self.conn.execute("DELETE FROM downloads WHERE filename = ?", (filename,))
        self.conn.commit()
        log.info(f"  ♻ {filename}: trong DB nhưng không còn trên disk, sẽ tải lại")
        return False

    def add(self, filename: str, url: str, file_size: int,
            stock_code: str = "", report_type: str = "", quarter_year: str = "",
            icb_code: str = "", exchange: str = ""):
        """Ghi nhận file đã download thành công."""
        self.conn.execute("""
            INSERT OR REPLACE INTO downloads
                (filename, url, stock_code, report_type, quarter_year,
                 icb_code, exchange, file_size, downloaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (filename, url, stock_code, report_type, quarter_year,
              icb_code, exchange, file_size, datetime.now().isoformat()))
        self.conn.commit()

    @property
    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]

    def summary(self) -> dict:
        """Thống kê tổng hợp cho monitoring."""
        cur = self.conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT stock_code) as stocks,
                   SUM(file_size) as total_size,
                   MIN(downloaded_at) as first_download,
                   MAX(downloaded_at) as last_download
            FROM downloads
        """)
        row = cur.fetchone()
        return {
            "total_files": row[0],
            "unique_stocks": row[1],
            "total_size_mb": round((row[2] or 0) / 1024 / 1024, 1),
            "first_download": row[3],
            "last_download": row[4],
        }

    def close(self):
        self.conn.close()


def download_pdf(url: str, dest: Path, history: DownloadHistory = None,
                 max_retries: int = 3,
                 stock_code: str = "", report_type: str = "",
                 quarter_year: str = "", icb_code: str = "",
                 exchange: str = "") -> str:
    """Download PDF file với retry logic + kiểm tra history.
    
    Returns: 'skipped' | 'downloaded' | 'failed'
    """
    filename = dest.name

    # Kiểm tra download history trước
    if history and history.is_downloaded(filename):
        log.info(f"  ⏭ Đã tải trước đó: {filename}")
        return "skipped"

    # Kiểm tra file vật lý (chưa có trong DB)
    if dest.exists():
        file_size = dest.stat().st_size
        log.info(f"  ✔ Đã tồn tại trên disk: {filename} ({file_size:,} bytes)")
        if history:
            history.add(filename, url, file_size, stock_code, report_type,
                       quarter_year, icb_code, exchange)
        return "skipped"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": BASE_URL,
    }

    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"  ⬇ Đang tải ({attempt}/{max_retries}): {url}")
            resp = requests.get(url, headers=headers, timeout=60, stream=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                log.warning(f"  ⚠ Content-Type không phải PDF: {content_type}")

            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = dest.stat().st_size
            if file_size < 1024:
                log.warning(f"  ⚠ File quá nhỏ ({file_size} bytes)")

            log.info(f"  ✔ Đã lưu: {filename} ({file_size:,} bytes)")
            if history:
                history.add(filename, url, file_size, stock_code, report_type,
                           quarter_year, icb_code, exchange)
            return "downloaded"

        except Exception as e:
            log.error(f"  ✖ Lỗi attempt {attempt}: {e}")
            if dest.exists():
                dest.unlink()
            if attempt < max_retries:
                time.sleep(2 * attempt)

    return "failed"


# ── Main Scraper ────────────────────────────────────────────────────────────

class CafeFScraper:
    """Scraper chính sử dụng Playwright."""

    def __init__(self):
        self.intercepted_apis = []  # Lưu các API endpoints đã bắt được
        self.entries = []           # Danh sách CBTT entries
        self.downloaded = 0
        self.failed = 0
        self.skipped = 0            # Đếm số file đã bỏ qua (đã có trong history)
        self.history = DownloadHistory(PDF_DIR)

    def _on_response(self, response):
        """Callback bắt network responses để tìm API endpoint."""
        url = response.url
        # Bắt các XHR/fetch calls trả về dữ liệu CBTT
        if any(kw in url.lower() for kw in [
            "congbothongtin", "cbtt", "filterlist", "getlist",
            "baocaotaichinh", "hosocongty", "ajax"
        ]):
            try:
                content_type = response.headers.get("content-type", "")
                status = response.status
                log.info(f"  🔍 Intercepted API: [{status}] {url[:120]}")
                log.info(f"     Content-Type: {content_type}")
                self.intercepted_apis.append({
                    "url": url,
                    "status": status,
                    "content_type": content_type,
                })
            except Exception:
                pass

    def _wait_for_cbtt_module(self, page, timeout_ms: int = 15000) -> dict:
        """Đợi IformationDisclosure JS module sẵn sàng.
        
        Returns dict với keys: exists, totalPage, pageIndex, pageSize
        """
        try:
            result = page.evaluate(f"""() => {{
                return new Promise((resolve) => {{
                    let elapsed = 0;
                    const check = () => {{
                        if (typeof IformationDisclosure !== 'undefined' && IformationDisclosure.totalPage > 0) {{
                            resolve({{
                                exists: true,
                                totalPage: IformationDisclosure.totalPage,
                                pageIndex: IformationDisclosure.pageIndex,
                                pageSize: IformationDisclosure.pageSize,
                            }});
                        }} else if (elapsed >= {timeout_ms}) {{
                            resolve({{ exists: false }});
                        }} else {{
                            elapsed += 300;
                            setTimeout(check, 300);
                        }}
                    }};
                    check();
                }});
            }}""")
            return result
        except Exception as e:
            log.warning(f"  ⚠ Lỗi khi đợi IformationDisclosure: {e}")
            return {"exists": False}

    def _extract_entries_from_page(self, page) -> list[dict]:
        """Parse các CBTT entries từ trang hiện tại.
        
        Chỉ lấy dữ liệu từ bảng CBTT (IformationDisclosure),
        KHÔNG lấy từ các link tin tức trên trang.
        """
        entries = []

        # Selectors ưu tiên cho bảng CBTT trên CafeF
        selectors = [
            "table tbody tr",
        ]

        rows = []
        for sel in selectors:
            try:
                all_rows = page.query_selector_all(sel)
                # Lọc: chỉ lấy rows có >= 3 cells (bảng CBTT: MãCK, TênDN, TiêuĐề, ...)
                valid_rows = []
                for r in all_rows:
                    cells = r.query_selector_all("td")
                    if cells and len(cells) >= 3:
                        valid_rows.append(r)
                if valid_rows:
                    rows = valid_rows
                    log.info(f"  📋 Tìm thấy {len(rows)} CBTT rows (selector: {sel})")
                    break
            except Exception:
                continue

        if not rows:
            log.warning("  ⚠ Không tìm thấy bảng dữ liệu CBTT")
            return []

        for row in rows:
            try:
                cells = row.query_selector_all("td")
                if not cells or len(cells) < 3:
                    continue

                # Extract text content từ cells
                cell_texts = []
                for cell in cells:
                    cell_texts.append((cell.inner_text() or "").strip())

                # Validation: cell đầu tiên phải giống mã chứng khoán (2-5 ký tự, chữ in hoa)
                stock_code = cell_texts[0].strip().upper()
                if not stock_code or len(stock_code) > 10:
                    continue
                # Bỏ qua header rows
                if stock_code.lower() in ["mã ck", "mã", "symbol", "code", "stt"]:
                    continue

                entry = {}

                # Tìm PDF links trong row
                links = row.query_selector_all("a[href]")
                pdf_links = []
                detail_links = []

                for link in links:
                    href = link.get_attribute("href") or ""
                    text = (link.inner_text() or "").strip()

                    if href.lower().endswith(".pdf"):
                        pdf_links.append(href)
                    elif href and not href.startswith("javascript"):
                        detail_links.append({"href": href, "text": text})

                entry["cells"] = cell_texts
                entry["pdf_links"] = pdf_links
                entry["detail_links"] = detail_links

                # CafeF CBTT layout: [MãCK, TênDN, TiêuĐềBáoCáo, Extra/N/A]
                entry["stock_code"] = stock_code
                entry["company"] = cell_texts[1] if len(cell_texts) > 1 else ""
                report_title = cell_texts[2] if len(cell_texts) > 2 else ""
                entry["report_title"] = report_title
                entry["report_type"] = report_title
                entry["date"] = report_title
                entry["extra"] = cell_texts[3] if len(cell_texts) > 3 else ""

                entries.append(entry)

            except Exception as e:
                log.debug(f"  Skip row: {e}")
                continue

        return entries

    def _find_pdf_on_detail_page(self, page, url: str) -> list[str]:
        """Truy cập trang chi tiết và tìm link PDF."""
        pdf_urls = []
        try:
            full_url = urljoin(BASE_URL, url)
            log.info(f"  🔗 Đang mở trang chi tiết: {full_url[:100]}")
            page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Tìm PDF links
            all_links = page.query_selector_all("a[href]")
            for link in all_links:
                href = link.get_attribute("href") or ""
                text = (link.inner_text() or "").strip().lower()

                if href.lower().endswith(".pdf"):
                    pdf_urls.append(urljoin(full_url, href))
                elif "tải" in text or "download" in text or "xem" in text:
                    # Có thể là link download
                    resolved = urljoin(full_url, href)
                    if resolved not in pdf_urls:
                        pdf_urls.append(resolved)

            # Tìm thêm trong iframe (một số trang nhúng PDF qua iframe)
            iframes = page.query_selector_all("iframe[src]")
            for iframe in iframes:
                src = iframe.get_attribute("src") or ""
                if src.lower().endswith(".pdf") or "viewer" in src.lower():
                    pdf_urls.append(urljoin(full_url, src))

            # Tìm trong embed/object tags
            embeds = page.query_selector_all("embed[src], object[data]")
            for embed in embeds:
                src = embed.get_attribute("src") or embed.get_attribute("data") or ""
                if src:
                    pdf_urls.append(urljoin(full_url, src))

        except PlaywrightTimeout:
            log.warning(f"  ⏱ Timeout khi mở trang chi tiết: {url[:80]}")
        except Exception as e:
            log.error(f"  ✖ Lỗi khi mở trang chi tiết: {e}")

        return list(set(pdf_urls))

    def _process_entry(self, page, entry: dict, index: int):
        """Xử lý 1 entry: tìm PDF và download.
        
        Naming: [ICB_CODE]_[TICKER]_[YEARQ]_[TYPE].pdf
        Thư mục: pdf/[ICB_CODE]/
        Ví dụ:  pdf/8350/8350_ACB_2024Q4_BCTC.pdf
        """
        stock = entry.get("stock_code", "").strip().upper()
        raw_date = entry.get("date", "")
        raw_report_type = entry.get("report_type", "")

        # Tổng hợp text từ cells để cải thiện extract quarter/year
        all_text = " ".join(entry.get("cells", []))

        # Normalize
        report_abbr = normalize_report_type(raw_report_type or all_text)
        quarter_year = extract_quarter_year(raw_date, all_text)

        # Lookup metadata từ StockRegistry
        icb_code = stock_registry.get_icb_code(stock) if stock else ""
        exchange = stock_registry.get_exchange(stock) if stock else ""

        log.info(f"\n{'='*60}")
        log.info(f"  [{index+1}] {stock} | ICB:{icb_code} | {quarter_year} | {report_abbr}")
        log.info(f"  Cells: {entry.get('cells', [])[:4]}")

        # Filter theo STOCK_CODE nếu có (hỗ trợ nhiều mã: ACB,FPT,VNM)
        if STOCK_CODE and stock:
            allowed = {s.strip().upper() for s in STOCK_CODE.split(",") if s.strip()}
            if allowed and stock.upper() not in allowed:
                log.info(f"  ⏭ Bỏ qua (không trong danh sách: {len(allowed)} mã)")
                return

        # Filter theo khoảng thời gian
        if not _quarter_in_range(quarter_year):
            log.info(f"  ⏭ Bỏ qua (ngoài khoảng thời gian: {quarter_year})")
            return

        pdf_urls = list(entry.get("pdf_links", []))

        # Nếu chưa có PDF link → vào trang chi tiết tìm
        if not pdf_urls and entry.get("detail_links"):
            for detail in entry["detail_links"][:2]:
                found = self._find_pdf_on_detail_page(page, detail["href"])
                pdf_urls.extend(found)

        if not pdf_urls:
            log.warning(f"  ⚠ Không tìm thấy PDF cho entry này")
            self.failed += 1
            return

        # Download từng PDF
        for i, pdf_url in enumerate(pdf_urls):
            full_url = urljoin(BASE_URL, pdf_url)

            # Tên file: [ICB_CODE]_[TICKER]_[YEARQ]_[TYPE].pdf
            icb_part = icb_code if icb_code else "0000"
            ticker_part = stock if stock else "UNKNOWN"

            if quarter_year:
                time_part = quarter_year
            else:
                date_clean = sanitize_filename(raw_date) if raw_date else datetime.now().strftime("%Y%m%d")
                time_part = date_clean

            filename = f"{icb_part}_{ticker_part}_{time_part}_{report_abbr}"
            if i > 0:
                filename += f"_{i+1}"
            filename += ".pdf"

            # Thư mục: pdf/[ICB_CODE]/
            dest_dir = PDF_DIR / icb_part
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename

            status = download_pdf(
                full_url, dest, history=self.history,
                stock_code=stock, report_type=report_abbr,
                quarter_year=quarter_year, icb_code=icb_code,
                exchange=exchange
            )
            if status == "downloaded":
                self.downloaded += 1
                # Rate limiting: delay giữa các download
                time.sleep(DOWNLOAD_DELAY)
            elif status == "skipped":
                self.skipped += 1
            else:
                self.failed += 1

    def run(self):
        """Chạy scraper chính."""
        log.info("=" * 60)
        log.info("CafeF CBTT PDF Scraper")
        log.info("=" * 60)
        log.info(f"Config:")
        log.info(f"  STOCK_CODE    : {STOCK_CODE or '(tất cả)'}")
        log.info(f"  MAX_PAGES     : {MAX_PAGES or '(tất cả)'}")
        log.info(f"  PDF_DIR       : {PDF_DIR.absolute()}")
        log.info(f"  HEADLESS      : {HEADLESS}")
        log.info(f"  PAGE_DELAY    : {PAGE_DELAY}s")
        log.info(f"  DOWNLOAD_DELAY: {DOWNLOAD_DELAY}s")
        log.info("")

        PDF_DIR.mkdir(parents=True, exist_ok=True)

        # Preload ticker data
        stock_registry.load()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=HEADLESS)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            # Bật network interception
            page.on("response", self._on_response)

            # ── Phase 1: Load trang CBTT ────────────────────────────────
            log.info(f"🌐 Đang mở trang: {CBTT_URL}")
            try:
                page.goto(CBTT_URL, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeout:
                log.warning("Timeout trên desktop, thử mobile version...")
                page.goto(MOBILE_CBTT_URL, wait_until="domcontentloaded", timeout=30000)

            # ── Phase 2: Đợi IformationDisclosure JS module sẵn sàng ───
            log.info("⏳ Đợi module CBTT (IformationDisclosure) khởi tạo...")
            cbtt_info = self._wait_for_cbtt_module(page, timeout_ms=15000)
            
            if cbtt_info.get("exists"):
                total_pages = cbtt_info["totalPage"]
                page_size = cbtt_info["pageSize"]
                # MAX_PAGES=0 → fetch all
                if MAX_PAGES <= 0:
                    actual_max_pages = total_pages
                else:
                    actual_max_pages = min(MAX_PAGES, total_pages)
                log.info(f"  ✅ Module CBTT sẵn sàng:")
                log.info(f"     Tổng số trang : {total_pages}")
                log.info(f"     Entries/trang  : {page_size}")
                log.info(f"     Sẽ scrape      : {actual_max_pages} trang")
            else:
                log.warning("  ⚠ Module CBTT không tìm thấy, thử scrape trực tiếp...")
                actual_max_pages = MAX_PAGES if MAX_PAGES > 0 else 10
                page.wait_for_timeout(5000)

            # Nếu có 1 mã CK → dùng autocomplete search của CBTT (nhiều mã thì filter ở _process_entry)
            single_stock = STOCK_CODE.split(",")[0].strip() if STOCK_CODE else ""
            if single_stock and "," not in STOCK_CODE and cbtt_info.get("exists"):
                try:
                    page.evaluate(f"""
                        IformationDisclosure.refInputAC.value = "{single_stock}";
                        IformationDisclosure.handleFindDisclosure();
                    """)
                    log.info(f"  ✏ Đã filter theo mã CK: {single_stock}")
                    page.wait_for_timeout(3000)
                    cbtt_info = self._wait_for_cbtt_module(page, timeout_ms=5000)
                    if cbtt_info.get("exists"):
                        if MAX_PAGES <= 0:
                            actual_max_pages = cbtt_info["totalPage"]
                        else:
                            actual_max_pages = min(MAX_PAGES, cbtt_info["totalPage"])
                        log.info(f"  📊 Sau filter: {cbtt_info['totalPage']} trang")
                except Exception as e:
                    log.warning(f"  ⚠ Lỗi khi filter mã CK: {e}")

            # ── Phase 3: Chụp screenshot để debug ───────────────────────
            screenshot_path = PDF_DIR / "_debug_page.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            log.info(f"📸 Screenshot saved: {screenshot_path}")

            # ── Phase 4: Extract entries và navigate pages ──────────────
            for page_num in range(1, actual_max_pages + 1):
                log.info(f"\n{'─'*60}")
                log.info(f"📃 Đang xử lý trang {page_num}/{actual_max_pages}")

                entries = self._extract_entries_from_page(page)
                log.info(f"   Tìm thấy {len(entries)} CBTT entries trên trang {page_num}")

                if not entries:
                    log.warning(f"   Không tìm thấy entries trên trang {page_num}. Dừng.")
                    break

                self.entries.extend(entries)

                # Xử lý từng entry
                # Mở tab mới cho detail pages để không mất context trang chính
                detail_page = context.new_page()

                for idx, entry in enumerate(entries):
                    self._process_entry(detail_page, entry, idx + (page_num - 1) * 20)

                detail_page.close()

                # Pagination: chuyển trang bằng IformationDisclosure JS
                if page_num < actual_max_pages:
                    # Adaptive rate limiting: tăng delay mỗi 20 trang
                    delay = PAGE_DELAY + (page_num // 20) * 0.5
                    log.info(f"   ⏱ Đợi {delay:.1f}s trước trang tiếp...")
                    time.sleep(delay)

                    next_success = self._go_to_next_page(page, page_num)
                    if not next_success:
                        log.info("   Không còn trang tiếp theo. Dừng.")
                        break

            # ── Kết thúc ────────────────────────────────────────────────
            browser.close()

        # ── Tổng kết ────────────────────────────────────────────────────
        log.info(f"\n{'='*60}")
        log.info(f"✅ HOÀN THÀNH")
        log.info(f"   Tổng entries tìm thấy : {len(self.entries)}")
        log.info(f"   PDF mới tải           : {self.downloaded}")
        log.info(f"   Đã có (bỏ qua)        : {self.skipped}")
        log.info(f"   Thất bại             : {self.failed}")
        log.info(f"   Tổng trong DB history : {self.history.count}")
        log.info(f"   Thư mục PDF          : {PDF_DIR.absolute()}")
        log.info(f"{'='*60}")

        # Thống kê tổng hợp từ DB
        stats = self.history.summary()
        log.info(f"📊 DB Stats: {stats['total_files']} files, "
                 f"{stats['unique_stocks']} mã CK, "
                 f"{stats['total_size_mb']} MB")

        # Lưu report JSON
        report = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "stock_code": STOCK_CODE,
                "max_pages": MAX_PAGES,
                "pdf_dir": str(PDF_DIR.absolute()),
            },
            "total_entries": len(self.entries),
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "db_stats": stats,
        }
        report_path = PDF_DIR / "_scraper_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log.info(f"📊 Report saved: {report_path}")

        # Đóng DB connection
        self.history.close()

    def _go_to_next_page(self, page, current_page: int) -> bool:
        """Chuyển đến trang tiếp theo bằng IformationDisclosure JS API.
        
        Sử dụng: IformationDisclosure.handleChangePage(N)
        Thay vì click link <a> (dẫn đến trang tin tức thay vì CBTT)
        """
        target_page = current_page + 1
        try:
            log.info(f"   ➡ Chuyển trang CBTT: IformationDisclosure.handleChangePage({target_page})")
            page.evaluate(f"IformationDisclosure.handleChangePage({target_page})")
            
            # Đợi table re-render (IformationDisclosure gọi reRender → getData → renderTable)
            page.wait_for_timeout(2000)
            
            # Verify trang đã chuyển
            new_page_index = page.evaluate("IformationDisclosure.pageIndex")
            if new_page_index == target_page:
                log.info(f"   ✅ Đã chuyển sang trang {target_page}")
                return True
            else:
                log.warning(f"   ⚠ pageIndex = {new_page_index}, expected {target_page}")
                return False
        except Exception as e:
            log.warning(f"   ⚠ Lỗi chuyển trang CBTT: {e}")
            # Fallback: thử click pagination-item div
            try:
                pag_btn = page.query_selector(f"div.pagination-item:has-text('{target_page}')")
                if pag_btn and pag_btn.is_visible():
                    pag_btn.click()
                    page.wait_for_timeout(2000)
                    return True
            except Exception:
                pass
            return False


# ── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        scraper = CafeFScraper()
        scraper.run()
    except KeyboardInterrupt:
        log.info("\n⛔ Đã dừng bởi người dùng.")
    except Exception as e:
        log.error(f"\n💥 Lỗi nghiêm trọng: {e}", exc_info=True)
        sys.exit(1)
