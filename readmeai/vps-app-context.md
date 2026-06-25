# VPS App Context — Shared Infrastructure & Co-Tenant Map

This document catalogs all applications deployed on the shared VPS `31.97.110.12` to prevent service collisions, port overlaps, and deployment failures.

---

## 1. Co-Tenant Applications Mapping

| Application Name | Public Domain | Host Internal Ports | Absolute Project Path | Process Manager | Nginx Configuration Path |
|---|---|---|---|---|---|
| **Stock Report** | `stockreport.tnsai.vn` | `8002` (FastAPI) | `/opt/stockreport` | Systemd | `/etc/nginx/sites-available/stockreport.tnsai.vn` |
| **PDF2QMD** | `pdf2qmd.tnsai.vn` | `8770` (Adapter)<br>`8765` (Supertonic) | `/opt/pdf2qmd` | Systemd | `/etc/nginx/sites-available/pdf2qmd.tnsai.vn` |
| **TNS SSO** | `www.tnsai.vn` | `3011` (Frontend)<br>`8009` (Backend - SSO) | `/opt/tnsai/code` | Docker Compose | `/etc/nginx/sites-available/tnsai.vn` |
| **Ecodata** | `ecodata.tnsai.vn` | `3000` (Frontend)<br>`8000` (Backend)<br>`8084` (RMCP) | `/opt/ecodata` | Docker Compose | `/etc/nginx/sites-available/ecodata.tnsai.vn` |
| **PDFHub** | `pdfhub.tnsai.vn` | `3008` (Frontend)<br>`8007` (Backend) | `/opt/pdfhub` | Docker Compose | `/etc/nginx/sites-available/pdfhub.tnsai.vn` |
| **Fintech** | `fintech.tnsai.vn` | `3016` (Frontend)<br>`8010` (Backend) | `/opt/fintech` | Docker Compose | `/etc/nginx/sites-available/fintech.tnsai.vn` |
| **Marketplace**| `UNKNOWN` | `3015` | `/opt/marketplace` | Docker Compose | `UNKNOWN` |
| **Bodulieu** | `UNKNOWN` | `3014` | `/opt/bodulieu` | Docker Compose | `UNKNOWN` |
| **Wordpress** | `vietlod.com` | `3012` | `/opt/wordpress-vietlod` | Docker Compose | `UNKNOWN` |
| | `sachktl.com` | `3013` | `/opt/wordpress-sachktl` | Docker Compose | `UNKNOWN` |
| **Ollama** | `UNKNOWN` | `11435` | `/opt/ollama` | Docker Compose | `UNKNOWN` |

---

## 2. Infrastructure Guardrails

1. **Port Guard:** Do NOT bind any service to ports `3000`, `3008`, `3011-3016`, `5432-5436`, `6379-6382`, `7474`, `7687`, `8000`, `8002`, `8007`, `8010`, `8084`, `8765`, `8770`, or `11435` to prevent port collisions.
2. **Never use `docker compose down`** or `docker system prune` globally. Work only on single containers (e.g. `docker compose restart <service>`) using explicit yaml files.
3. **Nginx Warning:** Check Nginx configuration syntax with `nginx -t` before reloads. Avoid duplicate configuration parameters (e.g. `ssl_protocols`) that trigger upstream overrides.
4. **Log paths:** Direct log diagnostics to specific paths instead of dumping into generic syslog spaces.
