# SpendLite — Expense Tracker

A simple, fast, containerized personal expense tracking application built for Docker Compose.

- **Frontend:** React 18 + Vite (Responsive UI, INR `₹` currency, live cache indicator)
- **Backend:** Python + FastAPI (RESTful API, Pydantic validation, CORS configured)
- **Cache:** Redis 7 (60-second TTL on total spending, automatic invalidation on add/delete)
- **Storage:** JSON file (`data/expenses.json`) persisted across container restarts with Docker Volumes
- **Containerization:** Docker & Docker Compose with health checks and service dependencies

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
  |   GET  /expenses        -> List all transactions            |
  |   POST /expenses        -> Add expense & invalidate cache   |
  |   DELETE /expenses/{id} -> Remove expense & invalidate cache|
  |   GET  /expenses/total  -> Redis-cached total spending      |
  |   GET  /health          -> Service & Redis status           |
  +-------------------------------------------------------------+
           |                                          |
   (Check/Update Cache)                       (Read/Write Data)
           v                                          v
+-----------------------+              +------------------------------+
|     Redis Cache       |              |        JSON Storage          |
|   (spendlite-redis)   |              |  (spendlite-backend-data)    |
|       Port 6379       |              |     data/expenses.json       |
|    60s TTL Cache      |              |   Mounted via Docker Volume  |
+-----------------------+              +------------------------------+
```

### How the Redis Cache Works
1. When `GET /expenses/total` is requested, FastAPI first checks the Redis key `spendlite:total_expenses`.
2. **Cache Hit:** If found, the cached total is returned immediately (`"cached": true`).
3. **Cache Miss:** If not found in Redis, FastAPI calculates the sum from `data/expenses.json`, saves the result to Redis with a **60-second TTL**, and returns it (`"cached": false`).
4. **Cache Invalidation:** When an expense is added (`POST /expenses`) or deleted (`DELETE /expenses/{id}`), the cache key is immediately deleted so the next total calculation is fresh.
5. All cache events (`CACHE HIT`, `CACHE MISS`, `CACHE SET`, `CACHE INVALIDATED`) are logged to the backend console.

---

## 📁 Project Structure

```text
spendlite/
├── docker-compose.yml          # Multi-container orchestration (Redis, Backend, Frontend)
├── .env.example                # Example environment variables
├── .gitignore                  # Git ignore rules for Python, Node, and data
├── README.md                   # Documentation and guide
├── backend/
│   ├── Dockerfile              # Python 3.11-slim container
│   ├── requirements.txt        # FastAPI, Uvicorn, Redis, Pydantic, Pytest
│   ├── main.py                 # FastAPI application and route endpoints
│   ├── models.py               # Pydantic data schemas & validators
│   ├── storage.py              # JSON file persistence manager
│   ├── cache.py                # Redis caching and invalidation logic
│   ├── config.py               # Environment configuration
│   ├── data/
│   │   └── .gitkeep            # Directory for expenses.json volume mount
│   └── tests/
│       ├── __init__.py
│       └── test_expenses.py    # Automated backend & cache test suite
└── frontend/
    ├── Dockerfile              # Node.js 20-alpine container with Vite
    ├── package.json            # React & Vite dependencies
    ├── vite.config.js          # Vite configuration
    ├── index.html              # HTML entry point
    └── src/
        ├── main.jsx            # React root mount
        ├── App.jsx             # Expense Tracker UI, forms & state
        ├── App.css             # Component styling & responsiveness
        └── index.css           # Global typography & base styles
```

---

## 🚀 Quick Start (Windows Commands)

### Prerequisites
Make sure **Docker Desktop** is installed and running on Windows.

### 1. Build and Start All Containers
Open **PowerShell** or **Command Prompt** in the `spendlite` folder:

```powershell
docker compose up -d --build
```

Docker Compose will start:
- `spendlite-redis` on port `6379`
- `spendlite-backend` on port `8000`
- `spendlite-frontend` on port `5173`

### 2. Access the Application
- **Frontend UI:** Open your browser to [http://localhost:5173](http://localhost:5173)
- **Backend API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

### 3. Check Service Status
```powershell
docker compose ps
```

---

## 🔍 How to Demonstrate Redis Cache Hits & Misses

Open two terminal windows side-by-side to observe caching behavior:

### Terminal 1: Watch Backend Logs
```powershell
docker compose logs -f backend
```

### Terminal 2: Make API Requests (or use the Web UI)

#### Step 1: Calculate Total (Cache Miss)
Run this command in Terminal 2:
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 0.0, "cached": false, "currency": "INR", ...}`
- **Terminal 1 Log:**
  ```text
  [CACHE MISS] Total spending key 'spendlite:total_expenses' not found in Redis
  [CACHE SET] Total spending (₹0.00) cached in Redis with TTL=60s
  ```

#### Step 2: Repeat Request within 60s (Cache Hit)
Run the exact same command again:
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 0.0, "cached": true, "currency": "INR", ...}`
- **Terminal 1 Log:**
  ```text
  [CACHE HIT] Total spending retrieved from Redis: ₹0.00
  ```

#### Step 3: Add an Expense (Cache Invalidation)
Add an expense via the Web UI at [http://localhost:5173](http://localhost:5173) or using `curl`:
```powershell
curl -X POST http://localhost:8000/expenses -H "Content-Type: application/json" -d "{\"title\":\"Books\",\"amount\":450.00,\"category\":\"Education\",\"date\":\"2026-10-23\"}"
```
- **Terminal 1 Log:**
  ```text
  [CACHE INVALIDATED] Total spending cache key 'spendlite:total_expenses' cleared from Redis
  ```

#### Step 4: Fetch Total Again (New Cache Miss & Recalculation)
```powershell
curl http://localhost:8000/expenses/total
```
- **Response:** `{"total": 450.0, "cached": false, "currency": "INR", ...}`
- **Terminal 1 Log:**
  ```text
  [CACHE MISS] Total spending key 'spendlite:total_expenses' not found in Redis
  [CACHE SET] Total spending (₹450.00) cached in Redis with TTL=60s
  ```

---

## 🧪 Running Automated Tests

The automated test suite runs in isolation with mock Redis and temporary JSON storage files, verifying:
- Adding an expense (`POST /expenses`)
- Input validation (rejects negative amounts, empty titles, invalid dates)
- Listing expenses (`GET /expenses`)
- Deleting an expense (`DELETE /expenses/{id}`)
- Returning correct total calculation
- Cache miss and subsequent cache hit
- Cache invalidation on add
- Cache invalidation on delete
- Health check endpoint

### Run Tests Inside the Backend Docker Container
```powershell
docker compose exec backend pytest
```
*(Or if using unittest runner)*:
```powershell
docker compose exec backend python -m unittest discover -s tests -p "test_*.py" -v
```

### Run Tests Locally (Without Docker)
If you have Python installed locally:
```powershell
cd backend
$env:PYTHONPATH = "."
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 🛑 Stopping and Managing Containers

### Stop the Application (Preserving Data Volume)
```powershell
docker compose down
```

### Stop and Wipe All Data (Fresh Start)
```powershell
docker compose down -v
```

### Rebuild Containers After Code Changes
```powershell
docker compose up -d --build
```

---

## ⚙️ Environment Variables Reference

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `REDIS_HOST` | `redis` | Hostname of the Redis service |
| `REDIS_PORT` | `6379` | Port for the Redis service |
| `REDIS_TTL` | `60` | Cache expiry time in seconds |
| `DATA_FILE_PATH` | `/app/data/expenses.json` | Path to persistent JSON storage |
| `CORS_ORIGINS` | `*` | Allowed CORS origins for the API |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL for the frontend |
