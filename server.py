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
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# ── Project imports ─────────────────────────────────────────────────────────
from stock_data import registry as stock_registry

load_dotenv()

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

            scraper = scraper_module.CafeFScraper()

            # Monkey-patch _process_entry to emit progress
            original_process = scraper._process_entry

            def patched_process(page, entry, index):
                if self.should_stop:
                    raise InterruptedError("Stopped by user")
                stock = entry.get("stock_code", "")
                self.progress["current_entry"] = f"{stock} - {entry.get('date', '')}"
                self._broadcast_sync({"type": "progress", **self.progress})
                original_process(page, entry, index)
                self.progress["downloaded"] = scraper.downloaded
                self.progress["skipped"] = scraper.skipped
                self.progress["failed"] = scraper.failed
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

            self.progress["status"] = "completed"
            self.progress["completed_at"] = datetime.now().isoformat()

        except InterruptedError:
            self.progress["status"] = "stopped"
        except Exception as e:
            self.progress["status"] = "error"
            self.progress["error"] = str(e)
            log.error(f"Scrape error: {e}", exc_info=True)
        finally:
            self.running = False
            self._broadcast_sync({"type": "progress", **self.progress})

scrape_job = ScrapeJob()

# ── Helper: Query SQLite ────────────────────────────────────────────────────
def get_db():
    db_path = PDF_DIR / "_download_history.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── API Routes ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    stock_registry.load()
    log.info("🚀 Server started, StockRegistry loaded")


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
    quarter_year: str = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    """Query download history từ SQLite."""
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
    if quarter_year:
        conditions.append("quarter_year LIKE ?")
        params.append(f"%{quarter_year}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM downloads {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM downloads {where} ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    conn.close()
    return {
        "records": [dict(r) for r in rows],
        "total": total,
    }


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


# ── Google Integration ──────────────────────────────────────────────────────

@app.post("/api/gdrive/sync")
async def gdrive_sync():
    """Upload tất cả PDF lên Google Drive."""
    try:
        from google_sync import GoogleDriveSync
        sync = GoogleDriveSync()
        stats = sync.upload_all()
        return {"status": "ok", **stats}
    except FileNotFoundError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"Google Drive sync error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/gsheet/sync")
async def gsheet_sync():
    """Sync metadata lên Google Sheets."""
    try:
        from google_sync import GoogleSheetSync
        sync = GoogleSheetSync()
        result = sync.sync()
        return {"status": "ok", **result}
    except FileNotFoundError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log.error(f"Google Sheet sync error: {e}", exc_info=True)
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
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
