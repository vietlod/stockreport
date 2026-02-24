# ECODATA VPS Infrastructure

**Domain:** ecodata.khoviet.com
**VPS IP:** 212.85.24.158
**OS:** Ubuntu (Docker-based deployment)
**SSL:** Let's Encrypt (TLSv1.2 + TLSv1.3)
**Last Updated:** 2026-02-11

---

## 1. Tong Quan Kien Truc

```
Internet
  |
  v
Nginx (VPS host) :443 SSL
  |
  +-- /api/*  /auth/*  /payments/*  /health  /exports/*  /admin/(users|tiers|statistics|data/)
  |       --> Backend (FastAPI) :8000
  |
  +-- /docs/*
  |       --> Frontend :3000 --> Docs container :80
  |
  +-- /* (all other)
          --> Frontend (React SPA) :3000
```

**Docker Network:** `econdata-network` (bridge)
**Compose prefix:** `ecodata_` --> network thuc te: `ecodata_econdata-network`

---

## 2. Bang Tong Hop Cac Service

| # | Service | Container Name | Image/Build | Port (host:container) | Tech Stack | Health Check |
|---|---------|---------------|-------------|----------------------|------------|-------------|
| 1 | **PostgreSQL** | `econdata-postgres` | `postgres:15-alpine` | `5432:5432` | PostgreSQL 15, asyncpg | `pg_isready` |
| 2 | **Redis** | `econdata-redis` | `redis:7-alpine` | `6379:6379` | Redis 7, AOF persistence | `redis-cli ping` |
| 3 | **Neo4j** | `econdata-neo4j` | `neo4j:5-community` | `7474:7474`, `7687:7687` | Neo4j 5 + APOC plugin | `wget http://localhost:7474` |
| 4 | **Backend API** | `econdata-backend` | `python:3.11-slim` | `8000:8000` | FastAPI + Uvicorn | `curl http://localhost:8000/health` |
| 5 | **Celery Worker** | `econdata-celery-worker` | `python:3.11-slim` | (no port) | Celery 5.6, concurrency=2 | `celery inspect ping` |
| 6 | **Python Service** | `econdata-python-service` | `python:3.11-slim` | `5000:5000` | FastAPI (PDF/OCR) | `curl http://localhost:5000/health` |
| 7 | **VNPay Adapter** | `econdata-adapter` | `node:18-alpine` | `4000:4000` | Express.js 4.19 | `http://localhost:4000/healthz` |
| 8 | **Frontend** | `econdata-frontend` | `node:20-alpine` + `nginx:alpine` | `3000:80` | React 19 + Vite 6.2 | `curl http://localhost:80` |
| 9 | **Docs** | `econdata-docs` | `nginx` | (internal :80 only) | Docusaurus 3.9 | `curl http://localhost/` |

### Stock Market Stack (Rieng biet - docker-compose.stock.yml)

| # | Service | Container Name | Port (host:container) | Tech Stack |
|---|---------|---------------|----------------------|------------|
| 10 | **Stock PostgreSQL** | `stock-postgres` | `5432:5432` | PostgreSQL 15 (DB: stockmarket) |
| 11 | **Stock API** | `stock-api` | `8001:8001` | Python + Vnstock |

---

## 3. Chi Tiet Tung Service

### 3.1 PostgreSQL (Database chinh)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Image | `postgres:15-alpine` |
| Port | `5432:5432` |
| Database | `ecodata` |
| User | `ecodata_user` |
| Volume | `postgres_data:/var/lib/postgresql/data` |
| Driver | asyncpg (async) |
| Restart | `unless-stopped` |

**Luu tru:** Users, indicators, payments, metadata, financial data

---

### 3.2 Redis (Cache & Message Broker)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Image | `redis:7-alpine` |
| Port | `6379:6379` |
| Persistence | AOF (`--appendonly yes`) |
| Volume | `redis_data:/data` |
| Restart | `unless-stopped` |

**Vai tro:** Cache API responses, Celery broker, Celery result backend, session storage

---

### 3.3 Neo4j (Knowledge Graph)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Image | `neo4j:5-community` |
| Ports | `7474:7474` (HTTP), `7687:7687` (Bolt) |
| Plugins | APOC |
| Heap | 512MB init, 1GB max |
| Volumes | `neo4j_data:/data`, `neo4j_logs:/logs` |
| Restart | `unless-stopped` |

**Vai tro:** Document knowledge graph, relationship mapping

---

### 3.4 Backend API (FastAPI)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Base Image | `python:3.11-slim` |
| Framework | FastAPI + Uvicorn |
| Port | `8000:8000` |
| Command | `uvicorn main:app --host 0.0.0.0 --port 8000` |
| Volumes | `./backend:/app`, `backend_uploads:/app/uploads`, `backend_exports:/app/exports` |
| Depends on | postgres, redis, adapter, neo4j (all healthy) |

**API Endpoints chinh:**
- `/api/*` - RESTful API
- `/auth/*` - Authentication (JWT)
- `/admin/*` - Admin management
- `/payments/*` - VNPay integration
- `/exports/*` - File downloads
- `/health` - Health check

**Tech Stack Backend:**
| Library | Version | Vai tro |
|---------|---------|---------|
| FastAPI | 0.123+ | Web framework |
| Uvicorn | 0.38+ | ASGI server |
| SQLAlchemy | 2.0+ | ORM |
| asyncpg | 0.31+ | Async PostgreSQL |
| Pydantic | 2.12+ | Validation |
| Celery | 5.6+ | Task queue |
| Pandas | 2.2+ | Data processing |
| NumPy | 2.1+ | Numerical computing |
| SciPy | 1.11+ | Scientific computing |
| Statsmodels | 0.14+ | Econometrics |
| LinearModels | 5.3+ | Panel regression |
| PyArrow | 18+ | Parquet support |
| Plotly | 5.18+ | Visualizations |

**AI/LLM Providers:**
| Provider | Model | SDK |
|----------|-------|-----|
| Anthropic (primary) | claude-3-haiku-20240307 | anthropic SDK |
| OpenRouter | gemini-2.5-flash | REST API |
| DeepSeek | deepseek-chat | REST API |
| Ollama (local) | llama3.2:3b | HTTP API |

**Rate Limits (Chat):**
| Membership | Limit |
|-----------|-------|
| FREE | 10 msg/hour |
| PREMIUM | 100 msg/hour |
| PREMIUM_PLUS | 500 msg/hour |

---

### 3.5 Celery Worker

| Thuoc tinh | Gia tri |
|-----------|---------|
| Base Image | Same as backend |
| Command | `celery -A celery_app worker --loglevel=info --concurrency=2` |
| Concurrency | 2 processes |
| Broker | Redis (redis://redis:6379/0) |
| Result Backend | Redis |
| Depends on | postgres, redis (healthy) |

**Vai tro:** Background data ingestion, export generation, batch processing

---

### 3.6 Python Service (PDF Processing)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Base Image | `python:3.11-slim` |
| Port | `5000:5000` |
| Command | `uvicorn main:app --host 0.0.0.0 --port 5000` |
| Volumes | `./python-service:/app`, `./tucode:/app/tucode:ro`, `python_service_data:/app/data` |

**Vai tro:** PDF extraction, table parsing, OCR
**Libraries:** PyMuPDF, pdfplumber, camelot-py, OpenCV, Pillow

---

### 3.7 VNPay Adapter

| Thuoc tinh | Gia tri |
|-----------|---------|
| Base Image | `node:18-alpine` |
| Framework | Express.js 4.19 |
| Port | `4000:4000` |
| Command | `node ./bin/www` |
| Security | Helmet, CORS, shared secret |

**Vai tro:** Payment gateway - sign VNPay URLs, validate IPN callbacks
**VNPay Config:** Sandbox mode, VND currency, locale=vn

**Dependencies:**
| Package | Version |
|---------|---------|
| express | 4.19.2 |
| cors | 2.8.5 |
| helmet | 7.1.0 |
| morgan | 1.10.0 |
| node-fetch | 2.6.9 |
| dotenv | 16.4.5 |

---

### 3.8 Frontend (React SPA)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Build Image | `node:20-alpine` |
| Runtime Image | `nginx:alpine` |
| Port | `3000:80` |
| Build Output | `/usr/share/nginx/html` |
| Depends on | backend, docs |

**Frontend Tech Stack:**
| Library | Version | Vai tro |
|---------|---------|---------|
| React | 19.2 | UI framework |
| TypeScript | 5.8+ | Type safety |
| Vite | 6.2 | Build tool |
| React Router | 7.9 | Routing |
| react-i18next | 16.3 | i18n (EN/VI) |
| i18next | 25.6 | i18n core |
| Chart.js | 4.5 | Charts |
| react-chartjs-2 | 5.3 | Chart components |
| react-markdown | 9.1 | Markdown render |
| react-dropzone | 14.3 | File upload |
| @react-oauth/google | 0.12 | Google login |
| lucide-react | - | Icons |

**Nginx Frontend Config** (`nginx.conf`):
- Gzip compression enabled
- Static assets cached 1 year (`Cache-Control: public, immutable`)
- `/api`, `/auth`, `/payments`, `/exports` --> proxy to `backend:8000`
- `/admin/(users|tiers|statistics|data/)` --> proxy to `backend:8000`
- `/docs` --> proxy to `docs:80`
- `/*` --> `try_files $uri $uri/ /index.html` (SPA routing)

---

### 3.9 Documentation (Docusaurus)

| Thuoc tinh | Gia tri |
|-----------|---------|
| Runtime | nginx |
| Port | Internal :80 only (no host mapping) |
| Framework | Docusaurus 3.9 |
| Access | Via `/docs` route on frontend |

**Dependencies:** @docusaurus/core 3.9, OpenAPI docs plugin, Mermaid diagrams

---

## 4. Nginx VPS Host Configuration

**File:** `/etc/nginx/sites-available/ecodata.khoviet.com`
**Source:** [scripts/deployment/nginx_ecodata.conf](scripts/deployment/nginx_ecodata.conf)

### Routing Table

| Route | Proxy Target | Port | Muc dich |
|-------|-------------|------|----------|
| `/api/*` | `127.0.0.1:8000` | Backend | REST API |
| `/auth/*` | `127.0.0.1:8000` | Backend | Authentication |
| `/admin/users` | `127.0.0.1:8000` | Backend | User management |
| `/admin/roles` | `127.0.0.1:8000` | Backend | Role management |
| `/admin/memberships` | `127.0.0.1:8000` | Backend | Subscription management |
| `/admin/logs` | `127.0.0.1:8000` | Backend | Admin logs |
| `/admin/data/*` | `127.0.0.1:8000` | Backend | Data upload/management |
| `/payments/*` | `127.0.0.1:8000` | Backend | Payment processing |
| `/health` | `127.0.0.1:8000` | Backend | Health check |
| `/docs` | `127.0.0.1:3000` | Frontend -> Docs | Documentation |
| `/*` | `127.0.0.1:3000` | Frontend | React SPA |

### SSL/Security

| Config | Gia tri |
|--------|---------|
| Protocols | TLSv1.2, TLSv1.3 |
| Certificate | Let's Encrypt |
| HSTS | 31536000s (1 year) |
| X-Frame-Options | SAMEORIGIN |
| X-Content-Type-Options | nosniff |
| X-XSS-Protection | 1; mode=block |
| HTTP -> HTTPS | Redirect 301 |
| Proxy timeout | 300s |

---

## 5. Docker Volumes

| Volume | Mount Path | Vai tro |
|--------|-----------|---------|
| `postgres_data` | `/var/lib/postgresql/data` | Database persistence |
| `redis_data` | `/data` | Cache + queue persistence |
| `neo4j_data` | `/data` | Graph database data |
| `neo4j_logs` | `/logs` | Graph database logs |
| `backend_uploads` | `/app/uploads` | User file uploads |
| `backend_exports` | `/app/exports` | Export files (CSV/Excel/Parquet) |
| `python_service_data` | `/app/data` | PDF processing cache |

---

## 6. Docker Compose Files

| File | Muc dich | Services |
|------|----------|----------|
| `docker-compose.production.yml` | Production (VPS) | 9 services (full stack) |
| `docker-compose.local.yml` | Local dev | 2 services (postgres + redis) |
| `docker-compose.stock.yml` | Stock market | 2 services (stock-postgres + stock-api) |

---

## 7. Environment Files

| File | Muc dich |
|------|----------|
| `.env` | Local development |
| `.env.production` | Production (VPS) |
| `.env.example` | Template |

### Bien Moi Truong Quan Trong

```
# Database
DATABASE_URL=postgresql+asyncpg://ecodata_user:***@postgres:5432/ecodata

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Security
SECRET_KEY=***  (min 32 chars)
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_MIN=129600  (90 ngay)
JWT_REFRESH_TTL_DAYS=30

# Payment
PAYMENT_ADAPTER_BASE_URL=http://adapter:4000
FASTAPI_SHARED_SECRET=***

# Data Source API Keys
WB_API_KEY, IMF_API_KEY, FRED_API_KEY, WTO_API_KEY,
UNCTAD_CLIENT_ID, UNCTAD_API_KEY, SAMADB_TOKEN, UN_API_KEY

# AI/LLM
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=***
OPENROUTER_API_KEY=***
DEEPSEEK_API_KEY=***

# Neo4j
NEO4J_URI=bolt://neo4j:7687
```

---

## 8. Dependency Graph

```
                    +-----------+
                    |  Nginx    |
                    |  (VPS)    |
                    +-----+-----+
                          |
            +-------------+-------------+
            |                           |
      +-----v-----+             +------v------+
      | Frontend   |             | Backend     |
      | :3000 (80) |             | :8000       |
      +-----+------+             +------+------+
            |                           |
      +-----v-----+         +----------+----------+
      | Docs       |         |          |          |
      | :80        |   +-----v----+ +---v----+ +--v-----+
      +------------+   | Postgres | | Redis  | | Neo4j  |
                       | :5432    | | :6379  | | :7687  |
                       +----------+ +--------+ +--------+
                                        |
                                  +-----v--------+
                                  | Celery Worker |
                                  +--------------+

      +----------------+     +------------------+
      | Python Service |     | VNPay Adapter    |
      | :5000          |     | :4000            |
      +----------------+     +------------------+
```

---

## 9. Cac Lenh Thuong Dung

### Khoi dong / Dung

```bash
# Start all services (production)
docker-compose -f docker-compose.production.yml up -d

# Start specific service
docker-compose -f docker-compose.production.yml up -d backend

# Restart a service
docker-compose -f docker-compose.production.yml restart backend

# Xem logs
docker-compose -f docker-compose.production.yml logs -f backend

# KHONG dung docker-compose down (se stop TAT CA services)
```

### Health Check

```bash
# Backend API
curl https://ecodata.khoviet.com/health

# Kiem tra tat ca containers
docker ps -a | grep econdata

# Kiem tra PostgreSQL
docker exec econdata-postgres pg_isready -U ecodata_user

# Kiem tra Redis
docker exec econdata-redis redis-cli ping

# Kiem tra Neo4j
curl http://localhost:7474
```

### Troubleshooting

```bash
# Login tra ve 500 -> Kiem tra DB containers
docker ps -a | grep econdata

# Name resolution error -> Database container down
docker start econdata-postgres econdata-redis

# Frontend khong load -> Can docs container
docker start econdata-docs

# Rebuild khong cache
docker-compose -f docker-compose.production.yml build --no-cache frontend
```

---

## 10. Luu Y Quan Trong

1. **Docker-compose v1 (1.29.2)** co bug `ContainerConfig` KeyError khi metadata bi corrupt. Workaround: dung `docker run` truc tiep
2. **KHONG BAO GIO** dung `docker-compose down` - se stop tat ca services ke ca app khac
3. **Frontend** can `docs` container chay (upstream trong nginx.conf cho route `/docs`)
4. **Network name** thuc te la `ecodata_econdata-network` (co prefix project name)
5. **Port 3000:80** - nginx tren VPS proxy 443 -> 3000 (frontend container listen port 80)
