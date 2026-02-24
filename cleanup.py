"""
Auto-Delete Cleanup Module
===========================
Tự động xóa files/folders PDF đã tải sau khoảng thời gian cấu hình (retention).

Retention options:
  - 1w:    7 ngày
  - 1m:    30 ngày
  - 1q:    90 ngày (mặc định)
  - 1y:    365 ngày
  - never: Không xóa

Settings lưu trong _settings.json cùng thư mục PDF.
Scheduler chạy mỗi 24h kiểm tra + xóa files hết hạn.

Usage:
    from cleanup import load_settings, save_settings, cleanup_expired_files
    from cleanup import start_cleanup_scheduler
"""

import os
import json
import sqlite3
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("cleanup")

PDF_DIR = Path(os.getenv("PDF_DIR", "./pdf"))
SETTINGS_FILE = PDF_DIR / "_settings.json"

# ── Retention Options ───────────────────────────────────────────────────────

RETENTION_OPTIONS = {
    "1w":    {"days": 7,   "label": "1 tuần"},
    "1m":    {"days": 30,  "label": "1 tháng"},
    "1q":    {"days": 90,  "label": "1 quý"},
    "1y":    {"days": 365, "label": "1 năm"},
    "never": {"days": None, "label": "Không xóa"},
}

DEFAULT_SETTINGS = {
    "retention": "1q",   # mặc định: 1 quý
}


# ── Settings Persistence ────────────────────────────────────────────────────

def load_settings() -> dict:
    """Load settings từ _settings.json. Trả về defaults nếu chưa có."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validate retention key
            if data.get("retention") not in RETENTION_OPTIONS:
                data["retention"] = DEFAULT_SETTINGS["retention"]
            return {**DEFAULT_SETTINGS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> dict:
    """Lưu settings vào _settings.json. Trả về settings đã lưu."""
    # Validate
    if settings.get("retention") not in RETENTION_OPTIONS:
        settings["retention"] = DEFAULT_SETTINGS["retention"]

    current = load_settings()
    current.update(settings)

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)

    log.info(f"💾 Settings saved: retention={current['retention']}")
    return current


# ── Cleanup Logic ───────────────────────────────────────────────────────────

def cleanup_expired_files(pdf_dir: Path = None) -> dict:
    """Xóa files đã hết hạn retention.

    Logic:
    1. Load settings → lấy retention days
    2. Query DB: files có downloaded_at < cutoff_date
    3. Xóa file vật lý + record DB
    4. Xóa thư mục ICB rỗng

    Returns: {"deleted": int, "freed_mb": float, "errors": int, "retention": str}
    """
    if pdf_dir is None:
        pdf_dir = PDF_DIR

    settings = load_settings()
    retention_key = settings["retention"]
    retention_info = RETENTION_OPTIONS.get(retention_key, RETENTION_OPTIONS["1q"])

    if retention_info["days"] is None:
        log.info("⏭ Cleanup skipped: retention = never")
        return {"deleted": 0, "freed_mb": 0, "errors": 0, "retention": "never", "skipped": True}

    retention_days = retention_info["days"]
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    cutoff_iso = cutoff_date.isoformat()

    db_path = pdf_dir / "_download_history.db"
    if not db_path.exists():
        return {"deleted": 0, "freed_mb": 0, "errors": 0, "retention": retention_key, "skipped": False}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Query files hết hạn
    expired_rows = conn.execute(
        "SELECT id, filename, file_size, icb_code FROM downloads "
        "WHERE downloaded_at < ? AND downloaded_at != ''",
        (cutoff_iso,)
    ).fetchall()

    if not expired_rows:
        conn.close()
        log.info(f"⏭ Cleanup: no expired files (retention={retention_key}, cutoff={cutoff_date.strftime('%Y-%m-%d')})")
        return {"deleted": 0, "freed_mb": 0, "errors": 0, "retention": retention_key, "skipped": False}

    stats = {"deleted": 0, "freed_bytes": 0, "errors": 0}
    ids_to_delete = []

    for row in expired_rows:
        filename = row["filename"]
        file_size = row["file_size"] or 0

        # Tìm file trên disk (root hoặc ICB subfolder)
        file_path = pdf_dir / filename
        if not file_path.exists():
            # Tìm trong sub-directories
            for sub in pdf_dir.iterdir():
                if sub.is_dir() and (sub / filename).exists():
                    file_path = sub / filename
                    break

        try:
            if file_path.exists():
                file_path.unlink()
                stats["freed_bytes"] += file_size
                log.info(f"  🗑 Deleted: {filename} ({file_size} bytes)")
            # Luôn xóa record DB (kể cả file không còn trên disk)
            ids_to_delete.append(row["id"])
            stats["deleted"] += 1
        except Exception as e:
            stats["errors"] += 1
            log.error(f"  ✖ Error deleting {filename}: {e}")

    # Batch delete records
    if ids_to_delete:
        placeholders = ",".join(["?"] * len(ids_to_delete))
        conn.execute(f"DELETE FROM downloads WHERE id IN ({placeholders})", ids_to_delete)
        conn.commit()

    conn.close()

    # Xóa thư mục ICB rỗng
    _remove_empty_subdirs(pdf_dir)

    freed_mb = round(stats["freed_bytes"] / 1024 / 1024, 2)
    log.info(
        f"✅ Cleanup done: {stats['deleted']} files deleted, "
        f"{freed_mb} MB freed (retention={retention_key})"
    )

    return {
        "deleted": stats["deleted"],
        "freed_mb": freed_mb,
        "errors": stats["errors"],
        "retention": retention_key,
        "skipped": False,
    }


def _remove_empty_subdirs(pdf_dir: Path):
    """Xóa các thư mục con rỗng trong PDF_DIR."""
    for sub in pdf_dir.iterdir():
        if sub.is_dir() and sub.name != "__pycache__":
            # Kiểm tra rỗng (không có file, chỉ có thể có subfolder rỗng)
            contents = list(sub.iterdir())
            if not contents:
                try:
                    sub.rmdir()
                    log.info(f"  📁 Removed empty dir: {sub.name}")
                except Exception:
                    pass


# ── Background Scheduler ────────────────────────────────────────────────────

_scheduler_thread = None
_scheduler_running = False


def start_cleanup_scheduler(interval_hours: int = 24):
    """Khởi động background scheduler chạy cleanup định kỳ.

    - Daemon thread: tự dừng khi server tắt
    - Chạy cleanup lần đầu sau 60s (cho server khởi động xong)
    - Sau đó chạy mỗi interval_hours
    """
    global _scheduler_thread, _scheduler_running

    if _scheduler_running:
        log.info("⏭ Cleanup scheduler already running")
        return

    _scheduler_running = True

    def scheduler_loop():
        global _scheduler_running
        # Đợi server khởi động
        time.sleep(60)

        while _scheduler_running:
            try:
                settings = load_settings()
                if settings["retention"] != "never":
                    log.info(f"🧹 Running scheduled cleanup (retention={settings['retention']})...")
                    result = cleanup_expired_files()
                    log.info(f"   Result: {result}")
            except Exception as e:
                log.error(f"Scheduler cleanup error: {e}", exc_info=True)

            # Sleep interval (check every minute for graceful shutdown)
            for _ in range(interval_hours * 60):
                if not _scheduler_running:
                    break
                time.sleep(60)

        log.info("🛑 Cleanup scheduler stopped")

    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True, name="cleanup-scheduler")
    _scheduler_thread.start()
    log.info(f"🕐 Cleanup scheduler started (interval={interval_hours}h)")


def stop_cleanup_scheduler():
    """Dừng scheduler (gọi khi shutdown)."""
    global _scheduler_running
    _scheduler_running = False
