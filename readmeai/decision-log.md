# Decision Log — Architectural Choices

This document logs critical design choices, framework selections, and infrastructure configurations of the Stock Report application.

---

## 1. Active Decisions

### ADR-04: Domain Migration to `stockreport.tnsai.vn`
- **Date:** 2026-06-25
- **Status:** Approved & Implemented
- **Decision:** Migrate the application domain from `stockreport.tnsai.tech` to `stockreport.tnsai.vn` to align with the core ecosystem.
- **Consequences:**
  - Configured Nginx proxy on VPS host to route `stockreport.tnsai.vn` -> localhost `8002`.
  - Generated Let's Encrypt SSL certificate via Certbot.
  - Removed old `.tech` configurations.
  - Redirect callback changed in Google Cloud Console to `https://stockreport.tnsai.vn/oauth2callback`.

### ADR-03: Google Sign-In (GIS) Integration
- **Date:** 2026-02-25
- **Status:** Approved
- **Decision:** Replace the hardcoded administrator password (`tns/123colEn`) with Google Identity Services (GIS) Sign-In.
- **Consequences:**
  - Restricts access to emails configured in `.env` (`ALLOWED_EMAILS`).
  - Frontend checks authorization header tokens before launching UI.

### ADR-02: Non-Dockerized VPS Host Deployment
- **Date:** 2026-02-11
- **Status:** Approved
- **Decision:** Deploy Stock Report directly on the VPS host using systemd and a Python virtual environment, rather than packing it into a Docker container.
- **Rationale:** Headless Playwright requires extensive Chromium libraries. Installing them in Docker significantly bloats image size and consumes massive CPU/RAM during run loops. Direct host execution leverages host OS dependencies efficiently.

### ADR-01: SQLite for History databases
- **Date:** 2026-02-11
- **Status:** Approved
- **Decision:** Use local SQLite databases (`_download_history.db` and `_haiquan_history.db`) instead of connecting to a centralized PostgreSQL cluster.
- **Rationale:** The scraping history is read-heavy but writes only single files sequentially. SQLite has zero administrative overhead, requires no running service, and avoids port or connection collisions with other databases on the shared VPS.
