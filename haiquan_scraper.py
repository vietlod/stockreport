"""
Hải Quan PDF Report Scraper
============================
Tải báo cáo thống kê hải quan (PDF) từ files.customs.gov.vn.

Module độc lập — KHÔNG share code/state với cafef_scraper.py.

Chức năng:
  - parse_filename(): Phân tích URL → metadata + tên file chuẩn hóa
  - load_legacy_urls(): Import URLs từ haiquan.xlsx (2009-2022)
  - download_pdf(): Tải PDF với retry, resume
  - HaiQuanDownloadHistory: SQLite tracking (DB riêng)

Quy tắc đặt tên file output:
  {LOẠI_BC}_{KỲ_BC}_{MÃ_BC}.pdf

  LOẠI_BC: SB (Sơ bộ), CT (Chính thức/Final), DC (Điều chỉnh)
  KỲ_BC:   {YYYY}T{M}       — tháng trọn
            {YYYY}T{M}K1     — kỳ 1 (1-15)
            {YYYY}T{M}K2     — kỳ 2 (16-cuối tháng)
            {YYYY}Q{N}       — quý
  MÃ_BC:   1X, 1N, 2X, 2N, 3X, 3N, 5X, 5N, PTVT, ...
"""

import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import requests
import urllib3

# Suppress SSL warnings — files.customs.gov.vn has expired certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger("haiquan")

# ── Environment ─────────────────────────────────────────────────────────────
HQ_PDF_DIR = Path(os.getenv("HQ_PDF_DIR", "./pdf/haiquan"))
HQ_DOWNLOAD_DELAY = float(os.getenv("HQ_DOWNLOAD_DELAY", "1.0"))

# ── Constants ───────────────────────────────────────────────────────────────

# Status mapping: URL status → output abbreviation
STATUS_MAP = {
    "SB": "SB",       # Sơ bộ (Preliminary)
    "CT": "CT",       # Chính thức (Official)
    "DC": "DC",       # Điều chỉnh (Adjusted)
    "final": "CT",    # final = Chính thức
    "PR": "CT",       # Preliminary (EN) → CT
}

# Roman numeral → integer quarter
ROMAN_QUARTER = {"I": 1, "II": 2, "III": 3, "IV": 4}

# Standard filename pattern:
#   Optional numeric prefix + YYYY-T{M/MM}{Period?}-{Code}({Lang}-{Status}).pdf
#   Examples:
#     2022-T08T-5N(VN-SB).pdf
#     6542021-T08K2-1N(VN-CT).pdf
#     5892022-T08K2-1N(EN-PR).pdf  ← non-VN language
#     2010-T03K02-13B(VN-CT).pdf   ← K02 = K2
#     2015-T5T-4(VN-CT)-2017.pdf   ← single-digit month, trailing suffix
#     2015-T09T-2X (VN-SB).pdf     ← space before (
#     2020-T11-4(VN-SB).pdf        ← missing period suffix
#     2020-T08T-5N(VN-CT)-final.pdf ← trailing -final
RE_STANDARD = re.compile(
    r'(?:\d+)?'              # optional numeric prefix (e.g. 654, 245, 589)
    r'(\d{4})'               # year (YYYY)
    r'-T(\d{1,2})'           # month (M or MM — single or double digit)
    r'(T|K0?[12])?'          # period suffix: T=full month, K1/K01, K2/K02 (OPTIONAL)
    r'-'
    r'(\w+)'                 # report code (1X, 5N, 2X, etc.)
    r'\s*'                   # optional whitespace before (
    r'\('
    r'(?:\w+)-'              # language (VN, EN, etc.)
    r'(\w+)'                 # status (SB, CT, DC, PR, final, etc.)
    r'\)',
    re.IGNORECASE
)

# Quarter filename pattern (PTVT-style):
#   {Code}-{N|X}KQ{N}-{status_or_year}.pdf
#   Examples:
#     PTVT-NKQ2-final.pdf   → CT_2022Q2_PTVT
#     PTVT-XKQ3-SB.pdf      → SB_2022Q3_PTVT-XK
#     PTVT-NKQ1-2022.pdf    → CT_2022Q1_PTVT
#     PTVT-XKQ2-2022.pdf    → CT_2022Q2_PTVT-XK
RE_QUARTER = re.compile(
    r'^(?:\d+)?'             # optional numeric prefix
    r'(\w+)'                 # report code (PTVT)
    r'-(N|X)KQ'             # NK/XK direction + Q
    r'(\d+)'                # quarter number
    r'-(\w+)',              # status OR year (final, SB, CT, DC, 2022, etc.)
    re.IGNORECASE
)

# Quarter with Roman numerals:
#   {prefix} {Code}_{Q_roman}_{year}.pdf
#   {Code}-Q{roman} nam {year}.pdf
#   Examples:
#     Bieu HTX_QIV_2021.pdf     → CT_2021Q4_HTX
#     HTX-QI nam 2022.pdf       → CT_2022Q1_HTX
#     HTX-QII nam 2022.pdf      → CT_2022Q2_HTX
RE_QUARTER_ROMAN = re.compile(
    r'(?:Bieu\s+)?'              # optional "Bieu " prefix
    r'(\w+)'                     # report code (HTX, etc.)
    r'[-_]'                      # separator (- or _)
    r'Q(IV|III|II|I)'            # Roman numeral quarter (try longest first)
    r'(?:\s+nam\s+|[-_])'       # " nam " or separator
    r'(\d{4})',                   # year (YYYY)
    re.IGNORECASE
)

# Quarter with Arabic numerals (flexible separators):
#   {prefix?}{Code}[-_]{year}[-_ ]+Q{N}
#   {prefix?}{Code}-Q{N}[-_]{year}
#   Examples:
#     Bieu HTX_2020- Q4          → CT_2020Q4_HTX
#     579HTX-Q2-2020.pdf         → CT_2020Q2_HTX
#     HTX_2021-Q1.pdf            → CT_2021Q1_HTX
RE_QUARTER_ARABIC = re.compile(
    r'(?:Bieu\s+)?'              # optional "Bieu " prefix
    r'(?:\d+)?'                  # optional numeric prefix (579, etc.)
    r'([A-Za-z]\w*)'            # report code (HTX, etc.) — must start with letter
    r'[-_]'
    r'(?:'
        r'(\d{4})[-_\s]+Q(\d+)' # year-Q{N} pattern (HTX_2020- Q4)
        r'|'
        r'Q(\d+)[-_](\d{4})'    # Q{N}-year pattern (HTX-Q2-2020)
    r')',
    re.IGNORECASE
)

# Extract year from URL path: /TONG_CUC/{YYYY}/{M}/{D}/
RE_URL_YEAR = re.compile(r'/TONG_CUC/(\d{4})/')


# ── File Naming ─────────────────────────────────────────────────────────────

def parse_filename(url: str) -> dict | None:
    """Phân tích URL PDF hải quan → metadata + tên file chuẩn hóa.

    Returns dict with keys:
        filename:          Tên file output chuẩn hóa (e.g. SB_2022T8_5N.pdf)
        original_filename: Tên file gốc từ URL
        year:              Năm báo cáo (int)
        month:             Tháng (int hoặc None nếu quý)
        quarter:           Quý (int hoặc None nếu tháng)
        period:            T | K1 | K2 | Q
        report_code:       Mã báo cáo (1X, PTVT, etc.)
        report_type:       SB | CT | DC

    Returns None nếu không parse được.
    """
    # Decode URL-encoded chars
    decoded_url = unquote(url)
    # Extract filename from URL
    original_filename = decoded_url.rstrip('/').split('/')[-1]

    # ── Pattern 1: Standard monthly ──────────────────────────────────────
    m = RE_STANDARD.search(original_filename)
    if m:
        year = int(m.group(1))
        month_raw = int(m.group(2))
        period_suffix_raw = (m.group(3) or 'T').upper()  # T, K1, K2, K01, K02, or None→T
        report_code = m.group(4)
        status = m.group(5).upper()

        # Normalize K01→K1, K02→K2
        period_suffix = period_suffix_raw.replace('K01', 'K1').replace('K02', 'K2')

        # Default to CT if status unknown
        report_type = STATUS_MAP.get(status, "CT")

        # Build kỳ báo cáo
        if period_suffix == 'T':
            period_str = f"{year}T{month_raw}"
            period = "T"
        elif period_suffix in ('K1', 'K2'):
            period_str = f"{year}T{month_raw}{period_suffix}"
            period = period_suffix
        else:
            period_str = f"{year}T{month_raw}"
            period = "T"

        output_filename = f"{report_type}_{period_str}_{report_code}.pdf"

        return {
            "filename": output_filename,
            "original_filename": original_filename,
            "year": year,
            "month": month_raw,
            "quarter": None,
            "period": period,
            "report_code": report_code,
            "report_type": report_type,
        }

    # ── Pattern 2: Quarter PTVT-style (NK/XK) ───────────────────────────
    m = RE_QUARTER.search(original_filename)
    if m:
        report_code = m.group(1)
        direction = m.group(2).upper()   # N or X
        quarter = int(m.group(3))
        suffix_val = m.group(4)

        # Distinguish year vs status suffix
        if suffix_val.isdigit() and len(suffix_val) == 4:
            year = int(suffix_val)
            report_type = "CT"  # default when only year
        else:
            report_type = STATUS_MAP.get(suffix_val, "CT")
            # Year: extract from URL path, +1
            url_year_match = RE_URL_YEAR.search(decoded_url)
            if url_year_match:
                year = int(url_year_match.group(1)) + 1
            else:
                log.warning(f"  ⚠ Cannot determine year for quarter report: {original_filename}")
                return None

        # XK → append -XK to report code
        code_suffix = "-XK" if direction == "X" else ""
        period_str = f"{year}Q{quarter}"
        output_filename = f"{report_type}_{period_str}_{report_code}{code_suffix}.pdf"

        return {
            "filename": output_filename,
            "original_filename": original_filename,
            "year": year,
            "month": None,
            "quarter": quarter,
            "period": "Q",
            "report_code": f"{report_code}{code_suffix}",
            "report_type": report_type,
        }

    # ── Pattern 3: Quarter with Roman numerals ───────────────────────────
    m = RE_QUARTER_ROMAN.search(original_filename)
    if m:
        report_code = m.group(1)
        roman = m.group(2).upper()
        year = int(m.group(3))
        quarter = ROMAN_QUARTER.get(roman, 0)
        report_type = "CT"  # default

        period_str = f"{year}Q{quarter}"
        output_filename = f"{report_type}_{period_str}_{report_code}.pdf"

        return {
            "filename": output_filename,
            "original_filename": original_filename,
            "year": year,
            "month": None,
            "quarter": quarter,
            "period": "Q",
            "report_code": report_code,
            "report_type": report_type,
        }

    # ── Pattern 4: Quarter with Arabic numerals ──────────────────────────
    m = RE_QUARTER_ARABIC.search(original_filename)
    if m:
        report_code = m.group(1)
        # Two alternatives: year-Q{N} or Q{N}-year
        if m.group(2) is not None:  # year-Q{N} pattern
            year = int(m.group(2))
            quarter = int(m.group(3))
        else:  # Q{N}-year pattern
            quarter = int(m.group(4))
            year = int(m.group(5))
        report_type = "CT"  # default

        period_str = f"{year}Q{quarter}"
        output_filename = f"{report_type}_{period_str}_{report_code}.pdf"

        return {
            "filename": output_filename,
            "original_filename": original_filename,
            "year": year,
            "month": None,
            "quarter": quarter,
            "period": "Q",
            "report_code": report_code,
            "report_type": report_type,
        }

    # Cannot parse
    log.warning(f"  ⚠ Cannot parse filename: {original_filename} (URL: {url})")
    return None


# ── Download History (SQLite) ───────────────────────────────────────────────

class HaiQuanDownloadHistory:
    """Quản lý lịch sử download hải quan bằng SQLite.

    Database: _haiquan_history.db trong thư mục HQ_PDF_DIR.
    Hoàn toàn tách biệt với DownloadHistory của CafeF.
    """

    def __init__(self, pdf_dir: Path = None):
        self.pdf_dir = pdf_dir or HQ_PDF_DIR
        self.db_path = self.pdf_dir / "_haiquan_history.db"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Tạo bảng nếu chưa tồn tại."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS haiquan_downloads (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                filename         TEXT UNIQUE NOT NULL,
                url              TEXT,
                original_filename TEXT,
                year             INTEGER,
                month            INTEGER,
                quarter          INTEGER,
                period           TEXT,
                report_code      TEXT,
                report_type      TEXT,
                file_size        INTEGER,
                downloaded_at    TEXT,
                source           TEXT,
                drive_synced     INTEGER DEFAULT 0,
                drive_file_id    TEXT
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hq_year ON haiquan_downloads(year)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hq_type ON haiquan_downloads(report_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hq_code ON haiquan_downloads(report_code)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hq_period ON haiquan_downloads(period)"
        )
        self.conn.commit()
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM haiquan_downloads"
        ).fetchone()[0]
        if cnt:
            log.info(f"📊 Hải Quan history DB: {cnt} records")

    def is_downloaded(self, filename: str) -> bool:
        """Kiểm tra file đã download chưa.

        True nếu: có trong DB VÀ file vật lý tồn tại trên disk.
        """
        row = self.conn.execute(
            "SELECT id FROM haiquan_downloads WHERE filename = ?", (filename,)
        ).fetchone()
        if not row:
            return False

        pdf_path = self.pdf_dir / filename
        if pdf_path.exists():
            return True

        # File trong DB nhưng bị xóa trên disk → cho tải lại
        self.conn.execute(
            "DELETE FROM haiquan_downloads WHERE filename = ?", (filename,)
        )
        self.conn.commit()
        log.info(f"  ♻ {filename}: trong DB nhưng không còn trên disk, sẽ tải lại")
        return False

    def add(self, filename: str, url: str, file_size: int,
            original_filename: str = "", year: int = 0, month: int = None,
            quarter: int = None, period: str = "", report_code: str = "",
            report_type: str = "", source: str = ""):
        """Ghi nhận file đã download thành công."""
        self.conn.execute("""
            INSERT OR REPLACE INTO haiquan_downloads
                (filename, url, original_filename, year, month, quarter,
                 period, report_code, report_type, file_size,
                 downloaded_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (filename, url, original_filename, year, month, quarter,
              period, report_code, report_type, file_size,
              datetime.now().isoformat(), source))
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM haiquan_downloads"
        ).fetchone()[0]

    def summary(self) -> dict:
        """Thống kê tổng hợp."""
        row = self.conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT year) as unique_years,
                   COUNT(DISTINCT report_code) as unique_codes,
                   SUM(file_size) as total_size
            FROM haiquan_downloads
        """).fetchone()
        if row and row["total"]:
            return {
                "total_files": row["total"],
                "unique_years": row["unique_years"],
                "unique_codes": row["unique_codes"],
                "total_size_mb": round((row["total_size"] or 0) / 1024 / 1024, 1),
            }
        return {"total_files": 0, "unique_years": 0, "unique_codes": 0, "total_size_mb": 0}

    def close(self):
        self.conn.close()


# ── PDF Download ────────────────────────────────────────────────────────────

def download_pdf(url: str, dest: Path, history: HaiQuanDownloadHistory = None,
                 max_retries: int = 3, metadata: dict = None,
                 source: str = "") -> tuple[str, str | None]:
    """Download PDF file với retry logic + kiểm tra history.

    Args:
        url:         URL to download
        dest:        Local destination path (with standardized filename)
        history:     HaiQuanDownloadHistory instance
        max_retries: Number of retry attempts
        metadata:    Parsed metadata dict from parse_filename()
        source:      'xlsx_legacy' or 'web_crawl'

    Returns: tuple(result, error_msg)
        result:    'skipped' | 'downloaded' | 'failed'
        error_msg: None on success/skip, error string on failure
    """
    filename = dest.name
    meta = metadata or {}

    # Kiểm tra download history trước
    if history and history.is_downloaded(filename):
        log.info(f"  ⏭ Đã tải trước đó: {filename}")
        return "skipped", None

    # Kiểm tra file vật lý (chưa có trong DB)
    if dest.exists():
        file_size = dest.stat().st_size
        if file_size > 1024:  # > 1KB = valid
            log.info(f"  ✔ Đã tồn tại trên disk: {filename} ({file_size:,} bytes)")
            if history:
                history.add(
                    filename=filename, url=url, file_size=file_size,
                    original_filename=meta.get("original_filename", ""),
                    year=meta.get("year", 0),
                    month=meta.get("month"),
                    quarter=meta.get("quarter"),
                    period=meta.get("period", ""),
                    report_code=meta.get("report_code", ""),
                    report_type=meta.get("report_type", ""),
                    source=source,
                )
            return "skipped", None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.customs.gov.vn/",
    }

    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"  ⬇ Đang tải ({attempt}/{max_retries}): {url}")
            resp = requests.get(url, headers=headers, timeout=60, stream=True, verify=False)
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
                log.warning(f"  ⚠ File quá nhỏ ({file_size} bytes), có thể không phải PDF")

            log.info(f"  ✔ Đã lưu: {filename} ({file_size:,} bytes)")
            if history:
                history.add(
                    filename=filename, url=url, file_size=file_size,
                    original_filename=meta.get("original_filename", ""),
                    year=meta.get("year", 0),
                    month=meta.get("month"),
                    quarter=meta.get("quarter"),
                    period=meta.get("period", ""),
                    report_code=meta.get("report_code", ""),
                    report_type=meta.get("report_type", ""),
                    source=source,
                )
            return "downloaded", None

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            last_error = f"HTTP {status_code}"
            log.error(f"  ✖ Lỗi attempt {attempt}: {last_error} — {url}")
            if dest.exists():
                dest.unlink()
            # Không retry nếu 404/403/410 (URL không tồn tại)
            if status_code in (404, 403, 410):
                break
            if attempt < max_retries:
                time.sleep(2 * attempt)

        except requests.exceptions.Timeout:
            last_error = "Timeout (60s)"
            log.error(f"  ✖ Lỗi attempt {attempt}: {last_error} — {url}")
            if dest.exists():
                dest.unlink()
            if attempt < max_retries:
                time.sleep(2 * attempt)

        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {type(e).__name__}"
            log.error(f"  ✖ Lỗi attempt {attempt}: {last_error} — {url}")
            if dest.exists():
                dest.unlink()
            if attempt < max_retries:
                time.sleep(2 * attempt)

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            log.error(f"  ✖ Lỗi attempt {attempt}: {last_error}")
            if dest.exists():
                dest.unlink()
            if attempt < max_retries:
                time.sleep(2 * attempt)

    return "failed", last_error


# ── Legacy URL Import ───────────────────────────────────────────────────────

def load_legacy_urls(xlsx_path: str = None) -> list[dict]:
    """Import URLs từ haiquan.xlsx.

    Đọc file xlsx, extract URLs từ cột LinkSB và LinkCT,
    parse filename → metadata, deduplicate.

    Returns: list of dict with keys matching parse_filename() output + 'url', 'source'
    """
    import openpyxl

    xlsx_path = xlsx_path or str(Path(__file__).parent / "docs" / "haiquan" / "haiquan.xlsx")
    log.info(f"📖 Loading legacy URLs from {xlsx_path}")

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb.active

    # Find column indices by header name
    headers = {str(c.value).strip(): i for i, c in enumerate(ws[1]) if c.value}
    log.info(f"  Headers: {list(headers.keys())}")

    # Determine which columns to scan for URLs
    url_col_indices = []
    for col_name in ["LinkSB", "LinkCT"]:
        idx = headers.get(col_name)
        if idx is not None:
            url_col_indices.append(idx)

    # Fallback: nếu không tìm thấy LinkSB/LinkCT → quét tất cả columns tìm URL
    auto_detect = len(url_col_indices) == 0
    if auto_detect:
        log.info("  ⚠ Không tìm thấy cột LinkSB/LinkCT → auto-detect URL columns")

    results = []
    seen_urls = set()
    unparsed_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        # Quét theo columns đã xác định, hoặc tất cả cells nếu auto_detect
        cells_to_check = range(len(row)) if auto_detect else url_col_indices
        for idx in cells_to_check:
            if idx >= len(row):
                continue
            val = row[idx]
            if not isinstance(val, str) or not val.startswith("http"):
                continue

            url = val.strip()
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Parse filename
            meta = parse_filename(url)
            if meta:
                meta["url"] = url
                meta["source"] = "xlsx_legacy"
                results.append(meta)
            else:
                unparsed_count += 1
                # Đề xuất: download với tên gốc (không skip)
                original_fn = unquote(url.rstrip("/").split("/")[-1])
                results.append({
                    "url": url,
                    "filename": original_fn,
                    "original_filename": original_fn,
                    "year": 0,
                    "month": None,
                    "quarter": None,
                    "period": "",
                    "report_code": "",
                    "report_type": "",
                    "source": "xlsx_legacy",
                })

    wb.close()
    log.info(
        f"  ✔ Loaded {len(results)} unique URLs"
        f" ({unparsed_count} could not be parsed → will use original filename)"
    )
    return results


# ── Web Crawl (Playwright) ─────────────────────────────────────────────────

_CUSTOMS_STATS_URL = (
    "https://www.customs.gov.vn/index.jsp?pageId=4901"
    "&group=undefined"
    "&category=S%E1%BB%91%20li%E1%BB%87u%20%C4%91%E1%BB%8Bnh%20k%E1%BB%B3"
)


def crawl_web_urls(year_from: int = 2022, year_to: int = None,
                   max_pages: int = 110, timeout: int = 30) -> list[dict]:
    """Crawl customs.gov.vn bằng Playwright để tìm PDF URLs.

    Chiến lược:
      1. Mở trang thống kê định kỳ (pageId=4901) bằng Playwright
      2. Parse table → extract PDF links từ 3 cột (Sơ bộ, Điều chỉnh, Chính thức)
      3. Click #aNextPage để chuyển trang
      4. Parse filename → metadata, filter theo year range

    Args:
        year_from: Năm bắt đầu (default 2022)
        year_to:   Năm kết thúc (default năm hiện tại)
        max_pages: Số trang tối đa crawl (mỗi trang 20 records)
        timeout:   Timeout tải trang (seconds)

    Returns: list[dict] giống format load_legacy_urls() + source='web_crawl'
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    if year_to is None:
        year_to = datetime.now().year

    log.info(f"🌐 Web crawl (Playwright): tìm PDF từ customs.gov.vn ({year_from}–{year_to})")

    all_pdf_urls = set()
    results = []

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page()

        # Tải trang đầu tiên
        log.info(f"  🌍 Loading {_CUSTOMS_STATS_URL[:80]}...")
        page.goto(_CUSTOMS_STATS_URL, timeout=timeout * 1000)
        page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        log.info("  ✅ Page loaded")

        for page_num in range(1, max_pages + 1):
            # Extract PDF links từ table trên trang hiện tại
            pdf_links = page.evaluate("""() => {
                const links = [];
                const rows = document.querySelectorAll('table tbody tr');
                rows.forEach(row => {
                    const anchors = row.querySelectorAll('a[href]');
                    anchors.forEach(a => {
                        const href = a.getAttribute('href');
                        if (href && href.includes('.pdf') && href !== 'null') {
                            links.push(href.startsWith('http') ? href : 'https://files.customs.gov.vn' + href);
                        }
                    });
                });
                return links;
            }""")

            page_urls = set()
            for url in pdf_links:
                url = url.strip()
                if url and url not in all_pdf_urls:
                    page_urls.add(url)

            all_pdf_urls.update(page_urls)
            log.info(f"  📄 Page {page_num}: {len(page_urls)} PDF URLs "
                     f"(total: {len(all_pdf_urls)})")

            if not page_urls and page_num > 1:
                log.info(f"  📄 Page {page_num}: no new URLs, stopping")
                break

            # Chuyển trang bằng nút #aNextPage
            try:
                next_btn = page.query_selector("#aNextPage")
                if not next_btn:
                    log.info("  📄 No next page button found, stopping")
                    break

                # Kiểm tra đã ở trang cuối chưa
                is_disabled = page.evaluate("""() => {
                    const btn = document.querySelector('#aNextPage');
                    if (!btn) return true;
                    const style = window.getComputedStyle(btn);
                    return style.pointerEvents === 'none' ||
                           style.display === 'none' ||
                           btn.classList.contains('disabled');
                }""")
                if is_disabled:
                    log.info("  📄 Next page button disabled, reached last page")
                    break

                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=timeout * 1000)
                time.sleep(1)  # Đợi DOM update

            except PwTimeout:
                log.warning(f"  ⏱ Timeout navigating to page {page_num + 1}")
                break
            except Exception as e:
                log.warning(f"  ⚠ Error navigating: {e}")
                break

        browser.close()
        pw.stop()

    except PwTimeout:
        log.warning(f"  ⏱ Timeout loading customs.gov.vn ({timeout}s)")
        log.warning("  ⚠ Không thể kết nối. Sẽ dùng nguồn xlsx dự phòng.")
    except Exception as e:
        log.error(f"  ✖ Playwright error: {type(e).__name__}: {e}")

    log.info(f"  🔗 Tổng PDF URLs phát hiện: {len(all_pdf_urls)}")

    # Parse each URL → metadata
    unparsed = 0
    for url in sorted(all_pdf_urls):
        meta = parse_filename(url)
        if meta:
            year = meta.get("year", 0)
            if year and not (year_from <= year <= year_to):
                continue
            meta["url"] = url
            meta["source"] = "web_crawl"
            results.append(meta)
        else:
            unparsed += 1
            original_fn = unquote(url.rstrip("/").split("/")[-1])
            results.append({
                "url": url,
                "filename": original_fn,
                "original_filename": original_fn,
                "year": 0,
                "month": None,
                "quarter": None,
                "period": "",
                "report_code": "",
                "report_type": "",
                "source": "web_crawl",
            })

    log.info(
        f"  ✔ Web crawl: {len(results)} URLs processed"
        f" ({unparsed} could not be parsed → will use original filename)"
    )
    return results


# ── Main Scraper Class ──────────────────────────────────────────────────────

class HaiQuanScraper:
    """Scraper chính cho báo cáo hải quan.

    Hỗ trợ 2 nguồn:
      1. Legacy: import từ haiquan.xlsx (2009-2022)
      2. Web crawl: scrape từ customs.gov.vn (2022+)
    """

    def __init__(self, pdf_dir: Path = None):
        self.pdf_dir = pdf_dir or HQ_PDF_DIR
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.history = HaiQuanDownloadHistory(self.pdf_dir)
        self.downloaded = 0
        self.failed = 0
        self.skipped = 0
        self.should_stop = False
        self.error_details = []   # [{filename, url, error}, ...]
        self.last_error = ""      # Lỗi gần nhất (hiển thị trên UI)

    def run(self, config: dict = None,
            on_progress=None, on_download=None):
        """Chạy scraper theo config.

        Args:
            config: {
                source: 'xlsx' | 'web' | 'all',
                year_from: int, year_to: int,
                report_types: list[str],  # ['SB', 'CT', 'DC']
                report_codes: list[str],  # ['1X', '1N', ...]
            }
            on_progress: callback(current, total, filename, phase)
            on_download: callback(dest_path) — called after each successful download
        """
        config = config or {}
        source = config.get("source", "xlsx")
        year_from = config.get("year_from", 2009)
        year_to = config.get("year_to", 2025)
        report_types = config.get("report_types", [])
        report_codes = config.get("report_codes", [])

        self.downloaded = 0
        self.failed = 0
        self.skipped = 0
        self.should_stop = False

        # Phase: loading_xlsx — emit TRƯỚC khi load file
        if on_progress:
            on_progress(0, 0, "", "loading_xlsx")

        # Collect URLs
        all_urls = []
        seen_urls = set()
        self.data_source = ""  # Chỉ báo nguồn thực tế: web_crawl | xlsx | xlsx_fallback

        # File xlsx tổng hợp (haiquan0925.xlsx = merge haiquan.xlsx + haiquan2226.xlsx)
        _xlsx_0925 = str(Path(__file__).parent / "docs" / "haiquan" / "haiquan0925.xlsx")

        if source in ("xlsx", "all"):
            xlsx_path = _xlsx_0925 if Path(_xlsx_0925).exists() else None
            legacy = load_legacy_urls(xlsx_path=xlsx_path)
            all_urls.extend(legacy)
            seen_urls.update(u["url"] for u in legacy)
            self.data_source = "xlsx"

        if source in ("web", "all"):
            if on_progress:
                on_progress(0, 0, "", "crawling_web")
            web_urls = crawl_web_urls(year_from, year_to)
            for u in web_urls:
                if u["url"] not in seen_urls:
                    all_urls.append(u)
                    seen_urls.add(u["url"])

            if web_urls:
                self.data_source = "web_crawl" if source == "web" else "xlsx+web_crawl"

            # Fallback: web crawl fail → dùng haiquan0925.xlsx
            if not web_urls and source == "web":
                log.info("  📖 Web crawl trả về 0 URLs → fallback sang haiquan0925.xlsx")
                self.data_source = "xlsx_fallback"
                if Path(_xlsx_0925).exists():
                    fallback = load_legacy_urls(xlsx_path=_xlsx_0925)
                    for u in fallback:
                        if u["url"] not in seen_urls:
                            u["source"] = "xlsx_fallback"
                            all_urls.append(u)
                            seen_urls.add(u["url"])

        # Phase: filtering
        if on_progress:
            on_progress(0, len(all_urls), "", "filtering")

        # Filter
        if year_from or year_to:
            all_urls = [
                u for u in all_urls
                if (u.get("year", 0) == 0) or  # unparsed: include
                   (year_from <= u.get("year", 0) <= year_to)
            ]
        if report_types:
            types_upper = [t.upper() for t in report_types]
            all_urls = [
                u for u in all_urls
                if not u.get("report_type") or u["report_type"] in types_upper
            ]
        if report_codes:
            codes_upper = [c.upper() for c in report_codes]
            all_urls = [
                u for u in all_urls
                if not u.get("report_code") or u["report_code"] in codes_upper
            ]

        total = len(all_urls)
        log.info(f"📋 Total URLs to process: {total}")

        if on_progress:
            on_progress(0, total, "", "starting")

        for i, entry in enumerate(all_urls):
            if self.should_stop:
                log.info("⛔ Scraper stopped by user")
                break

            url = entry["url"]
            filename = entry["filename"]
            dest = self.pdf_dir / filename

            if on_progress:
                on_progress(i + 1, total, filename, "downloading")

            result, error_msg = download_pdf(
                url=url,
                dest=dest,
                history=self.history,
                metadata=entry,
                source=entry.get("source", ""),
            )

            if result == "downloaded":
                self.downloaded += 1
                self.last_error = ""
                if on_download:
                    on_download(str(dest))
            elif result == "skipped":
                self.skipped += 1
            else:
                self.failed += 1
                self.last_error = error_msg or "Unknown error"
                self.error_details.append({
                    "filename": filename,
                    "url": url,
                    "error": error_msg or "Unknown error",
                })
                # Giới hạn error_details để không chiếm quá nhiều bộ nhớ
                if len(self.error_details) > 50:
                    self.error_details = self.error_details[-50:]

            # Rate limiting
            if result == "downloaded":
                time.sleep(HQ_DOWNLOAD_DELAY)

        summary = {
            "total": total,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
        }
        log.info(
            f"✅ Hoàn tất: {self.downloaded} downloaded, "
            f"{self.skipped} skipped, {self.failed} failed / {total} total"
        )

        if on_progress:
            on_progress(total, total, "", "done")

        return summary

    def stop(self):
        self.should_stop = True

    def close(self):
        self.history.close()
