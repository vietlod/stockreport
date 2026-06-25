# File Criticality Map — Codebase Reference Levels

This document categorizes repository files by risk level and criticality to ensure coding agents do not make unsafe changes.

---

## 1. File Classification Matrix

| File Path | Criticality Level | Impact of Modification | Operational Role |
|---|---|---|---|
| `server.py` | **Tier 1 (Critical)** | High. Serves API routes, WebSocket traffic, and runs scraper background jobs. | Backend Core / Router |
| `.env` | **Tier 1 (Critical)** | High. Contains JWT secret, Google Drive folder IDs, and GIS configuration. | Local Config |
| `google_oauth_credentials.json` | **Tier 1 (Critical)**| High. Contains client credentials for Google API integration. | Auth Key |
| `google_sync.py` | **Tier 2 (Core)** | Medium. Runs Google Drive and Sheets upload sync logic. | Cloud Sync |
| `haiquan_sync.py` | **Tier 2 (Core)** | Medium. Runs Hải Quan Drive upload and Sheets metadata sync. | Cloud Sync |
| `cafef_scraper.py` | **Tier 2 (Core)** | Medium. CafeF report crawler engine. Uses Playwright. | Scraper Engine |
| `haiquan_scraper.py` | **Tier 2 (Core)** | Medium. Hải Quan statistics scraper engine. Uses requests. | Scraper Engine |
| `stock_data.py` | **Tier 2 (Core)** | Low. Ticker sector mapping and dictionary lookup database. | Dictionary Registry |
| `static/index.html` | **Tier 3 (UI)** | Low. Frontend UI layout. Holds SEO and Open Graph tags. | Web frontend |
| `static/app.js` | **Tier 3 (UI)** | Low. CafeF frontend JS control logic. | Web frontend |
| `static/style.css` | **Tier 3 (UI)** | Low. Dark-mode aesthetics and layout styles. | Web UI Styling |

---

## 2. Risk Mitigation Guidelines

- **Tier 1 Modification Rules:** Any changes to Tier 1 files MUST have a corresponding entry in `decision-log.md` and undergo a verification test immediately after implementation.
- **Config changes:** Never hardcode credentials in source code. Use environment variables defined in `.env` and map them in config files.
- **Git staged review:** Staged changes for Tier 1 and Tier 2 files must be carefully inspected via `git diff --stat` before committing.
