# CLAUDE.md - AI Assistant Guide for KDMS

**Last Updated:** 2025-11-27
**Version:** 7.0 (Phase 8 - KRX Market Cap Integration)
**Project:** KDMS (Korea Data Management System)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Architecture](#architecture)
4. [Directory Structure](#directory-structure)
5. [Development Workflows](#development-workflows)
6. [Database Schema & Patterns](#database-schema--patterns)
7. [API Structure](#api-structure)
8. [Key Conventions](#key-conventions)
9. [Common Tasks](#common-tasks)
10. [Testing & Deployment](#testing--deployment)
11. [Important Notes for AI Assistants](#important-notes-for-ai-assistants)

---

## Project Overview

**KDMS** is a production-ready full-stack Korean stock market data platform that collects, manages, and analyzes KOSPI/KOSDAQ market data.

### Purpose
- Collect daily and minute-level OHLCV data for Korean stocks
- Collect market capitalization and listed shares data via pykrx
- Manage financial statements and ratios with Point-in-Time (PIT) versioning
- Provide real-time data quality monitoring and gap detection
- Support quantitative screening strategies (magic formula style)
- Track data collection reliability through system milestones

### Key Features
- **Admin Dashboard**: Real-time task monitoring with WebSocket log streaming
- **Data Collection**: Automated daily updates, financial data, market cap, and minute-level backfills
- **Data Quality**: Freshness metrics, gap detection, and milestone tracking
- **API Services**: RESTful endpoints with Apache Arrow support for performance
- **Scheduling**: APScheduler-based cron jobs with manual execution support

---

## Technology Stack

### Backend
```yaml
Framework: FastAPI 0.121.1
Server: Uvicorn 0.38.0 (ASGI, async)
Language: Python 3.12
Database Driver: psycopg2-binary 2.9.11
Data Processing: Pandas 2.3.3, NumPy 2.0.2, PyArrow 22.0.0
Scheduler: APScheduler 3.11.0 (AsyncIOScheduler)
APIs: Kiwoom REST, KIS REST (Korean brokerage APIs), pykrx 1.0.46+ (KRX data)
Logging: Rich 14.2.0 with WebSocket support
Testing: pytest 8.4.2
Environment: python-dotenv 1.1.1
```

### Frontend
```yaml
Framework: Vue 3.5.22
Language: TypeScript 5.9
Build Tool: Vite 7.1.11
State Management: Pinia 3.0.3
Routing: Vue Router 4.6.3
HTTP Client: Axios 1.13.2 (180s timeout)
Charts: Chart.js 4.5.1 + vue-chartjs 5.3.3
Linting: ESLint 9.37.0
Formatting: Prettier 3.6.2
Node Version: 20.19+ or 22.12+
```

### Database
```yaml
RDBMS: TimescaleDB (PostgreSQL 16)
Features: Hypertables for time-series optimization
Connection Pooling: ThreadedConnectionPool (5-20 connections)
Max Connections: 100
Timezone: Asia/Seoul
```

### Infrastructure
```yaml
Containerization: Docker + Docker Compose
Web Server: Nginx 1.25 (reverse proxy + static files)
Network: Docker bridge (kdms-net)
Ports:
  - 80: Frontend (Nginx)
  - 8000: Backend (FastAPI) [internal]
  - 5432: Database (PostgreSQL)
```

---

## Architecture

### System Architecture
```
┌─────────────────┐
│   Nginx (80)    │ ← HTTP/WS Requests
└────────┬────────┘
         │
    ┌────▼─────┐
    │  Vue 3   │ (SPA, Frontend)
    │Frontend  │
    └────┬─────┘
         │ /api/* proxy
    ┌────▼─────────┐
    │   FastAPI    │ (Backend, Port 8000)
    │   Uvicorn    │
    └────┬─────────┘
         │
    ┌────▼──────────┐
    │ TimescaleDB   │ (PostgreSQL 16)
    │  (Port 5432)  │
    └───────────────┘
```

### Asynchronous Task Processing
- **Scheduler**: APScheduler `AsyncIOScheduler` (NOT `BackgroundScheduler`)
- **Execution Model**: Tasks run in scheduler's thread pool, not FastAPI event loop
- **State Management**: Global `job_statuses` dict tracks task progress
- **Real-time Updates**: WebSocket log streaming via `log_queue`

### Scheduled Jobs
```python
daily_update:          Mon-Fri 17:10 (after market close)
financial_update:      Sat 09:00 (weekly)
backfill_minute_data:  Sat 10:20 (weekly, includes market cap gap recovery)
```

### Data Flow Pattern
```
API Clients (Kiwoom/KIS/pykrx)
    ↓
Collectors (kis_rest.py, kiwoom_rest.py, krx_loader.py)
    ↓
Tasks (daily_task.py, financial_task.py, backfill_task.py)
    ↓
DatabaseManager (db_manager.py) → ConnectionPool
    ↓
TimescaleDB (Hypertables)
```

---

## Directory Structure

```
/home/user/nf_p01_kdms/
│
├── backend/                          # Python FastAPI backend
│   ├── main.py                       # App entry point, scheduler setup, lifespan events
│   ├── requirements.txt              # Python dependencies (58 packages)
│   ├── backend.Dockerfile            # Backend container (Python 3.12-slim)
│   │
│   ├── routers/                      # API endpoints (FastAPI routers)
│   │   ├── admin.py (243 lines)      # Task execution, scheduling, WebSocket logs
│   │   ├── data.py (596 lines)       # Stock/OHLCV/financial data queries, Arrow support
│   │   └── health.py (370 lines)     # Data freshness, gaps, milestones
│   │
│   ├── models/                       # Pydantic data models
│   │   ├── admin_models.py           # TaskRunRequest, ScheduleCreateRequest, ScheduleUpdateRequest
│   │   └── data_models.py            # Stock, OHLCV, Financial, Factor models
│   │
│   ├── tasks/                        # Background job implementations
│   │   ├── daily_task.py (600+ lines)     # Daily OHLCV + factor + market cap sync (Phase 5/5)
│   │   ├── financial_task.py (299 lines)  # PIT financial data updates
│   │   └── backfill_task.py (540+ lines)  # Historical minute data backfill + market cap gap recovery
│   │
│   ├── collectors/                   # Data source integrations (5200+ lines total)
│   │   ├── db_manager.py (940+ lines)     # PostgreSQL connection pooling, queries, market cap methods
│   │   ├── kis_rest.py (740 lines)        # KIS API client with token caching
│   │   ├── kiwoom_rest.py (400 lines)     # Kiwoom API client with auto token refresh
│   │   ├── krx_loader.py (90 lines)       # pykrx-based market cap collector (NEW)
│   │   ├── utils.py (303 lines)           # Date, market, formatting utilities
│   │   ├── factor_calculator.py           # Price adjustment factor calculations
│   │   ├── target_selector.py             # Select top stocks for minute data
│   │   └── exceptions.py                  # Custom exceptions (TokenAuthError, etc.)
│   │
│   ├── config/                       # Database configuration
│   │   ├── postgresql.conf           # TimescaleDB tuning, logging, memory settings
│   │   └── pg_hba.conf              # Connection authentication rules
│   │
│   ├── init/                         # Database initialization
│   │   └── init.sql (279 lines)      # Schema, hypertables, indexes, milestones
│   │
│   ├── log_utils.py                  # WebSocket logging setup, PollingLogFilter
│   └── test_utils.py                 # Test environment helpers
│
├── frontend/                         # Vue 3 TypeScript SPA
│   ├── package.json                  # npm dependencies (Vue 3, Vite, Pinia)
│   ├── vite.config.ts                # Dev server, API proxy to backend:8000
│   ├── eslint.config.ts              # Vue + TypeScript linting rules
│   ├── tsconfig.json                 # TypeScript compiler options
│   ├── frontend.Dockerfile           # Multi-stage: npm build → nginx serve
│   │
│   └── src/
│       ├── main.ts                   # App initialization
│       ├── App.vue                   # Root component
│       │
│       ├── router/
│       │   └── index.ts              # Routes: Dashboard, Health, Explorer, Schedules
│       │
│       ├── views/ (681 lines)        # Page components
│       │   ├── DashboardView.vue     # Task status, log terminal, quick actions
│       │   ├── ScheduleView.vue      # Schedule management UI
│       │   ├── HealthView.vue        # Data freshness, gaps, milestones
│       │   └── DataExplorerView.vue  # Table preview with filters
│       │
│       ├── stores/ (Pinia)
│       │   ├── adminStore.ts (159 lines)   # Task status polling, WebSocket logs
│       │   ├── dataStore.ts (44 lines)     # Table preview data
│       │   └── healthStore.ts (70 lines)   # Health metrics
│       │
│       ├── components/
│       │   ├── layout/
│       │   │   ├── MainLayout.vue    # Header + sidebar + router-view
│       │   │   ├── AppHeader.vue     # Navigation bar
│       │   │   └── AppSidebar.vue    # Menu (Dashboard, Health, Explorer, Schedules)
│       │   │
│       │   ├── dashboard/
│       │   │   ├── TaskStatusCard.vue     # Task status, progress, next run
│       │   │   └── LogTerminal.vue        # Real-time log display (WebSocket)
│       │   │
│       │   ├── health/
│       │   │   ├── StatCard.vue           # Health metrics display
│       │   │   ├── GapInspector.vue       # Missing data visualization
│       │   │   ├── MilestoneTimeline.vue  # Timeline of milestones
│       │   │   └── MilestoneModal.vue     # Create milestone dialog
│       │   │
│       │   └── schedule/
│       │       └── ScheduleModal.vue      # Create/edit schedule dialog
│       │
│       ├── types/ (TypeScript interfaces)
│       │   ├── admin.ts              # TaskStatus, JobStatuses, ScheduleItem
│       │   ├── data.ts               # Stock, OHLCV, Financial types
│       │   └── health.ts             # Freshness, gaps, milestones
│       │
│       └── api/
│           └── http.ts               # Axios instance with /api/* proxy
│
├── docker-compose.yml                # Multi-container orchestration (db, backend, frontend)
├── nginx.conf                        # Frontend static + API/WebSocket proxy
├── .gitignore                        # Python, Node, IDE, logs, secrets
├── .env                              # [GITIGNORED] DB credentials, API keys
│
├── standalone_scripts/               # Utility/backfill scripts
│   ├── backfill_krx_market_cap.py    # Smart market cap backfill (DB MAX(dt) detection) (NEW)
│   ├── initial_build.py (24KB)       # Bootstrap: master, daily OHLCV, factors
│   ├── backfill_minute_data.py (20KB)# Historical minute data collection
│   ├── daily_update.py (19KB)        # Legacy standalone daily update
│   ├── financial_update.py (10KB)    # Legacy standalone financial update
│   ├── verify_backfill.py (14KB)     # Data integrity verification
│   ├── truncate_financials.py        # Admin: clear financial data
│   └── main_collection.py (60KB)     # Comprehensive data collection orchestrator
│
└── logs/ backups/                    # Runtime logs, DB backups (Docker volumes)
```

### Key File Locations

| Purpose | Location |
|---------|----------|
| **API Entry Point** | `main.py:110` |
| **Task Execution** | `routers/admin.py:54` |
| **Data Queries** | `routers/data.py` |
| **Health Metrics** | `routers/health.py` |
| **Daily Job** | `tasks/daily_task.py:run_daily_update` |
| **Financial Job** | `tasks/financial_task.py:run_financial_update` |
| **Backfill Job** | `tasks/backfill_task.py:run_backfill_minute_data` |
| **Market Cap Gap Recovery** | `tasks/backfill_task.py:_backfill_market_cap_gaps` |
| **DB Connection** | `collectors/db_manager.py:DatabaseManager` |
| **KIS API Client** | `collectors/kis_rest.py:KISRestClient` |
| **Kiwoom API Client** | `collectors/kiwoom_rest.py:KiwoomRestClient` |
| **KRX Market Cap Loader** | `collectors/krx_loader.py:KRXLoader` |
| **Market Cap Backfill Script** | `standalone_scripts/backfill_krx_market_cap.py` |
| **Schema Init** | `init/init.sql` |
| **Frontend Entry** | `frontend/src/main.ts` |
| **API Proxy Config** | `frontend/vite.config.ts:18` |

---

## Development Workflows

### Local Development Setup

#### 1. Start Database
```bash
docker-compose up db -d
```

#### 2. Start Backend (Hot Reload)
```bash
# Set up environment
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
# (add other .env variables)

# Run with hot reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. Start Frontend (Dev Server)
```bash
cd frontend
npm install
npm run dev
# Vite dev server: http://localhost:5173
# API proxy: /api/* → http://127.0.0.1:8000
```

### Production Deployment

```bash
# Build and start all services
docker-compose build
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Access application
# Frontend: http://localhost
# Backend API: http://localhost/api (proxied via Nginx)
```

### Git Workflow

**Current Branch**: `claude/claude-md-mif9zuhkv26mywes-01SEcjN2r6tMkvVqH8MdC2C4`

```bash
# Commit changes
git add .
git commit -m "$(cat <<'EOF'
feat: Add new feature

- Detailed description
- Breaking changes if any
EOF
)"

# Push to feature branch
git push -u origin claude/claude-md-mif9zuhkv26mywes-01SEcjN2r6tMkvVqH8MdC2C4

# IMPORTANT: Branch must start with 'claude/' for successful push
```

**Commit Message Convention**:
- `feat:` - New feature
- `fix:` - Bug fix
- `chore:` - Maintenance, dependencies, config
- `docs:` - Documentation
- `refactor:` - Code restructuring

**Recent Commits**:
- `171a67c` fix: Improve API response validation logic and update defaults
- `4fdd128` feat: Add KRX market cap data collection with pykrx
- `fa434da` refactor: Extract duplicate token refresh logic into helper method
- `7e67da2` feat: Add Kiwoom API token auto-refresh and fail-fast error handling

---

## Database Schema & Patterns

### Core Tables

#### 1. **stock_info** - Stock Master Data
```sql
PRIMARY KEY: stk_cd (VARCHAR(6))
Fields: stk_nm, market_type, status, delist_dt, list_dt, m_vol, cap, update_dt
Purpose: KOSPI/KOSDAQ stock list (including delisted)
```

#### 2. **daily_ohlcv** - Daily Price Data (Hypertable)
```sql
PRIMARY KEY: (dt, stk_cd)
Partitioned By: dt (TimescaleDB hypertable)
Fields: open_prc, high_prc, low_prc, cls_prc, vol, amt, turn_rt
Purpose: Raw daily OHLCV data (not adjusted)
```

#### 3. **minute_ohlcv** - Minute Price Data (Hypertable)
```sql
PRIMARY KEY: (dt_tm, stk_cd)
Partitioned By: dt_tm (TimescaleDB hypertable)
Fields: open_prc, high_prc, low_prc, cls_prc, vol
Purpose: 1-minute OHLCV for selected high-volume stocks
```

#### 4. **price_adjustment_factors** - Adjustment Factors (PIT)
```sql
PRIMARY KEY: id (BIGSERIAL)
Unique Constraint: (stk_cd, event_dt, price_source)
Fields:
  - event_dt: Date when stock split/dividend occurred
  - price_ratio: Price adjustment multiplier
  - volume_ratio: Volume adjustment multiplier
  - price_source: Data source (KIWOOM, KIS)
  - effective_dt: When this factor was recorded (PIT tracking)
Purpose: Calculate adjusted prices from raw data
```

#### 5. **financial_statements** - Balance Sheet & Income Statement (PIT)
```sql
PRIMARY KEY: id (BIGSERIAL)
Index: (stk_cd, stac_yymm, div_cls_code, retrieved_at DESC)
Fields:
  - retrieved_at: When this version was collected (PIT)
  - stac_yymm: Fiscal period (YYYYMM)
  - div_cls_code: '0' (annual) or '1' (quarterly)
  - BS: cras, fxas, total_aset, flow_lblt, fix_lblt, total_lblt, cpfn, total_cptl
  - IS: sale_account, sale_cost, sale_totl_prfi, bsop_prti, op_prfi, thtr_ntin
Purpose: Financial statements with version control for screening
```

#### 6. **financial_ratios** - Financial Ratios (PIT)
```sql
PRIMARY KEY: id (BIGSERIAL)
Index: (stk_cd, stac_yymm, div_cls_code, retrieved_at DESC)
Fields:
  - Profitability: roe_val, cptl_ntin_rate, sale_ntin_rate
  - Growth: grs, bsop_prfi_inrt, ntin_inrt, equt_inrt, totl_aset_inrt
  - Stability: lblt_rate, crnt_rate, quck_rate, bram_depn
  - Valuation: eps, bps, sps, rsrv_rate
  - Other: eva, ebitda, ev_ebitda
Purpose: Financial ratios with PIT versioning
```

#### 7. **system_milestones** - Data Reliability Events
```sql
PRIMARY KEY: milestone_name
Fields: milestone_date, description, updated_at
Purpose: Track data collection reliability events
Example: 'SYSTEM:SCHEMA:CREATED', 'DATA:DAILY:COMPLETE:2024-01-01'
```

#### 8. **minute_target_history** - Minute Data Collection Targets
```sql
PRIMARY KEY: (quarter, market, symbol)
Fields: quarter (2024Q1), market (KOSPI/KOSDAQ), avg_trade_value, rank
Purpose: Track which stocks are selected for minute data collection each quarter
```

#### 9. **daily_market_cap** - Market Capitalization Data (Hypertable)
```sql
PRIMARY KEY: (dt, stk_cd)
Partitioned By: dt (TimescaleDB hypertable)
Fields: cls_prc, mkt_cap, vol, amt, listed_shares
Purpose: Daily market cap and listed shares from pykrx
Data Source: pykrx.stock.get_market_cap_by_ticker()
Collection: Daily at 17:10 (Phase 5/5), Weekly gap recovery (last 30 days)
Index: idx_daily_market_cap_stk_cd_dt (stk_cd, dt DESC)
```

### Point-in-Time (PIT) Pattern

**Problem**: Financial data gets revised over time. Using latest data introduces look-ahead bias in backtesting.

**Solution**: Store `retrieved_at` timestamp for each version. Query data as it appeared at a specific point in time.

**Example**:
```sql
-- Get Samsung (005930) Q4 2023 financials as of 2024-01-15
SELECT * FROM financial_statements
WHERE stk_cd = '005930'
  AND stac_yymm = '202312'
  AND div_cls_code = '0'
  AND retrieved_at <= '2024-01-15 23:59:59+09'
ORDER BY retrieved_at DESC
LIMIT 1;
```

### Connection Pooling Pattern

```python
# collectors/db_manager.py
class DatabaseManager:
    def __init__(self):
        self.pool = ThreadedConnectionPool(
            minconn=5,
            maxconn=20,
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        )

    def get_connection(self):
        return self.pool.getconn()

    def put_connection(self, conn):
        self.pool.putconn(conn)
```

**Usage**:
```python
conn = db_manager.get_connection()
try:
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM stock_info WHERE status = 'listed'")
    results = cursor.fetchall()
finally:
    db_manager.put_connection(conn)
```

---

## API Structure

### Endpoint Organization

| Prefix | Router | Purpose |
|--------|--------|---------|
| `/api/v1/admin` | `admin.py` | Task execution, scheduling, WebSocket logs |
| `/api/v1/data` | `data.py` | Stock/OHLCV/financial data queries |
| `/api/v1/health` | `health.py` | Data freshness, gaps, milestones |

### Admin Endpoints (`/api/v1/admin`)

```
GET    /tasks/status                    # Get all task statuses
POST   /tasks/{task_id}/run             # Execute task manually
GET    /jobs                            # List all scheduled jobs
POST   /jobs                            # Create new schedule
PUT    /jobs/{job_id}                   # Update schedule
DELETE /jobs/{job_id}                   # Delete schedule
POST   /jobs/{job_id}/pause             # Pause schedule
POST   /jobs/{job_id}/resume            # Resume schedule
WS     /logs/ws                         # WebSocket log streaming
```

**Task IDs**:
- `daily_update`: Daily OHLCV + factor sync
- `financial_update`: PIT financial data updates
- `backfill_minute_data`: Historical minute data backfill

### Data Endpoints (`/api/v1/data`)

```
GET    /stocks                          # List stocks (filter by market, status)
GET    /ohlcv/daily/{stk_cd}            # Daily OHLCV for stock
GET    /ohlcv/minute/{stk_cd}           # Minute OHLCV for stock
GET    /financials/statements           # Financial statements (PIT aware)
GET    /financials/ratios               # Financial ratios (PIT aware)
GET    /financials/screening            # Screening with filters + ranking
GET    /factors/{stk_cd}                # Price adjustment factors
```

**Apache Arrow Support**:
```bash
curl -H "Accept: application/vnd.apache.arrow.stream" \
     http://localhost/api/v1/data/ohlcv/daily/005930
```

### Health Endpoints (`/api/v1/health`)

```
GET    /freshness                       # Data freshness metrics (lag in days)
GET    /gaps/{table_name}               # Detect missing data gaps
GET    /milestones                      # List system milestones
POST   /milestones                      # Create milestone
```

### Response Formats

**Success**:
```json
{
  "data": [...],
  "message": "Success"
}
```

**Error**:
```json
{
  "detail": "Error message",
  "error": "Detailed error string"
}
```

**Status Codes**:
- `200 OK`: Success
- `404 Not Found`: Invalid task_id or resource
- `409 Conflict`: Task already running
- `500 Internal Server Error`: DB pool, scheduler failures

---

## Key Conventions

### Python Code Conventions

1. **Async Functions**: All FastAPI route handlers use `async def`
2. **Scheduler**: Always use `AsyncIOScheduler`, NEVER `BackgroundScheduler`
3. **Comments**: Korean comments for domain-specific terminology
4. **Docstrings**: Reference PRD sections (e.g., `[PRD 3.1.1]`)
5. **Logging**:
   ```python
   logging.info(f"[{task_id}] Task started")
   logging.error(f"[{task_id}] Error: {e}", exc_info=True)
   ```

6. **Error Handling**:
   ```python
   try:
       # operation
   except Exception as e:
       logger.error(f"Operation failed: {e}", exc_info=True)
       raise HTTPException(status_code=500, detail=str(e))
   ```

7. **Database Cursors**: Use `RealDictCursor` for dict-like row access
   ```python
   cursor = conn.cursor(cursor_factory=RealDictCursor)
   ```

### TypeScript/Vue Conventions

1. **Component Naming**: PascalCase (e.g., `TaskStatusCard.vue`)
2. **Composition API**: Use `<script setup lang="ts">`
3. **Type Safety**: Define interfaces in `types/` directory
4. **Store Usage**:
   ```typescript
   import { useAdminStore } from '@/stores/adminStore'
   const adminStore = useAdminStore()
   ```

5. **API Calls**:
   ```typescript
   import http from '@/api/http'
   const response = await http.get<StockInfo[]>('/data/stocks')
   ```

6. **Linting**: Run `npm run lint` before committing
7. **Formatting**: Use Prettier (100 char line length, 2-space indent)

### Environment Variables

**Required** (in `.env` file):
```bash
# Database
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=kdms_db
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# API Credentials (Kiwoom/KIS)
KIWOOM_APP_KEY=xxx
KIWOOM_APP_SECRET=xxx
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=xxx
```

**NEVER commit `.env` to git** - it's in `.gitignore`

### Code Comments Pattern

```python
# --- PRD 4.1.1: Global State Management ---
job_statuses = {
    "daily_update": {"is_running": False, "last_status": "none"},
}

# (신규) Phase 7: WebSocket 로그 스트리밍 큐
log_queue = asyncio.Queue(maxsize=1000)
```

**Comment Types**:
- `# ---`: Section headers
- `# [PRD X.Y.Z]`: PRD document reference
- `# (신규)`: New feature
- `# (수정)`: Modified code
- `# (핵심)`: Critical section

---

## Common Tasks

### 1. Add a New API Endpoint

**Backend** (e.g., in `routers/data.py`):
```python
@router.get("/new-endpoint", summary="Brief description")
async def new_endpoint(param: str = Query(...)):
    """
    [PRD X.Y.Z] Detailed description
    """
    # Implementation
    return {"data": result, "message": "Success"}
```

**Frontend** (e.g., in `stores/dataStore.ts`):
```typescript
async fetchNewData(param: string) {
  const response = await http.get(`/data/new-endpoint?param=${param}`)
  this.newData = response.data.data
}
```

### 2. Add a New Background Task

**Step 1**: Create task function (e.g., `tasks/new_task.py`)
```python
def run_new_task(job_statuses: dict, test_mode: bool = False):
    task_id = "new_task"
    job_statuses[task_id] = {
        "is_running": True,
        "phase": "Starting",
        "progress": 0,
        "start_time": datetime.now().isoformat()
    }

    try:
        # Task logic
        job_statuses[task_id]["phase"] = "Processing"
        job_statuses[task_id]["progress"] = 50

        # Finish
        job_statuses[task_id]["is_running"] = False
        job_statuses[task_id]["progress"] = 100
        job_statuses[task_id]["last_status"] = "success"
    except Exception as e:
        logging.error(f"[{task_id}] Error: {e}", exc_info=True)
        job_statuses[task_id]["is_running"] = False
        job_statuses[task_id]["last_status"] = "error"
```

**Step 2**: Register in `main.py`
```python
from tasks import new_task

# Add to job_statuses
job_statuses["new_task"] = {"is_running": False, "last_status": "none"}

# Add to scheduler (in lifespan function)
scheduler.add_job(
    func=lambda: new_task.run_new_task(job_statuses, test_mode=False),
    trigger='cron',
    day_of_week='mon-fri',
    hour=10,
    minute=0,
    id='new_task_schedule',
    name='new_task'
)
```

**Step 3**: Update `routers/admin.py`
```python
task_map = {
    "daily_update": daily_task.run_daily_update,
    "financial_update": financial_task.run_financial_update,
    "backfill_minute_data": backfill_task.run_backfill_minute_data,
    "new_task": new_task.run_new_task  # Add this
}
```

### 3. Database Migrations

**Current Approach**: Modify `init/init.sql` for schema changes.

**For Existing Databases**:
```sql
-- Apply migration manually
psql -h localhost -U your_user -d kdms_db -f migration.sql
```

**Future**: Consider Alembic for automated migrations.

### 4. Add New Table Preview

**Step 1**: Add database query (in `routers/data.py`)
```python
@router.get("/tables/{table_name}/preview")
async def get_table_preview(table_name: str, limit: int = 100):
    conn = db.get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM {table_name} LIMIT %s", (limit,))
        return {"data": cursor.fetchall()}
    finally:
        db.put_connection(conn)
```

**Step 2**: Update frontend store (`stores/dataStore.ts`)
```typescript
async fetchTablePreview(tableName: string) {
  const response = await http.get(`/data/tables/${tableName}/preview`)
  this.tableData = response.data.data
}
```

### 5. Debug WebSocket Logs

**Backend**:
```python
# log_utils.py sets up WebSocketHandler
# Logs go to log_queue automatically

# Test WebSocket connection
ws = await websocket.connect("ws://localhost:8000/api/v1/admin/logs/ws")
while True:
    message = await ws.receive_text()
    print(message)
```

**Frontend** (in `stores/adminStore.ts`):
```typescript
connectWebSocket() {
  this.ws = new WebSocket('ws://localhost:5173/api/v1/admin/logs/ws')
  this.ws.onmessage = (event) => {
    this.logs.push(event.data)
  }
}
```

---

## Testing & Deployment

### Testing

**Backend** (pytest):
```bash
# Run tests
pytest

# Run specific test
pytest tests/test_collectors.py::test_db_connection

# Run with coverage
pytest --cov=collectors --cov-report=html
```

**Frontend** (not yet configured):
```bash
# Future: Vitest or Jest
npm run test
```

**Manual Testing**:
```bash
# Test daily task manually
curl -X POST http://localhost/api/v1/admin/tasks/daily_update/run \
     -H "Content-Type: application/json" \
     -d '{"test_mode": true}'

# Check task status
curl http://localhost/api/v1/admin/tasks/status
```

### Build Process

**Backend**:
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y libpq-dev gcc
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend** (Multi-stage):
```dockerfile
# Stage 1: Build
FROM node:22 AS build-stage
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Deployment Checklist

1. **Environment Variables**:
   - [ ] `.env` file configured with production credentials
   - [ ] Database credentials secure
   - [ ] API keys valid

2. **Database**:
   - [ ] TimescaleDB initialized with `init.sql`
   - [ ] Connection pooling configured (5-20 connections)
   - [ ] Backups directory mounted

3. **Backend**:
   - [ ] Scheduler jobs registered
   - [ ] Log directory mounted
   - [ ] Health check endpoint responding

4. **Frontend**:
   - [ ] Nginx config correct (API proxy, WebSocket upgrade)
   - [ ] Static files served from `/usr/share/nginx/html`
   - [ ] Vue Router fallback to `index.html`

5. **Docker Compose**:
   - [ ] All services depend on correct containers
   - [ ] Volumes persisted (`kdms_db_data`)
   - [ ] Network `kdms-net` created

6. **Verification**:
   ```bash
   docker-compose ps
   docker-compose logs -f
   curl http://localhost/api/v1/admin/tasks/status
   ```

---

## Important Notes for AI Assistants

### Critical Rules

1. **NEVER use `BackgroundScheduler`** - Always use `AsyncIOScheduler`
   - Reason: FastAPI is async, BackgroundScheduler blocks the event loop

2. **NEVER block FastAPI event loop** with synchronous heavy tasks
   - Use: `scheduler.add_job(func=..., trigger='date')` for manual execution
   - Don't use: `BackgroundTasks.add_task()` for heavy tasks

3. **ALWAYS use connection pooling** - Never create direct `psycopg2.connect()`
   - Use: `db_manager.get_connection()` / `db_manager.put_connection(conn)`

4. **ALWAYS use `RealDictCursor`** for database queries
   - Reason: Returns dict-like rows for easier JSON serialization

5. **NEVER commit `.env`, `.token_cache/`, or `logs/`** to git
   - These are in `.gitignore` and contain secrets

6. **Branch naming**: Must start with `claude/` for successful push
   - Example: `claude/claude-md-mif9zuhkv26mywes-01SEcjN2r6tMkvVqH8MdC2C4`

### Data Integrity

1. **Point-in-Time (PIT) Queries**:
   - ALWAYS filter by `retrieved_at <= target_date` for financial data
   - Order by `retrieved_at DESC` and `LIMIT 1` to get the correct version

2. **Price Adjustment**:
   - Raw OHLCV is in `daily_ohlcv` (NOT adjusted)
   - Adjustment factors in `price_adjustment_factors`
   - Apply factors: `adjusted_price = raw_price * cumulative_price_ratio`

3. **Timezone**:
   - Database timezone: `Asia/Seoul`
   - Python: Use `datetime.now()` (no timezone) or `datetime.now(timezone.utc)`
   - Always be aware of timezone when comparing timestamps

### Performance Optimization

1. **Use Apache Arrow for large datasets**:
   ```python
   import pyarrow as pa
   table = pa.Table.from_pydict({"col": data})
   sink = pa.BufferOutputStream()
   writer = pa.ipc.RecordBatchStreamWriter(sink, table.schema)
   writer.write_table(table)
   writer.close()
   return Response(content=sink.getvalue().to_pybytes(),
                   media_type="application/vnd.apache.arrow.stream")
   ```

2. **Index Usage**:
   - Daily OHLCV: Use `idx_daily_ohlcv_stk_cd_dt` for stock-specific queries
   - Minute OHLCV: Use `idx_minute_ohlcv_stk_cd_dt_tm`
   - Financials: Use `idx_fs_pit_screening` for PIT queries

3. **Connection Pool Tuning**:
   - Current: 5-20 connections
   - If `PoolError`, increase `maxconn` in `DatabaseManager.__init__()`

### Common Pitfalls

1. **Task Status Not Updating**:
   - Ensure `job_statuses` dict is passed to task function
   - Update `job_statuses[task_id]` throughout task execution

2. **WebSocket Disconnects**:
   - Frontend auto-reconnects after 3s
   - Backend `log_queue` has maxsize=1000, may drop logs if full

3. **Scheduler Jobs Not Running**:
   - Check `scheduler.running` is True
   - Verify timezone: `scheduler = AsyncIOScheduler(timezone="Asia/Seoul")`
   - Check `misfire_grace_time` for delayed execution

4. **Docker Container Crashes**:
   - Backend: Check `docker-compose logs backend` for Python errors
   - Frontend: Nginx config syntax error - check `nginx -t`
   - Database: Check volume permissions, disk space

5. **API Timeout (180s)**:
   - If task takes >180s, it's likely a long-running job
   - Use manual execution endpoint + status polling instead of waiting

### Code Quality

1. **Before Committing**:
   - [ ] Run `npm run lint` for frontend
   - [ ] Run `pytest` for backend (if tests exist)
   - [ ] Check `docker-compose build` succeeds
   - [ ] Verify no secrets in code

2. **PR Description Template**:
   ```markdown
   ## Summary
   - Brief description of changes

   ## Changes
   - Detailed list of modifications

   ## Testing
   - How to test the changes

   ## Checklist
   - [ ] Linting passed
   - [ ] Tests passing
   - [ ] No breaking changes (or documented)
   ```

### Useful Commands

```bash
# Database access
docker exec -it kdms_timescaledb psql -U your_user -d kdms_db

# Backend logs (real-time)
docker-compose logs -f backend

# Restart services
docker-compose restart backend

# Check disk usage
docker system df

# Cleanup
docker-compose down
docker volume rm kdms_kdms_db_data  # DANGER: Deletes all data

# Manual task execution
curl -X POST http://localhost/api/v1/admin/tasks/daily_update/run \
     -H "Content-Type: application/json" \
     -d '{"test_mode": false}'
```

---

## Contact & Resources

**Project Type**: Korean stock market data platform
**Primary Language**: Python (backend), TypeScript (frontend), Korean (comments)
**PRD Version**: v6.0 (Phase 7 - Dashboard Integration)

**Key Technologies**:
- FastAPI + Uvicorn (async Python web framework)
- Vue 3 + Vite + TypeScript (modern frontend stack)
- TimescaleDB + PostgreSQL 16 (time-series database)
- APScheduler (async job scheduling)
- Docker Compose (container orchestration)

**Important Files to Read First**:
1. `main.py` - Understand app initialization and scheduler setup
2. `init/init.sql` - Understand database schema (including daily_market_cap)
3. `routers/admin.py` - Understand task execution pattern
4. `collectors/krx_loader.py` - Understand pykrx market cap collection
5. `tasks/daily_task.py` - Understand Phase 5/5 market cap integration
6. `frontend/src/router/index.ts` - Understand frontend routes
7. `docker-compose.yml` - Understand deployment architecture

**When in Doubt**:
- Check existing code patterns before creating new ones
- Refer to PRD comments in code (e.g., `[PRD 3.1.1]`)
- Test with `test_mode=true` before running in production
- Use WebSocket logs for real-time debugging
- For market cap data issues, check pykrx DataFrame columns and debug logs

---

**Last Updated**: 2025-11-27 by AI Assistant
**Version**: 7.0 (Phase 8 - KRX Market Cap Integration)
