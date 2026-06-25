# Memory.md — Persistent Session State & Learnings

This document persists the active context, state, and learnings of AI agent sessions for the Stock Report application.

---

## 1. Project Context & Environment

- **Application Name:** Report Manager (CafeF CBTT & Hải Quan)
- **Domain:** `stockreport.tnsai.vn` (migrated from `stockreport.tnsai.tech` / `stockreport.khoviet.com` on 2026-06-25)
- **Shared VPS IP:** `31.97.110.12` (Shared with PDF2QMD, Ecodata, PDFHub, Fintech, Bodulieu, Marketplace, and WordPress instances)
- **Deployment Type:** Direct host deployment (non-Dockerized). Nginx on the host proxies traffic to the FastAPI app running under a systemd service.

---

## 2. Core Architecture Reference

- **Backend API & Server:** FastAPI (Python 3.12). Runs as a systemd service `stockreport` on port `8002`.
- **Frontend SPA:** Single-page app using Vanilla HTML5, Vanilla CSS, and Vanilla JS (ES6+). Served statically by the FastAPI server from the `/static` directory.
- **Scraper Engines:** Playwright (Chromium) for CafeF reports; `requests` for Hải Quan statistics.
- **Database:** SQLite. Separate databases are used for isolation:
  - CafeF download history: `pdf/_download_history.db`
  - Hải Quan download history: `pdf/haiquan/_haiquan_history.db`
- **Google Integration:** Uses Google API Client with OAuth2 (for Drive and Sheets sync). OAuth credentials are local and ignored by git (`google_oauth_credentials.json`).
- **Nginx Config Path:** `/etc/nginx/sites-available/stockreport.tnsai.vn` (symlinked to `/etc/nginx/sites-enabled/`).

---

## 3. Important Learnings & Discoveries

### A. Nginx Host Fallback & SSO Redirect Issue
- **Discovery:** If a domain points to the VPS via DNS but Nginx has no server block matching it, Nginx routes requests to the first loaded SSL block (the default/fallback block). On this VPS, the fallback block resolved to `tnsai.vn` (the TNS SSO Portal).
- **Fix:** Creating a dedicated Nginx block for `stockreport.tnsai.vn` successfully routed requests to the local port `8002`, bypassing the default SSO redirection.

### B. Google Cloud Console Redirect URI
- **Discovery:** When changing redirect URIs in `google_oauth_credentials.json` and the environment files, the Google OAuth 2.0 client ID must also be configured inside the Google Cloud Console dashboard to allow origins/callbacks from `https://stockreport.tnsai.vn`.

### C. SSL Configuration & Shared VPS Nginx Options
- **Discovery:** Sites on this VPS must inherit global SSL options from `/etc/nginx/conf.d/` rather than defining redundant `ssl_protocols` or ciphers locally. Doing so triggers Nginx startup warnings.

---

## 4. Completed Tasks Log

| Task | Date | Scope of Files / Commands | Impact |
|---|---|---|---|
| Domain Migration | 2026-06-25 | `deploy-vps.ps1`, `server.py`, `nginx_stockreport.conf` | Updated default redirect URIs to `https://stockreport.tnsai.vn/oauth2callback`. |
| Nginx & SSL Setup | 2026-06-25 | `nginx_stockreport.conf`, `certbot` | Enabled SSL for `stockreport.tnsai.vn`. Cleaned up old `.tech` configurations. |
| Favicon & SEO | 2026-06-25 | `favicon.svg`, `og-image.png`, `robots.txt`, `index.html` | Created SVG favicon and OG image. Added JSON-LD schema metadata. |
| Docs Updates | 2026-06-25 | `/opt/pdf2qmd/docs/ports.md`, other VPS docs | Replaced old domain references across all documentation files on the VPS. |

---

## 5. Active Actions & Next Steps

- **Google Console Registry:** Remind the user to add `https://stockreport.tnsai.vn/oauth2callback` to their Google Developer Console callback whitelist.
- **Monitor Sync Jobs:** Ensure the WebSocket progress updates and Google Sync jobs continue to run successfully on the new domain.
