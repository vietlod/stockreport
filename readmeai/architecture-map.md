# Architecture Map — Stock Report Components & Stack

This document maps the architectural layers, technology choices, directory structure, and main entry points of the Stock Report application.

---

## 1. Technical Stack

| Layer | Component | Details / Technology |
|---|---|---|
| **Frontend** | Single Page App | Vanilla JS (ES6) + Vanilla CSS + HTML5. Served statically. |
| **Backend** | API Server | FastAPI + Uvicorn (Python 3.12). |
| **Database** | Metadata & History | SQLite (standard Python `sqlite3`). |
| **Scraper** | CafeF Crawler | Playwright (Chromium) to crawl and download BCTC PDFs. |
| | Hải Quan Crawler | `requests` client parsing XLS/PDF statistics. |
| **Integrations**| Google Cloud Suite | Google OAuth2 Client & Drive/Sheets API for remote backups. |
| **Realtime** | UI Updates | WebSockets for progress and download logging. |

---

## 2. Component Diagram

```
       ┌────────────────────────┐
       │   Browser (Web UI)     │
       └───────────┬────────────┘
                   │ HTTPS / WebSockets
                   v
       ┌────────────────────────┐
       │   FastAPI Web Server   │ <─── [server.py]
       └─────┬────────────┬─────┘
             │            │
             │ SQLite     │ Google API
             v            v
      ┌───────────┐  ┌───────────┐
      │ SQLite DB │  │ GDrive &  │
      └───────────┘  │ GSheets   │
                     └───────────┘
```

---

## 3. Directory Layout & Entry Points

- **`server.py`**: The primary ASGI entry point. Initializes FastAPI, sets up routes, WebSocket manager, and runs background scraper threads.
- **`cafef_scraper.py`**: CafeF scraper script. Launches headless Playwright to scrape and save PDF reports.
- **`haiquan_scraper.py`**: Hải Quan scraper. Coordinates Excel downloads and PDF extraction.
- **`google_sync.py`**: Module handling Google Drive and Google Sheets synchronization.
- **`haiquan_sync.py`**: Sync helper for Hải Quan statistics files.
- **`static/`**: Contains the web UI files:
  - `index.html`: Main SPA file.
  - `style.css`: Dark mode layout.
  - `app.js`: Client logic for CafeF.
  - `haiquan_app.js`: Client logic for Hải Quan.
- **`pdf/`**: Local storage for downloaded PDFs.
  - `pdf/_download_history.db`: SQLite database for CafeF.
  - `pdf/haiquan/`: Storage for Hải Quan reports.
  - `pdf/haiquan/_haiquan_history.db`: SQLite database for Hải Quan.
