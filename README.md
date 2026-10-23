# SpendLite — Expense Tracker

A simple, fast, containerized personal expense tracking application powered by **FastAPI**, **PostgreSQL**, **Redis**, and **React + Vite**.

- **Frontend:** React 18 + Vite (Responsive dashboard, INR `₹` currency, live cache & connection indicators)
- **Backend:** Python + FastAPI + SQLAlchemy ORM (Pydantic validation, CORS configured)
- **Database:** PostgreSQL 16 (Persistent relational storage with Docker named volume)
- **Cache:** Redis 7 (60-second TTL on total spending, automatic cache invalidation on add/delete)
- **Containerization:** Docker & Docker Compose with service health checks and automatic startup sequencing

---

## 🏛️ Architecture Overview

```text
  +-------------------------------------------------------------+
  |                   User Browser (Client)                     |
  |                http://localhost:5173                        |
  +-------------------------------------------------------------+
                                 |
                                 v  (HTTP REST API)
  +-------------------------------------------------------------+
  |              FastAPI Backend (spendlite-backend)             |
  |                    http://localhost:8000                    |
  |                                                             |
  |   GET    /expenses        -> List all transactions (from DB)|
  |   POST   /expenses        -> Insert into DB & clear cache   |
  |   DELETE /expenses/{id}   -> Delete from DB & clear cache   |
  |   GET    /expenses/total  -> Redis-cached total spending    |
  |   GET    /health          -> DB & Redis connectivity status |
  +-------------------------------------------------------------+
            |                                          |
   (Check/Update Cache)                       (Read/Write Data)
            v                                          v
+-----------------------+              +------------------------------+
|     Redis Cache       |              |    PostgreSQL Database       |
|   (spendlite-redis)   |              |       (spendlite-db)         |
|       Port 6379       |              |          Port 5432           |
|    60s TTL Cache      |              |  Persistent Volume: db-data  |
+-----------------------+              +------------------------------+
```

### Automatic Service Dependency & Health Checks
- The **PostgreSQL container** runs a health check using `pg_isready -U spendlite_user -d spendlite_db`.
- The **Redis container** runs a health check using `redis-cli ping`.
- The **FastAPI backend** uses Docker Compose `condition: service_healthy` to wait for both PostgreSQL and Redis to be fully operational before launching.

---

## 💾 Database Persistence & Storage

1. **PostgreSQL Relational Model (`expenses` table)**:
   - `id` (VARCHAR 36, UUID Primary Key)
   - `title` (VARCHAR 100, Not Null)
   - `amount` (FLOAT, Not Null)
   - `category` (VARCHAR 50, Not Null)
   - `date` (VARCHAR 10, YYYY-MM-DD, Not Null)
   - `created_at` (VARCHAR 50, ISO 8601 UTC timestamp)
2. **Persistent Storage**:
   - The PostgreSQL database files are mounted to the named Docker volume `spendlite-db-data` (`/var/lib/postgresql/data`).
   - All records are saved permanently on your disk and survive container restarts, stops (`docker compose down`), and image rebuilds.

---

## 🔄 Migrating Existing JSON Records to PostgreSQL

If you have legacy records saved in `expenses.json`:
1. **Automatic Migration on Startup**:
   - SpendLite checks on backend startup if an `expenses.json` file is present in the data volume.
   - If found, it automatically imports any non-duplicate records into PostgreSQL and creates a backup named `expenses.json.migrated_backup`.
2. **Manual Migration Command**:
   - You can also run the dedicated migration script inside the container at any time:
     ```powershell
     docker compose exec backend python migrate_json_to_db.py
     ```

---

## ⚡ Redis Caching Behavior

1. When `GET /expenses/total` is called:
   - FastAPI first checks Redis for the key `spendlite:total_expenses`.
   - **Cache Hit:** Returns the cached total immediately (`"cached": true`).
   - **Cache Miss:** Runs an SQL `SELECT SUM(amount)` aggregation query against PostgreSQL, caches the result in Redis with a **60-second TTL**, and returns it (`"cached": false`).
2. When an expense is created (`POST /expenses`) or deleted (`DELETE /expenses/{id}`):
   - The cache key is immediately invalidated (`[CACHE INVALIDATED]`).
   - The next request to `GET /expenses/total` will query PostgreSQL for the new total and repopulate the Redis cache.
3. Every cache action is logged directly to the backend console.

---

## 📁 Project Structure

```text
spendlite/
├── docker-compose.yml          # Multi-container orchestration (PostgreSQL, Redis, Backend, Frontend)
├── .env.example                # Example environment variables
├── .gitignore                  # Git ignore rules for Python, Node, data, and logs
├── README.md                   # Documentation and guide
├── backend/
│   ├── Dockerfile              # Python 3.11-slim container with curl health check
│   ├── requirements.txt        # FastAPI, SQLAlchemy, Psycopg2, Redis, Pydantic, Pytest
│   ├── main.py                 # FastAPI endpoints, CORS, lifespan & auto-migration
│   ├── database.py             # SQLAlchemy engine, session maker, get_db dependency
│   ├── models.py               # SQLAlchemy ExpenseDB model & Pydantic schemas
│   ├── cache.py                # Redis caching and invalidation logic
│   ├── config.py               # Environment configuration
│   ├── migrate_json_to_db.py   # Migration tool from legacy JSON to PostgreSQL
│   ├── data/
│   │   └── .gitkeep            # Directory for legacy data / volume mount
│   └── tests/
│       ├── __init__.py
│       └── test_expenses.py    # Automated test suite (SQLite in-memory + Mock Redis)
└── frontend/
    ├── Dockerfile              # Node.js 20-alpine container with Vite
    ├── package.json            # React 18 + Vite dependencies
    ├── vite.config.js          # Vite config (host 0.0.0.0, port 5173, polling watch)
    ├── index.html              # HTML entry point with Inter font
    └── src/
        ├── main.jsx            # React root mount
        ├── App.jsx             # Expense Tracker UI, forms, state & INR currency
        ├── App.css             # Responsive styling, cards, category progress bars
        └── index.css           # Global typography & base styles
```

---

## 🚀 Quick Start (Windows Commands)

### Prerequisites
Make sure **Docker Desktop** is running on your Windows machine.

### 1. Build and Start All Containers
Open **PowerShell** or **Command Prompt** in the `spendlite` folder:

```powershell
docker compose up -d --build
```

Docker Compose will start:
- `spendlite-db` (PostgreSQL 16) on port `5432`
- `spendlite-redis` (Redis 7) on port `6379`
- `spendlite-backend` (FastAPI + SQLAlchemy) on port `8000`
- `spendlite-frontend` (React + Vite) on port `5173`

### 2. Verify Service Health
Check that all 4 services are healthy and running:
```powershell
docker compose ps
```

Verify backend, database, and Redis connectivity:
```powershell
curl http://localhost:8000/health
```
**Expected response:**
```json
{
  "status": "healthy",
  "app": "SpendLite — Expense Tracker",
  "database": "connected",
  "redis_connected": true
}
```

### 3. Open the Application
- **Frontend UI:** Open your browser to [http://localhost:5173](http://localhost:5173)
- **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🔍 How to Demonstrate Redis Cache Hits & Misses

Open two terminal windows side-by-side:

### Terminal 1: Watch Backend Logs
```powershell
docker compose logs -f backend
```

### Terminal 2: Test API Requests (or use the Web UI)

#### Step A: Calculate Total (Cache Miss)
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 0.0, "cached": false, "currency": "INR", "message": "Cache Miss: Computed from PostgreSQL and cached in Redis"}`
- **Terminal 1 Log:**
  ```text
  [CACHE MISS] Total spending key 'spendlite:total_expenses' not found in Redis
  [CACHE SET] Total spending (₹0.00) cached in Redis with TTL=60s
  ```

#### Step B: Repeat Request within 60s (Cache Hit)
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 0.0, "cached": true, "currency": "INR", "message": "Cache Hit: Retrieved from Redis"}`
- **Terminal 1 Log:**
  ```text
  [CACHE HIT] Total spending retrieved from Redis: ₹0.00
  ```

#### Step C: Add an Expense (Cache Invalidation)
Add an expense via the Web UI at [http://localhost:5173](http://localhost:5173) or using `curl`:
```powershell
curl -X POST http://localhost:8000/expenses -H "Content-Type: application/json" -d "{\"title\":\"Database Textbook\",\"amount\":750.00,\"category\":\"Education\",\"date\":\"2026-10-23\"}"
```
- **Terminal 1 Log:**
  ```text
  [CACHE INVALIDATED] Total spending cache key 'spendlite:total_expenses' cleared from Redis
  ```

#### Step D: Fetch Total Again (New Cache Miss & Recalculation)
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 750.0, "cached": false, "currency": "INR", "message": "Cache Miss: Computed from PostgreSQL and cached in Redis"}`
- **Terminal 1 Log:**
  ```text
  [CACHE MISS] Total spending key 'spendlite:total_expenses' not found in Redis
  [CACHE SET] Total spending (₹750.00) cached in Redis with TTL=60s
  ```

---

## 🧪 Running Automated Tests

The automated test suite runs in full isolation using an in-memory SQLite database and mock Redis, ensuring your live database is never altered:
- Adding an expense with validation
- Listing expenses sorted latest first
- Deleting an expense with 404 handling
- Total calculation from database
- Redis cache hit, cache miss, and 60s TTL behavior
- Redis cache invalidation on add and delete
- Database and Redis health checks
- Legacy JSON data migration

### Run Tests Inside the Backend Docker Container
```powershell
docker compose exec backend pytest
```
*(Or with Python's standard unittest runner)*:
```powershell
docker compose exec backend python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 🛑 Stopping and Managing Containers

### Stop Containers (Preserves PostgreSQL Data Volume)
```powershell
docker compose down
```

### Stop Containers and Wipe Database (Clean Reset)
```powershell
docker compose down -v
```

### Rebuild After Code Changes
```powershell
docker compose up -d --build
```

---

## ⚙️ Environment Variables Reference

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `POSTGRES_USER` | `spendlite_user` | PostgreSQL database user |
| `POSTGRES_PASSWORD` | `spendlite_password` | PostgreSQL database password |
| `POSTGRES_DB` | `spendlite_db` | PostgreSQL database name |
| `POSTGRES_HOST` | `db` | Database hostname inside Docker network |
| `POSTGRES_PORT` | `5432` | Database port |
| `DATABASE_URL` | `postgresql+psycopg2://spendlite_user:spendlite_password@db:5432/spendlite_db` | SQLAlchemy connection URI |
| `REDIS_HOST` | `redis` | Redis hostname inside Docker network |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_TTL` | `60` | Cache expiry time in seconds |
| `DATA_FILE_PATH` | `/app/data/expenses.json` | Path to legacy JSON data for auto-migration |
| `CORS_ORIGINS` | `*` | Allowed CORS origins for the API |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL for the frontend |
