# Service Boundaries — Pipeline & Integration Isolation

This document outlines the service boundaries, data models, database limits, and integration interfaces within the Stock Report application.

---

## 1. Internal Pipeline Isolation

The application is strictly divided into two independent statistical pipelines:

```
            ┌──────────────────────────────────────────────┐
            │                 FastAPI App                  │
            └──────────────┬────────────────┬──────────────┘
                           │                │
            ┌──────────────v─────┐    ┌─────v──────────────┐
            │   CafeF Pipeline   │    │ Hải Quan Pipeline  │
            ├────────────────────┤    ├────────────────────┤
            │ • Playwright       │    │ • requests / Excel │
            │ • pdf/ subfolders  │    │ • flat pdf/haiquan │
            │ • _download_       │    │ • _haiquan_        │
            │   history.db       │    │   history.db       │
            └────────────────────┘    └────────────────────┘
```

### A. CafeF CBTT Pipeline
- **Scraper:** Uses Playwright to browse CafeF, search ticker codes, and download PDFs.
- **Storage:** PDFs are grouped by ICB Industry sector codes (e.g. `pdf/8350/` for Banks).
- **History Database:** SQLite database at `pdf/_download_history.db`.
- **Sync:** Syncs metadata to the Google Sheet tab `"DATA"` and PDFs to `GOOGLE_DRIVE_FOLDER_ID`.

### B. Hải Quan Statistics Pipeline
- **Scraper:** Uses standard `requests` sessions to query `files.customs.gov.vn` and download reports.
- **Storage:** PDFs are stored flat in `pdf/haiquan/`.
- **History Database:** SQLite database at `pdf/haiquan/_haiquan_history.db`.
- **Sync:** Syncs metadata to the Google Sheet tab `"HAI QUAN"` and PDFs to `HQ_GOOGLE_DRIVE_FOLDER_ID`.

---

## 2. Shared Integration Boundaries

### A. Google OAuth 2.0 Web Flow
- Shared credentials file: `google_oauth_credentials.json` (ignored by git).
- Shared token file: `_google_token.json` (stores active refresh tokens).
- Redirect Endpoint: `/oauth2callback` processes callback codes and redirects back to `/`.

### B. WebSockets Manager
- Endpoint `/ws/progress` broadcasts real-time progress events.
- To prevent frontend collisions, events carry specific type payloads:
  - CafeF: `type: "progress"` (scraping) and `type: "sync_progress"` (Google sync).
  - Hải Quan: `type: "haiquan_progress"` (scraping) and `type: "haiquan_sync_progress"` (Google sync).
- Frontend tabs listen selectively to update progress stats.
