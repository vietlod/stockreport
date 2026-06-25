# Docker Map — Container Infrastructure & Safety Policies

This document outlines the container topology of other applications on the shared VPS and details why Stock Report is deployed as a non-dockerized host process.

---

## 1. Stock Report - Non-Dockerized Rationale
- **App Deployment Status:** `no docker detected`
- **Technical Rationale:** Headless Playwright (Chromium) requires several native system library packages (X11, GL, fontconfig, etc.). Running Chromium in docker requires either building extremely heavy custom images (~1.5GB to 2GB) or mounting host OS libraries, which is error-prone. Host-level virtual environment execution avoids this virtualization overhead, consumes less CPU/RAM, and runs the chromium scraper reliably.

---

## 2. Shared VPS Docker Topology

Although Stock Report runs directly on the host, other applications share the VPS Docker resources:

| Container Name | Compose File | Shared Network | Volumes / Database |
|---|---|---|---|
| `econdata-postgres` | `/opt/ecodata/docker-compose.yml` | `ecodata-network` | `postgres_data` (User metadata) |
| `econdata-redis` | `/opt/ecodata/docker-compose.yml` | `ecodata-network` | `redis_data` (Cache/Broker) |
| `econdata-neo4j` | `/opt/ecodata/docker-compose.yml` | `ecodata-network` | `neo4j_data` (Knowledge Graph) |
| `pdfhub-frontend` | `/opt/pdfhub/docker-compose.yml` | `pdfhub-network` | Statically built frontend |
| `pdfhub-backend` | `/opt/pdfhub/docker-compose.yml` | `pdfhub-network` | FastAPI backend |
| `fintech-frontend` | `/opt/fintech/docker-compose.yml` | `fintech-network` | React static build |

---

## 3. Strict VPS Docker Rules

> [!CAUTION]
> **No Global Down Operations:**
> Running `docker compose down` or `docker system prune` globally on the VPS host will stop or wipe critical databases and frontends for all client apps (e.g. Ecodata, PDFHub, Fintech).
> - ALWAYS execute commands on a single target container using the explicit docker compose file:
>   ```bash
>   docker compose -f /opt/ecodata/docker-compose.yml restart econdata-redis
>   ```
> - NEVER run docker cleanups without explicit confirmation from the user.
