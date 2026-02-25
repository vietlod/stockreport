"""
CafeF CBTT Scraper — FastAPI Server
====================================
Web server cung cấp REST API + WebSocket cho UI quản lý scraping.

Endpoints:
  GET  /                        → UI (static/index.html)
  GET  /api/stock-data          → Danh sách exchanges, industries, indexes
  GET  /api/tickers             → Filter tickers theo exchange/icb/index
  GET  /api/history             → Query download history (SQLite)
  GET  /api/stats               → Thống kê theo sàn/ngành/chỉ số
  POST /api/scrape              → Bắt đầu scrape job (async)
  GET  /api/scrape/status       → Trạng thái job hiện tại
  POST /api/scrape/stop         → Dừng job
  POST /api/gdrive/sync         → Upload PDF lên Google Drive
  POST /api/gsheet/sync         → Sync metadata lên Google Sheets
  WS   /ws/progress             → WebSocket realtime progress

Usage:
  python server.py
"""

import os
import sys
import json
import time
import sqlite3
import secrets
import hashlib
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
import uvicorn

# ── Load .env FIRST (trước mọi os.getenv) ──────────────────────────────────
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ── Google Sign-In Auth ─────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
ALLOWED_EMAILS = [e.strip() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()]
JWT_SECRET = os.getenv("JWT_SECRET", "") or secrets.token_hex(32)

# In-memory session store: token → {email, name, sub}
_active_sessions: dict[str, dict] = {}

security = HTTPBearer(auto_error=False)

def _make_session_token(email: str, sub: str) -> str:
    """Tạo session token deterministic từ secret + user info."""
    return hashlib.sha256(f"{JWT_SECRET}:{email}:{sub}".encode()).hexdigest()

async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials not in _active_sessions:
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập")
    return True

# ── Project imports ─────────────────────────────────────────────────────────
from stock_data import registry as stock_registry

PDF_DIR = Path(os.getenv("PDF_DIR", "./pdf"))

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("server")

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="CafeF CBTT Report Manager", version="1.0.0")

# ── WebSocket Manager ───────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = ConnectionManager()

# ── Scrape Job State ────────────────────────────────────────────────────────
class ScrapeJob:
    def __init__(self):
        self.running = False
        self.should_stop = False
        self.progress = {}
        self.thread = None
        self.loop = None

    def start(self, config: dict, loop):
        if self.running:
            return False
        self.running = True
        self.should_stop = False
        self.loop = loop
        self.progress = {
            "status": "starting",
            "current_page": 0,
            "total_pages": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "filtered_stock": 0,
            "filtered_time": 0,
            "drive_synced": 0,
            "current_entry": "",
            "started_at": datetime.now().isoformat(),
        }
        self.thread = threading.Thread(
            target=self._run_scrape, args=(config,), daemon=True
        )
        self.thread.start()
        return True

    def stop(self):
        self.should_stop = True

    def _broadcast_sync(self, data: dict):
        """Thread-safe broadcast to WebSocket clients."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(data), self.loop
            )

    def _run_scrape(self, config: dict):
        """Run the scraper in a background thread."""
        scraper = None
        drive_sync_count = [0]
        try:
            # Dynamically import to avoid circular deps
            import importlib
            import cafef_scraper as scraper_module
            importlib.reload(scraper_module)

            # Override config
            if config.get("stock_code"):
                scraper_module.STOCK_CODE = config["stock_code"]
            else:
                scraper_module.STOCK_CODE = ""

            max_pages = config.get("max_pages", 0)
            scraper_module.MAX_PAGES = max_pages

            scraper_module.TIME_FROM_YEAR = config.get("from_year")
            scraper_module.TIME_FROM_QUARTER = config.get("from_quarter") or ""
            scraper_module.TIME_TO_YEAR = config.get("to_year")
            scraper_module.TIME_TO_QUARTER = config.get("to_quarter") or ""

            scraper = scraper_module.CafeFScraper()

            # Drive sync real-time: upload mỗi file ngay sau khi tải
            drive_sync = None
            if os.getenv("GOOGLE_DRIVE_FOLDER_ID"):
                try:
                    from google_sync import GoogleDriveSync
                    drive_sync = GoogleDriveSync()
                    log.info("☁ Drive sync real-time: enabled")
                except Exception as e:
                    log.warning(f"☁ Drive sync disabled: {e}")

            def on_download(dest):
                if drive_sync and dest.exists():
                    file_id = drive_sync.upload_single(dest)
                    if file_id:
                        drive_sync_count[0] += 1
                        # Mark file as synced in DB + store Drive file ID
                        try:
                            db_conn = get_db()
                            if db_conn:
                                db_conn.execute(
                                    "UPDATE downloads SET drive_synced = 1, drive_file_id = ? WHERE filename = ?",
                                    (file_id, dest.name)
                                )
                                db_conn.commit()
                                db_conn.close()
                        except Exception:
                            pass

            scraper.on_download_callback = on_download

            # Monkey-patch _process_entry to emit progress + stats
            original_process = scraper._process_entry

            def patched_process(page, entry, index):
                if self.should_stop:
                    raise InterruptedError("Stopped by user")
                stock = entry.get("stock_code", "")
                self.progress["current_entry"] = f"{stock} - {entry.get('date', '')}"
                # Multi-ticker tracking
                self.progress["current_ticker"] = scraper.current_ticker
                self.progress["ticker_index"] = scraper.ticker_index
                self.progress["total_tickers"] = scraper.total_tickers
                self._broadcast_sync({"type": "progress", **self.progress})
                original_process(page, entry, index)
                self.progress["downloaded"] = scraper.downloaded
                self.progress["skipped"] = scraper.skipped
                self.progress["failed"] = scraper.failed
                self.progress["filtered_stock"] = scraper.filtered_stock
                self.progress["filtered_time"] = scraper.filtered_time
                self.progress["drive_synced"] = drive_sync_count[0]
                self.progress["error_details"] = scraper.error_details[-5:]  # Last 5
                # Crash recovery tracking
                self.progress["crashed_tickers"] = len(scraper.crashed_tickers)
                self.progress["skipped_tickers"] = len(scraper.skipped_tickers)
                self.progress["browser_restarts"] = scraper.browser_restarts
                # Time range context cho frontend
                if scraper_module.TIME_FROM_YEAR or scraper_module.TIME_TO_YEAR:
                    fr = f"{scraper_module.TIME_FROM_YEAR or ''}{'Q'+scraper_module.TIME_FROM_QUARTER if scraper_module.TIME_FROM_QUARTER else ''}"
                    to = f"{scraper_module.TIME_TO_YEAR or ''}{'Q'+scraper_module.TIME_TO_QUARTER if scraper_module.TIME_TO_QUARTER else ''}"
                    self.progress["time_range"] = f"{fr or '*'} → {to or '*'}"
                summary = get_stats_summary_sync()
                if summary:
                    self.progress["stats_summary"] = summary
                self._broadcast_sync({"type": "progress", **self.progress})

            scraper._process_entry = patched_process

            # Monkey-patch _go_to_next_page to track page progress
            original_next = scraper._go_to_next_page

            def patched_next(page, current_page):
                self.progress["current_page"] = current_page + 1
                self._broadcast_sync({"type": "progress", **self.progress})
                return original_next(page, current_page)

            scraper._go_to_next_page = patched_next

            self.progress["status"] = "running"
            self._broadcast_sync({"type": "progress", **self.progress})

            scraper.run()

            self.progress["downloaded"] = scraper.downloaded
            self.progress["skipped"] = scraper.skipped
            self.progress["failed"] = scraper.failed
            self.progress["filtered_stock"] = scraper.filtered_stock
            self.progress["filtered_time"] = scraper.filtered_time
            self.progress["drive_synced"] = drive_sync_count[0]
            self.progress["error_details"] = scraper.error_details[-5:]
            self.progress["crashed_tickers"] = len(scraper.crashed_tickers)
            self.progress["skipped_tickers"] = len(scraper.skipped_tickers)
            self.progress["browser_restarts"] = scraper.browser_restarts
            self.progress["stats_summary"] = get_stats_summary_sync()
            self.progress["status"] = "completed"
            self.progress["completed_at"] = datetime.now().isoformat()

        except InterruptedError:
            self.progress["downloaded"] = scraper.downloaded
            self.progress["skipped"] = scraper.skipped
            self.progress["failed"] = scraper.failed
            self.progress["filtered_stock"] = scraper.filtered_stock
            self.progress["filtered_time"] = scraper.filtered_time
            self.progress["drive_synced"] = drive_sync_count[0]
            self.progress["crashed_tickers"] = len(scraper.crashed_tickers)
            self.progress["skipped_tickers"] = len(scraper.skipped_tickers)
            self.progress["browser_restarts"] = scraper.browser_restarts
            self.progress["stats_summary"] = get_stats_summary_sync()
            self.progress["status"] = "stopped"
        except Exception as e:
            self.progress["downloaded"] = scraper.downloaded if scraper else 0
            self.progress["skipped"] = scraper.skipped if scraper else 0
            self.progress["failed"] = scraper.failed if scraper else 0
            self.progress["filtered_stock"] = scraper.filtered_stock if scraper else 0
            self.progress["filtered_time"] = scraper.filtered_time if scraper else 0
            self.progress["drive_synced"] = drive_sync_count[0]
            self.progress["crashed_tickers"] = len(scraper.crashed_tickers) if scraper else 0
            self.progress["skipped_tickers"] = len(scraper.skipped_tickers) if scraper else 0
            self.progress["browser_restarts"] = scraper.browser_restarts if scraper else 0
            self.progress["stats_summary"] = get_stats_summary_sync()
            self.progress["status"] = "error"
            self.progress["error"] = str(e)
            log.error(f"Scrape error: {e}", exc_info=True)
        finally:
            self.running = False
            self._broadcast_sync({"type": "progress", **self.progress})
            # Auto Sheet sync: trigger nếu scraping thành công và có download
            if self.progress.get("status") == "completed" and self.progress.get("downloaded", 0) > 0:
                try:
                    log.info("📊 Auto Sheet sync: khởi tạo sau khi scraping hoàn tất...")
                    if self.loop and not sync_job._sheet_running:
                        sync_job.start_sheet(self.loop)
                        log.info("📊 Auto Sheet sync: đã bắt đầu chạy nền")
                except Exception as e:
                    log.warning(f"📊 Auto Sheet sync error: {e}")

scrape_job = ScrapeJob()


# ── Sync Job State (Google Drive / Sheet) ───────────────────────────────────

class SyncJob:
    """Background sync job — Drive và Sheet chạy độc lập, đồng thời."""

    def __init__(self):
        # Trạng thái riêng biệt cho Drive và Sheet
        self._drive_running = False
        self._drive_progress = {}
        self._drive_thread = None

        self._sheet_running = False
        self._sheet_progress = {}
        self._sheet_thread = None

        self.loop = None

    # ── Public properties (backward compat) ──

    @property
    def running(self):
        return self._drive_running or self._sheet_running

    @property
    def sync_type(self):
        parts = []
        if self._drive_running:
            parts.append("drive")
        if self._sheet_running:
            parts.append("sheet")
        return "+".join(parts) if parts else ""

    @property
    def progress(self):
        """Return progress cho sync đang chạy (ưu tiên drive nếu cả 2)."""
        if self._drive_running:
            return self._drive_progress
        if self._sheet_running:
            return self._sheet_progress
        # Trả về progress gần nhất
        return self._drive_progress or self._sheet_progress

    def start_drive(self, loop):
        if self._drive_running:
            return False
        self._drive_running = True
        self.loop = loop
        self._drive_progress = {
            "sync_type": "drive",
            "status": "running",
            "uploaded": 0,
            "skipped": 0,
            "errors": 0,
            "total": 0,
            "current_file": "",
            "started_at": datetime.now().isoformat(),
        }
        self._drive_thread = threading.Thread(
            target=self._run_drive, daemon=True
        )
        self._drive_thread.start()
        return True

    def start_sheet(self, loop):
        if self._sheet_running:
            return False
        self._sheet_running = True
        self.loop = loop
        self._sheet_progress = {
            "sync_type": "sheet",
            "status": "running",
            "rows": 0,
            "started_at": datetime.now().isoformat(),
        }
        self._sheet_thread = threading.Thread(
            target=self._run_sheet, daemon=True
        )
        self._sheet_thread.start()
        return True

    def _broadcast_sync(self, data: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(data), self.loop
            )

    def _run_drive(self):
        try:
            from google_sync import GoogleDriveSync
            sync = GoogleDriveSync()

            def on_phase(phase, detail):
                self._drive_progress.update({
                    "phase": phase,
                    "total": detail.get("total_local", 0),
                    "total_remote": detail.get("total_remote", 0),
                })
                self._broadcast_sync({"type": "sync_progress", **self._drive_progress})

            def on_progress(current, total, filename, stats):
                # ETA calculation
                elapsed = stats.get("elapsed_s", 0)
                processed = stats["uploaded"] + stats["errors"]  # skip doesn't count for ETA
                if processed > 0 and current < total:
                    avg_per_file = elapsed / processed if processed else 0
                    remaining = total - current
                    # Only count remaining uploads (not skips)
                    eta_s = round(avg_per_file * remaining)
                else:
                    eta_s = 0
                self._drive_progress.update({
                    "phase": "uploading",
                    "uploaded": stats["uploaded"],
                    "skipped": stats["skipped"],
                    "errors": stats["errors"],
                    "total": total,
                    "current_file": filename,
                    "current_folder": stats.get("current_folder", ""),
                    "current_index": current,
                    "action": stats.get("action", ""),
                    "error_msg": stats.get("error_msg", ""),
                    "eta_s": eta_s,
                })
                self._broadcast_sync({"type": "sync_progress", **self._drive_progress})

            stats = sync.upload_all(progress_callback=on_progress, phase_callback=on_phase)
            self._drive_progress.update({
                "status": "completed",
                "phase": "done",
                "uploaded": stats["uploaded"],
                "skipped": stats["skipped"],
                "errors": stats["errors"],
                "total": stats["total"],
                "completed_at": datetime.now().isoformat(),
            })
        except Exception as e:
            self._drive_progress["status"] = "error"
            self._drive_progress["error"] = str(e)
            log.error(f"Drive sync error: {e}", exc_info=True)
        finally:
            self._drive_running = False
            self._broadcast_sync({"type": "sync_progress", **self._drive_progress})

    def _run_sheet(self):
        try:
            from google_sync import GoogleSheetSync
            sync = GoogleSheetSync()

            def on_sheet_progress(phase, detail):
                self._sheet_progress.update({
                    "phase": phase,
                    "rows": detail.get("rows", 0),
                })
                self._broadcast_sync({"type": "sync_progress", **self._sheet_progress})

            result = sync.sync(progress_callback=on_sheet_progress)
            self._sheet_progress.update({
                "status": "completed",
                "phase": "done",
                "rows": result.get("rows", 0),
                "skipped": result.get("skipped", False),
                "sheet_id": result.get("sheet_id", ""),
                "completed_at": datetime.now().isoformat(),
            })
        except Exception as e:
            self._sheet_progress["status"] = "error"
            self._sheet_progress["error"] = str(e)
            log.error(f"Sheet sync error: {e}", exc_info=True)
        finally:
            self._sheet_running = False
            self._broadcast_sync({"type": "sync_progress", **self._sheet_progress})


sync_job = SyncJob()


# ══════════════════════════════════════════════════════════════════════════════
# Hải Quan — Job State (HOÀN TOÀN TÁCH BIỆT với CafeF)
# ══════════════════════════════════════════════════════════════════════════════

HQ_PDF_DIR = Path(os.getenv("HQ_PDF_DIR", "./pdf/haiquan"))


class HaiQuanScrapeJob:
    """Background scrape job cho Hải Quan — ISOLATED from CafeF ScrapeJob."""

    def __init__(self):
        self.running = False
        self.should_stop = False
        self.progress = {}
        self.thread = None
        self.loop = None

    def start(self, config: dict, loop):
        if self.running:
            return False
        self.running = True
        self.should_stop = False
        self.progress = {
            "status": "running",
            "phase": "starting",
            "total": 0, "current": 0,
            "downloaded": 0, "skipped": 0, "failed": 0,
            "current_file": "",
            "started_at": datetime.now().isoformat(),
        }
        self.loop = loop
        self.thread = threading.Thread(
            target=self._run_scrape, args=(config,), daemon=True
        )
        self.thread.start()
        return True

    def stop(self):
        self.should_stop = True

    def _broadcast(self, data: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(data), self.loop
            )

    def _run_scrape(self, config: dict):
        try:
            from haiquan_scraper import HaiQuanScraper

            scraper = HaiQuanScraper(pdf_dir=HQ_PDF_DIR)

            def on_progress(current, total, filename, phase):
                if self.should_stop:
                    scraper.stop()
                self.progress.update({
                    "current": current,
                    "total": total,
                    "current_file": filename,
                    "phase": phase,
                    "downloaded": scraper.downloaded,
                    "skipped": scraper.skipped,
                    "failed": scraper.failed,
                })
                self._broadcast({
                    "type": "haiquan_progress",
                    **self.progress,
                })

            result = scraper.run(config=config, on_progress=on_progress)
            self.progress.update({
                "status": "completed",
                "phase": "done",
                **result,
                "completed_at": datetime.now().isoformat(),
            })
            scraper.close()

        except Exception as e:
            self.progress["status"] = "error"
            self.progress["error"] = str(e)
            log.error(f"HaiQuan scrape error: {e}", exc_info=True)
        finally:
            self.running = False
            self._broadcast({"type": "haiquan_progress", **self.progress})


class HaiQuanSyncJob:
    """Background Drive sync job cho Hải Quan — ISOLATED from CafeF SyncJob."""

    def __init__(self):
        self._drive_running = False
        self._drive_progress = {}
        self._drive_thread = None
        self.loop = None

    @property
    def running(self):
        return self._drive_running

    @property
    def progress(self):
        return self._drive_progress

    def start_drive(self, loop):
        if self._drive_running:
            return False
        self._drive_running = True
        self.loop = loop
        self._drive_progress = {
            "sync_type": "haiquan_drive",
            "status": "running",
            "phase": "starting",
            "uploaded": 0, "skipped": 0, "errors": 0,
            "total": 0,
            "started_at": datetime.now().isoformat(),
        }
        self._drive_thread = threading.Thread(
            target=self._run_drive, daemon=True
        )
        self._drive_thread.start()
        return True

    def _broadcast(self, data: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(data), self.loop
            )

    def _run_drive(self):
        try:
            from haiquan_sync import HaiQuanDriveSync
            sync = HaiQuanDriveSync()

            def on_phase(phase, detail):
                self._drive_progress.update({
                    "phase": phase,
                    "total": detail.get("total_local", 0),
                    "total_remote": detail.get("total_remote", 0),
                })
                self._broadcast({
                    "type": "haiquan_sync_progress",
                    **self._drive_progress,
                })

            def on_progress(current, total, filename, stats):
                elapsed = stats.get("elapsed_s", 0)
                processed = stats["uploaded"] + stats["errors"]
                if processed > 0 and current < total:
                    avg_per_file = elapsed / processed
                    remaining = total - current
                    eta_s = round(avg_per_file * remaining)
                else:
                    eta_s = 0
                self._drive_progress.update({
                    "phase": "uploading",
                    "uploaded": stats["uploaded"],
                    "skipped": stats["skipped"],
                    "errors": stats["errors"],
                    "total": total,
                    "current_file": filename,
                    "current_index": current,
                    "action": stats.get("action", ""),
                    "error_msg": stats.get("error_msg", ""),
                    "eta_s": eta_s,
                })
                self._broadcast({
                    "type": "haiquan_sync_progress",
                    **self._drive_progress,
                })

            stats = sync.upload_all(
                progress_callback=on_progress, phase_callback=on_phase
            )
            self._drive_progress.update({
                "status": "completed",
                "phase": "done",
                "uploaded": stats["uploaded"],
                "skipped": stats["skipped"],
                "errors": stats["errors"],
                "total": stats["total"],
                "completed_at": datetime.now().isoformat(),
            })
        except Exception as e:
            self._drive_progress["status"] = "error"
            self._drive_progress["error"] = str(e)
            log.error(f"HaiQuan Drive sync error: {e}", exc_info=True)
        finally:
            self._drive_running = False
            self._broadcast({
                "type": "haiquan_sync_progress",
                **self._drive_progress,
            })


haiquan_scrape_job = HaiQuanScrapeJob()
haiquan_sync_job = HaiQuanSyncJob()

# ── Helper: Query SQLite ────────────────────────────────────────────────────

def get_db():
    db_path = PDF_DIR / "_download_history.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Auto-migration: đảm bảo cột mới tồn tại
    for col, col_type in [("drive_synced", "INTEGER DEFAULT 0"), ("drive_file_id", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE downloads ADD COLUMN {col} {col_type}")
        except Exception:
            pass  # column already exists
    return conn


def get_stats_summary_sync() -> dict:
    """Lấy summary thống kê từ DB (sync, dùng trong thread)."""
    conn = get_db()
    if not conn:
        return {}
    try:
        row = conn.execute(
            "SELECT COUNT(*) as total, COUNT(DISTINCT stock_code) as unique_stocks, "
            "SUM(file_size) as total_size FROM downloads"
        ).fetchone()
        if row and row["total"]:
            return {
                "total_files": row["total"],
                "unique_stocks": row["unique_stocks"],
                "total_size_mb": round((row["total_size"] or 0) / 1024 / 1024, 1),
            }
    finally:
        conn.close()
    return {}


# ── API Routes ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    stock_registry.load()
    # Start cleanup scheduler (auto-delete expired files every 24h)
    from cleanup import start_cleanup_scheduler
    start_cleanup_scheduler(interval_hours=24)
    log.info("🚀 Server started, StockRegistry loaded, Cleanup scheduler started")


@app.get("/api/stock-data")
async def get_stock_data():
    """Trả về toàn bộ dữ liệu lookup cho frontend."""
    return stock_registry.to_json()


@app.get("/api/tickers")
async def get_tickers(
    exchange: str = Query(None),
    icb_code: str = Query(None),
    index_code: str = Query(None),
    search: str = Query(None),
):
    """Filter tickers theo sàn/ngành/chỉ số."""
    tickers = set()

    if exchange:
        tickers = set(stock_registry.tickers_by_exchange(exchange))
    elif icb_code:
        tickers = set(stock_registry.tickers_by_icb_code(icb_code))
    elif index_code:
        tickers = set(stock_registry.tickers_by_index(index_code))

    if search:
        search = search.upper()
        if tickers:
            tickers = {t for t in tickers if search in t}
        else:
            # Search all
            all_t = set(stock_registry._exchange.keys()) | set(stock_registry._industry.keys())
            tickers = {t for t in all_t if search in t}

    result = []
    for t in sorted(tickers):
        result.append({
            "ticker": t,
            "exchange": stock_registry.get_exchange(t),
            "icb_code": stock_registry.get_icb_code(t),
            "icb_name": stock_registry.get_icb_name(t),
            "indexes": stock_registry.get_indexes(t),
        })

    return {"tickers": result, "count": len(result)}


@app.get("/api/history")
async def get_history(
    stock_code: str = Query(None),
    icb_code: str = Query(None),
    exchange: str = Query(None),
    quarter_year: str = Query(None),
    drive_synced: int = Query(None, ge=0, le=1),
    sort_by: str = Query("downloaded_at"),
    sort_dir: str = Query("desc"),
    limit: int = Query(100),
    offset: int = Query(0),
):
    """Query download history từ SQLite với filter + sorting."""
    conn = get_db()
    if not conn:
        return {"records": [], "total": 0}

    conditions = []
    params = []
    if stock_code:
        conditions.append("stock_code = ?")
        params.append(stock_code.upper())
    if icb_code:
        conditions.append("icb_code = ?")
        params.append(icb_code)
    if exchange:
        conditions.append("exchange = ?")
        params.append(exchange.upper())
    if quarter_year:
        conditions.append("quarter_year LIKE ?")
        params.append(f"%{quarter_year}%")
    if drive_synced is not None:
        conditions.append("drive_synced = ?")
        params.append(drive_synced)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Sort validation
    allowed_sorts = {
        "stock_code": "stock_code",
        "quarter_year": "quarter_year",
        "downloaded_at": "downloaded_at",
    }
    sort_col = allowed_sorts.get(sort_by, "downloaded_at")
    sort_direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    total = conn.execute(
        f"SELECT COUNT(*) FROM downloads {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM downloads {where} ORDER BY {sort_col} {sort_direction} LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    conn.close()
    return {
        "records": [dict(r) for r in rows],
        "total": total,
    }


@app.get("/api/history/filters")
async def get_history_filters():
    """Trả danh sách distinct exchanges và ICB codes cho filter dropdowns."""
    conn = get_db()
    if not conn:
        return {"exchanges": [], "icb_codes": []}

    exchanges = [r[0] for r in conn.execute(
        "SELECT DISTINCT exchange FROM downloads WHERE exchange != '' AND exchange IS NOT NULL ORDER BY exchange"
    ).fetchall()]

    icb_codes = [r[0] for r in conn.execute(
        "SELECT DISTINCT icb_code FROM downloads WHERE icb_code != '' AND icb_code IS NOT NULL ORDER BY icb_code"
    ).fetchall()]

    conn.close()
    return {"exchanges": exchanges, "icb_codes": icb_codes}


@app.delete("/api/history/cleanup")
async def cleanup_history(
    stock_code: str = Query(None),
    icb_code: str = Query(None),
    exchange: str = Query(None),
    drive_synced: int = Query(None, ge=0, le=1),
    _admin=Depends(require_admin),
):
    """Xóa records theo filter: xóa file local + DB record.
    Dùng cùng filter params như GET /api/history.
    """
    conn = get_db()
    if not conn:
        return {"deleted": 0, "freed_bytes": 0, "error": "DB not found"}

    conditions = []
    params = []
    if stock_code:
        conditions.append("stock_code = ?")
        params.append(stock_code.upper())
    if icb_code:
        conditions.append("icb_code = ?")
        params.append(icb_code)
    if exchange:
        conditions.append("exchange = ?")
        params.append(exchange.upper())
    if drive_synced is not None:
        conditions.append("drive_synced = ?")
        params.append(drive_synced)

    if not conditions:
        conn.close()
        return {"deleted": 0, "freed_bytes": 0, "error": "Cần ít nhất 1 filter để tránh xóa toàn bộ"}

    where = f"WHERE {' AND '.join(conditions)}"

    # Lấy danh sách files cần xóa
    rows = conn.execute(
        f"SELECT id, filename, icb_code, file_size FROM downloads {where}", params
    ).fetchall()

    if not rows:
        conn.close()
        return {"deleted": 0, "freed_bytes": 0}

    deleted = 0
    freed = 0
    dirs_to_check = set()

    for r in rows:
        filename = r["filename"]
        file_icb = r["icb_code"] or ""
        file_size = r["file_size"] or 0

        # Xóa file vật lý
        if file_icb:
            file_path = PDF_DIR / file_icb / filename
        else:
            file_path = PDF_DIR / filename

        try:
            if file_path.exists():
                file_path.unlink()
                freed += file_size
                if file_icb:
                    dirs_to_check.add(PDF_DIR / file_icb)
        except Exception as e:
            log.warning(f"🗑 Không thể xóa file {file_path}: {e}")

    # Xóa records khỏi DB
    conn.execute(f"DELETE FROM downloads {where}", params)
    conn.commit()
    deleted = conn.total_changes
    conn.close()

    # Dọn thư mục ICB rỗng
    for d in dirs_to_check:
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
                log.info(f"🗑 Xóa thư mục rỗng: {d.name}")
        except Exception:
            pass

    log.info(f"🗑 Cleanup: {deleted} records, giải phóng {freed / 1024 / 1024:.1f}MB")
    return {"deleted": deleted, "freed_bytes": freed}


@app.get("/api/stats")
async def get_stats():
    """Thống kê download theo sàn/ngành/chỉ số."""
    conn = get_db()
    if not conn:
        return {"by_exchange": [], "by_industry": [], "by_index": [], "summary": {}}

    # By exchange
    by_exchange = conn.execute("""
        SELECT exchange, COUNT(*) as count, SUM(file_size) as total_size
        FROM downloads WHERE exchange != '' GROUP BY exchange ORDER BY count DESC
    """).fetchall()

    # By ICB
    by_industry = conn.execute("""
        SELECT icb_code, COUNT(*) as count, SUM(file_size) as total_size
        FROM downloads WHERE icb_code != '' GROUP BY icb_code ORDER BY count DESC
    """).fetchall()

    # Summary
    summary = conn.execute("""
        SELECT COUNT(*) as total, COUNT(DISTINCT stock_code) as unique_stocks,
               SUM(file_size) as total_size
        FROM downloads
    """).fetchone()

    # Enrich industry with names
    industries = []
    for row in by_industry:
        code = row["icb_code"]
        tickers = stock_registry.tickers_by_icb_code(code)
        # Get name from any ticker in this group
        name = ""
        for t in tickers[:1]:
            name = stock_registry.get_icb_name(t)
        industries.append({
            "icb_code": code,
            "icb_name": name,
            "count": row["count"],
            "total_size_mb": round((row["total_size"] or 0) / 1024 / 1024, 1),
        })

    # Stats per index
    by_index = []
    for idx in stock_registry.all_indexes():
        idx_tickers = set(stock_registry.tickers_by_index(idx))
        # Count downloaded files for tickers in this index
        if idx_tickers:
            placeholders = ",".join("?" * len(idx_tickers))
            row = conn.execute(
                f"SELECT COUNT(*) as count FROM downloads WHERE stock_code IN ({placeholders})",
                list(idx_tickers)
            ).fetchone()
            by_index.append({"index": idx, "count": row["count"], "total_tickers": len(idx_tickers)})

    conn.close()
    return {
        "by_exchange": [dict(r) for r in by_exchange],
        "by_industry": industries,
        "by_index": by_index,
        "summary": {
            "total_files": summary["total"],
            "unique_stocks": summary["unique_stocks"],
            "total_size_mb": round((summary["total_size"] or 0) / 1024 / 1024, 1),
        },
    }


@app.post("/api/scrape")
async def start_scrape(config: dict = {}):
    """Bắt đầu scrape job bất đồng bộ."""
    if scrape_job.running:
        return JSONResponse(
            status_code=409, content={"error": "A scrape job is already running"}
        )

    loop = asyncio.get_event_loop()
    started = scrape_job.start(config, loop)
    if started:
        return {"status": "started", "config": config}
    return JSONResponse(status_code=500, content={"error": "Failed to start"})


@app.get("/api/scrape/status")
async def scrape_status():
    """Trạng thái job hiện tại."""
    return {
        "running": scrape_job.running,
        "progress": scrape_job.progress,
    }


@app.post("/api/scrape/stop")
async def stop_scrape():
    """Dừng job đang chạy."""
    if not scrape_job.running:
        return {"status": "not_running"}
    scrape_job.stop()
    return {"status": "stopping"}


# ── Auth (Google Sign-In) ───────────────────────────────────────────────────

@app.get("/api/auth/config")
async def auth_config():
    """Public: trả Google client_id cho frontend GIS."""
    return {"google_client_id": GOOGLE_CLIENT_ID}


@app.post("/api/auth/google")
async def auth_google(data: dict):
    """Xác thực Google ID token, trả session token."""
    credential = data.get("credential", "")
    if not credential:
        return JSONResponse(status_code=400, content={"error": "Missing credential"})
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        idinfo = id_token.verify_oauth2_token(
            credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        email = idinfo.get("email", "")
        if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
            log.warning(f"🚫 Login rejected: {email} not in whitelist")
            return JSONResponse(status_code=403,
                content={"error": f"Email {email} không được phép truy cập"})

        sub = idinfo["sub"]
        token = _make_session_token(email, sub)
        _active_sessions[token] = {
            "email": email,
            "name": idinfo.get("name", ""),
            "sub": sub,
        }
        log.info(f"✅ Login: {email}")
        return {
            "ok": True,
            "token": token,
            "email": email,
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture", ""),
        }
    except ValueError as e:
        log.warning(f"🚫 Invalid id_token: {e}")
        return JSONResponse(status_code=401,
            content={"error": f"Token không hợp lệ"})


# ── Settings & Cleanup ──────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Lấy cài đặt hiện tại + danh sách retention options."""
    from cleanup import load_settings, RETENTION_OPTIONS
    settings = load_settings()
    return {
        **settings,
        "retention_options": {
            k: v["label"] for k, v in RETENTION_OPTIONS.items()
        },
    }


@app.post("/api/settings")
async def update_settings(data: dict, _: bool = Depends(require_admin)):
    """Cập nhật cài đặt. Body: {retention: '1q'}"""
    from cleanup import save_settings
    try:
        saved = save_settings(data)
        return {"status": "ok", **saved}
    except Exception as e:
        log.error(f"Save settings error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/cleanup/run")
async def run_cleanup(_: bool = Depends(require_admin)):
    """Chạy cleanup thủ công. Xóa files hết hạn retention ngay lập tức."""
    from cleanup import cleanup_expired_files
    try:
        result = cleanup_expired_files()
        return {"status": "ok", **result}
    except Exception as e:
        log.error(f"Manual cleanup error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Google OAuth (Web flow for production) ───────────────────────────────────

@app.get("/api/oauth2/start")
async def oauth2_start(_: bool = Depends(require_admin)):
    """Trả URL để redirect user đến Google consent. Production: https://stockreport.khoviet.com/oauth2callback"""
    try:
        from google_sync import get_oauth_authorization_url
        url = get_oauth_authorization_url()
        return {"url": url}
    except Exception as e:
        log.error(f"OAuth start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/oauth2callback")
async def oauth2_callback(code: str = Query(None), error: str = Query(None)):
    """Nhận callback từ Google, lưu token, redirect về /"""
    from urllib.parse import quote
    if error:
        log.warning(f"OAuth callback error: {error}")
        return RedirectResponse(url="/?oauth=error&msg=" + quote(error, safe=""), status_code=302)
    if not code:
        return RedirectResponse(url="/?oauth=error&msg=no_code", status_code=302)
    try:
        from google_sync import save_oauth_token_from_callback
        save_oauth_token_from_callback(code)
        return RedirectResponse(url="/?oauth=success", status_code=302)
    except Exception as e:
        log.error(f"OAuth callback save error: {e}", exc_info=True)
        return RedirectResponse(url="/?oauth=error&msg=" + quote(str(e)[:80], safe=""), status_code=302)


@app.get("/api/oauth2/status")
async def oauth2_status():
    """Kiểm tra đã có token chưa."""
    from pathlib import Path
    token_file = Path(__file__).parent / "_google_token.json"
    return {"connected": token_file.exists()}


@app.get("/api/oauth2/debug")
async def oauth2_debug():
    """Debug: redirect_uri + client_id để so khớp với Google Cloud Console."""
    from urllib.parse import urlparse, parse_qs
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "https://stockreport.khoviet.com/oauth2callback")
    result = {"redirect_uri": redirect_uri, "client_id": "", "error": None}
    try:
        from google_sync import get_oauth_authorization_url
        url = get_oauth_authorization_url()
        params = parse_qs(urlparse(url).query)
        result["redirect_uri_in_request"] = params.get("redirect_uri", [""])[0]
        result["client_id"] = params.get("client_id", [""])[0]
    except Exception as e:
        result["error"] = str(e)
    result["hint"] = "redirect_uri phải khớp CHÍNH XÁC trong OAuth client có client_id trên"
    return result


# ── Google Integration ──────────────────────────────────────────────────────

def _check_google_drive_config():
    """Validate Google Drive config before sync."""
    oauth_path = os.getenv("GOOGLE_OAUTH_CREDENTIALS", "./google_oauth_credentials.json")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    if not Path(oauth_path).exists():
        raise ValueError(
            f"Không tìm thấy {oauth_path}. Tạo OAuth client từ Google Cloud Console."
        )
    if not folder_id:
        raise ValueError("Chưa cấu hình GOOGLE_DRIVE_FOLDER_ID trong .env")


def _check_google_sheet_config():
    """Validate Google Sheet config before sync."""
    oauth_path = os.getenv("GOOGLE_OAUTH_CREDENTIALS", "./google_oauth_credentials.json")
    if not Path(oauth_path).exists():
        raise ValueError(
            f"Không tìm thấy {oauth_path}. Tạo OAuth client từ Google Cloud Console."
        )


@app.post("/api/gdrive/sync")
async def gdrive_sync(_: bool = Depends(require_admin)):
    """Upload tất cả PDF lên Google Drive (chạy nền).

    Trả response ngay, sync tiếp tục chạy trong background thread.
    Tiến trình broadcast qua WebSocket (type: sync_progress).
    """
    try:
        _check_google_drive_config()
        loop = asyncio.get_event_loop()
        started = sync_job.start_drive(loop)
        if not started:
            return JSONResponse(
                status_code=409,
                content={"error": "Drive sync đang chạy. Vui lòng đợi hoàn tất."}
            )
        return {"status": "started", "sync_type": "drive"}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except FileNotFoundError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"Google Drive sync error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/gdrive/test")
async def gdrive_test(_: bool = Depends(require_admin)):
    """Diagnostic: test Drive upload with 1 PDF file. Returns detailed results."""
    try:
        _check_google_drive_config()
        from google_sync import GoogleDriveSync, DRIVE_FOLDER_ID, PDF_DIR, SCOPES
        from googleapiclient.http import MediaFileUpload

        sync = GoogleDriveSync()
        service = sync._service()

        # Find first PDF
        pdfs = sorted(PDF_DIR.rglob("*.pdf"))
        if not pdfs:
            return {"error": "No PDF files found in PDF_DIR", "pdf_dir": str(PDF_DIR)}

        test_file = pdfs[0]
        local_size = test_file.stat().st_size
        filename = test_file.name
        icb_folder = test_file.parent.name if test_file.parent != PDF_DIR else None

        # Get parent folder
        if icb_folder:
            parent_id = sync._get_or_create_folder(service, icb_folder, DRIVE_FOLDER_ID)
        else:
            parent_id = DRIVE_FOLDER_ID

        # Upload (non-resumable)
        media = MediaFileUpload(
            str(test_file), mimetype="application/pdf", resumable=False
        )
        result = service.files().create(
            body={"name": f"_test_{filename}", "parents": [parent_id]},
            media_body=media, fields="id,name,size,mimeType",
            supportsAllDrives=True,
        ).execute()

        return {
            "status": "success",
            "local_file": str(test_file),
            "local_size": local_size,
            "icb_folder": icb_folder,
            "parent_id": parent_id,
            "drive_folder_id": DRIVE_FOLDER_ID,
            "remote": result,
            "scopes": SCOPES,
            "creds_type": type(sync.creds).__name__,
        }
    except Exception as e:
        import traceback
        from googleapiclient.errors import HttpError
        err_detail = {"error": str(e), "traceback": traceback.format_exc()}
        if isinstance(e, HttpError):
            err_detail["http_status"] = e.resp.status
            err_detail["http_reason"] = getattr(e.resp, "reason", "")
            try:
                err_detail["http_content"] = e.content.decode("utf-8", errors="replace") if e.content else ""
            except Exception:
                err_detail["http_content"] = str(e.content)[:500]
        return JSONResponse(status_code=500, content=err_detail)


@app.post("/api/gsheet/sync")
async def gsheet_sync(_: bool = Depends(require_admin)):
    """Sync metadata lên Google Sheets (chạy nền).

    Trả response ngay, sync tiếp tục chạy trong background thread.
    Incremental: skip nếu data không thay đổi (hash-based).
    """
    try:
        _check_google_sheet_config()
        loop = asyncio.get_event_loop()
        started = sync_job.start_sheet(loop)
        if not started:
            return JSONResponse(
                status_code=409,
                content={"error": "Sheet sync đang chạy. Vui lòng đợi hoàn tất."}
            )
        return {"status": "started", "sync_type": "sheet"}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except FileNotFoundError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"Google Sheet sync error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/sync/status")
async def sync_status():
    """Trạng thái sync hiện tại (Drive và/hoặc Sheet)."""
    return {
        "running": sync_job.running,
        "sync_type": sync_job.sync_type,
        "drive": sync_job._drive_progress if sync_job._drive_progress else None,
        "sheet": sync_job._sheet_progress if sync_job._sheet_progress else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Hải Quan — API Routes (HOÀN TOÀN TÁCH BIỆT với CafeF)
# ══════════════════════════════════════════════════════════════════════════════


def get_hq_db():
    """Get HaiQuan SQLite connection (separate from CafeF)."""
    db_path = HQ_PDF_DIR / "_haiquan_history.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


@app.post("/api/haiquan/scrape")
async def hq_start_scrape(config: dict = {}):
    """Bắt đầu Hải Quan scrape job."""
    if haiquan_scrape_job.running:
        return JSONResponse(
            status_code=409,
            content={"error": "HaiQuan scrape job đang chạy"}
        )
    loop = asyncio.get_event_loop()
    started = haiquan_scrape_job.start(config, loop)
    if started:
        return {"status": "started", "config": config}
    return JSONResponse(status_code=500, content={"error": "Failed to start"})


@app.get("/api/haiquan/scrape/status")
async def hq_scrape_status():
    """Trạng thái HaiQuan scrape job."""
    return {
        "running": haiquan_scrape_job.running,
        "progress": haiquan_scrape_job.progress,
    }


@app.post("/api/haiquan/scrape/stop")
async def hq_stop_scrape():
    """Dừng HaiQuan scrape job."""
    if not haiquan_scrape_job.running:
        return {"status": "not_running"}
    haiquan_scrape_job.stop()
    return {"status": "stopping"}


@app.get("/api/haiquan/history")
async def hq_get_history(
    year: int = Query(None),
    month: int = Query(None),
    period: str = Query(None),
    report_type: str = Query(None),
    report_code: str = Query(None),
    drive_synced: int = Query(None, ge=0, le=1),
    search: str = Query(None),
    sort_by: str = Query("downloaded_at"),
    sort_dir: str = Query("desc"),
    limit: int = Query(100),
    offset: int = Query(0),
):
    """Query HaiQuan download history."""
    conn = get_hq_db()
    if not conn:
        return {"records": [], "total": 0}

    conditions = []
    params = []
    if year is not None:
        conditions.append("year = ?")
        params.append(year)
    if month is not None:
        conditions.append("month = ?")
        params.append(month)
    if period:
        conditions.append("period = ?")
        params.append(period.upper())
    if report_type:
        conditions.append("report_type = ?")
        params.append(report_type.upper())
    if report_code:
        conditions.append("report_code = ?")
        params.append(report_code.upper())
    if drive_synced is not None:
        conditions.append("drive_synced = ?")
        params.append(drive_synced)
    if search:
        conditions.append("filename LIKE ?")
        params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    allowed_sorts = {
        "filename": "filename",
        "year": "year",
        "month": "month",
        "report_code": "report_code",
        "report_type": "report_type",
        "downloaded_at": "downloaded_at",
        "file_size": "file_size",
    }
    sort_col = allowed_sorts.get(sort_by, "downloaded_at")
    sort_direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    total = conn.execute(
        f"SELECT COUNT(*) FROM haiquan_downloads {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM haiquan_downloads {where} "
        f"ORDER BY {sort_col} {sort_direction} LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    conn.close()
    return {"records": [dict(r) for r in rows], "total": total}


@app.get("/api/haiquan/history/filters")
async def hq_get_history_filters():
    """Filter options cho HaiQuan history."""
    conn = get_hq_db()
    if not conn:
        return {"years": [], "report_types": [], "report_codes": [], "periods": []}

    years = [r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM haiquan_downloads WHERE year > 0 ORDER BY year DESC"
    ).fetchall()]
    report_types = [r[0] for r in conn.execute(
        "SELECT DISTINCT report_type FROM haiquan_downloads "
        "WHERE report_type IS NOT NULL AND report_type != '' ORDER BY report_type"
    ).fetchall()]
    report_codes = [r[0] for r in conn.execute(
        "SELECT DISTINCT report_code FROM haiquan_downloads "
        "WHERE report_code IS NOT NULL AND report_code != '' ORDER BY report_code"
    ).fetchall()]
    periods = [r[0] for r in conn.execute(
        "SELECT DISTINCT period FROM haiquan_downloads "
        "WHERE period IS NOT NULL AND period != '' ORDER BY period"
    ).fetchall()]

    conn.close()
    return {
        "years": years,
        "report_types": report_types,
        "report_codes": report_codes,
        "periods": periods,
    }


@app.delete("/api/haiquan/history/cleanup")
async def hq_cleanup_history(
    request: Request,
    _admin=Depends(require_admin),
):
    """Xóa HaiQuan records + files theo filter (JSON body)."""
    body = await request.json()
    year = body.get("year")
    report_type = body.get("report_type")
    report_code = body.get("report_code")
    drive_synced = body.get("drive_synced")
    conn = get_hq_db()
    if not conn:
        return {"deleted": 0, "freed_bytes": 0, "error": "DB not found"}

    conditions = []
    params = []
    if year is not None:
        conditions.append("year = ?")
        params.append(year)
    if report_type:
        conditions.append("report_type = ?")
        params.append(report_type.upper())
    if report_code:
        conditions.append("report_code = ?")
        params.append(report_code.upper())
    if drive_synced is not None:
        conditions.append("drive_synced = ?")
        params.append(drive_synced)

    if not conditions:
        conn.close()
        return {"deleted": 0, "freed_bytes": 0,
                "error": "Cần ít nhất 1 filter để tránh xóa toàn bộ"}

    where = f"WHERE {' AND '.join(conditions)}"
    rows = conn.execute(
        f"SELECT id, filename, file_size FROM haiquan_downloads {where}", params
    ).fetchall()

    if not rows:
        conn.close()
        return {"deleted": 0, "freed_bytes": 0}

    freed = 0
    for r in rows:
        file_path = HQ_PDF_DIR / r["filename"]
        try:
            if file_path.exists():
                freed += r["file_size"] or 0
                file_path.unlink()
        except Exception as e:
            log.warning(f"🗑 Cannot delete {file_path}: {e}")

    conn.execute(f"DELETE FROM haiquan_downloads {where}", params)
    conn.commit()
    deleted = conn.total_changes
    conn.close()

    log.info(f"🗑 HQ Cleanup: {deleted} records, freed {freed / 1024 / 1024:.1f}MB")
    return {"deleted": deleted, "freed_bytes": freed}


@app.get("/api/haiquan/stats")
async def hq_get_stats():
    """Thống kê HaiQuan downloads."""
    conn = get_hq_db()
    if not conn:
        return {"by_year": [], "by_type": [], "by_code": [], "summary": {}}

    by_year = [dict(r) for r in conn.execute("""
        SELECT year, COUNT(*) as count, SUM(file_size) as total_size
        FROM haiquan_downloads WHERE year > 0
        GROUP BY year ORDER BY year DESC
    """).fetchall()]

    by_type = [dict(r) for r in conn.execute("""
        SELECT report_type, COUNT(*) as count, SUM(file_size) as total_size
        FROM haiquan_downloads WHERE report_type != ''
        GROUP BY report_type ORDER BY count DESC
    """).fetchall()]

    by_code = [dict(r) for r in conn.execute("""
        SELECT report_code, COUNT(*) as count, SUM(file_size) as total_size
        FROM haiquan_downloads WHERE report_code != ''
        GROUP BY report_code ORDER BY count DESC
    """).fetchall()]

    summary = conn.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT year) as unique_years,
               COUNT(DISTINCT report_code) as unique_codes,
               SUM(file_size) as total_size
        FROM haiquan_downloads
    """).fetchone()

    conn.close()
    return {
        "by_year": by_year,
        "by_type": by_type,
        "by_code": by_code,
        "summary": {
            "total_files": summary["total"],
            "unique_years": summary["unique_years"],
            "unique_codes": summary["unique_codes"],
            "total_size_mb": round((summary["total_size"] or 0) / 1024 / 1024, 1),
        },
    }


@app.post("/api/haiquan/gdrive/sync")
async def hq_gdrive_sync(_: bool = Depends(require_admin)):
    """Upload HaiQuan PDFs lên Google Drive (folder riêng)."""
    try:
        _check_google_drive_config()
        loop = asyncio.get_event_loop()
        started = haiquan_sync_job.start_drive(loop)
        if not started:
            return JSONResponse(
                status_code=409,
                content={"error": "HQ Drive sync đang chạy. Vui lòng đợi."}
            )
        return {"status": "started", "sync_type": "haiquan_drive"}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"HQ Drive sync error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/haiquan/sync/status")
async def hq_sync_status():
    """Trạng thái HaiQuan sync."""
    return {
        "running": haiquan_sync_job.running,
        "drive": haiquan_sync_job.progress if haiquan_sync_job.progress else None,
    }


@app.post("/api/haiquan/gsheet/sync")
async def hq_gsheet_sync(_: bool = Depends(require_admin)):
    """Sync HaiQuan metadata lên Google Sheets."""
    try:
        _check_google_sheet_config()
        from haiquan_sync import HaiQuanSheetSync
        syncer = HaiQuanSheetSync()
        result = syncer.sync()
        return result
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"HQ Sheet sync error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── WebSocket ───────────────────────────────────────────────────────────────


@app.websocket("/ws/progress")
async def websocket_progress(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep alive — client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Static Files ────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
