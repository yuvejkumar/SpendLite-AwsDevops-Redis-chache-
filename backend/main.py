import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from cache import RedisCacheManager
import config
from database import check_db_health, get_db, init_db
from migrate_json_to_db import migrate_json_to_database
from models import Expense, ExpenseCreate, ExpenseDB, TotalResponse

# Configure logging to console with clear timestamp and formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spendlite.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing SpendLite Backend with PostgreSQL & Redis...")
    # 1. Initialize Redis Cache Manager
    app.state.cache = RedisCacheManager(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        ttl=config.REDIS_TTL,
        key=config.CACHE_KEY_TOTAL,
    )

    # 2. Initialize PostgreSQL tables
    try:
        init_db()
        logger.info("Database schema verified.")
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)

    # 3. Check and migrate legacy JSON expenses if found
    try:
        migrated = migrate_json_to_database(config.DATA_FILE_PATH)
        if migrated > 0:
            logger.info("Auto-migrated %d expense(s) from legacy JSON storage to PostgreSQL.", migrated)
    except Exception as e:
        logger.warning("Could not execute automatic JSON data migration: %s", e)

    logger.info("SpendLite Backend started successfully.")
    yield
    logger.info("SpendLite Backend shutting down.")


app = FastAPI(
    title="SpendLite — Expense Tracker API",
    version="2.0.0",
    description="FastAPI Backend with PostgreSQL storage and Redis caching",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS if "*" not in config.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_cache(request: Request) -> RedisCacheManager:
    if hasattr(request.app.state, "cache"):
        return request.app.state.cache
    return RedisCacheManager(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        ttl=config.REDIS_TTL,
        key=config.CACHE_KEY_TOTAL,
    )


@app.get("/health", summary="Health Check")
def health_check(
    db: Session = Depends(get_db),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Check health of application, PostgreSQL database, and Redis connectivity."""
    db_healthy = check_db_health()
    redis_healthy = cache.is_connected()
    overall_status = "healthy" if (db_healthy and redis_healthy) else "degraded"

    return {
        "status": overall_status,
        "app": "SpendLite — Expense Tracker",
        "database": "connected" if db_healthy else "disconnected",
        "redis_connected": redis_healthy,
    }


@app.get("/expenses", response_model=List[Expense], summary="List All Expenses")
def list_expenses(db: Session = Depends(get_db)):
    """Return all tracked expenses from PostgreSQL, sorted latest first."""
    expenses = (
        db.query(ExpenseDB)
        .order_by(ExpenseDB.date.desc(), ExpenseDB.created_at.desc())
        .all()
    )
    return expenses


@app.post(
    "/expenses",
    response_model=Expense,
    status_code=status.HTTP_201_CREATED,
    summary="Create Expense",
)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Create a new expense, persist to PostgreSQL, and invalidate cached total."""
    expense = ExpenseDB(
        title=payload.title,
        amount=payload.amount,
        category=payload.category,
        date=payload.date,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    # Invalidate cache so next /expenses/total reflects the new expense
    cache.invalidate_total()
    return expense


@app.delete("/expenses/{id}", summary="Delete Expense")
def delete_expense(
    id: str,
    db: Session = Depends(get_db),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Delete an expense by ID from PostgreSQL and invalidate cached total."""
    expense = db.query(ExpenseDB).filter(ExpenseDB.id == id).first()
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense with ID '{id}' was not found.",
        )

    db.delete(expense)
    db.commit()

    # Invalidate cache so next /expenses/total reflects removed expense
    cache.invalidate_total()
    return {"message": "Expense deleted successfully", "id": id}


@app.get("/expenses/total", response_model=TotalResponse, summary="Get Total Spending")
def get_total_expenses(
    db: Session = Depends(get_db),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Calculate or retrieve cached total spending.

    - Checks Redis first.
    - If CACHE HIT: returns cached total immediately.
    - If CACHE MISS: calculates sum from PostgreSQL, caches in Redis with 60s TTL, and returns.
    """
    cached_val = cache.get_total()
    if cached_val is not None:
        return TotalResponse(
            total=cached_val,
            cached=True,
            currency="INR",
            message="Cache Hit: Retrieved from Redis",
        )

    # Cache miss - calculate total from PostgreSQL
    total_scalar = db.query(func.coalesce(func.sum(ExpenseDB.amount), 0.0)).scalar()
    total = round(float(total_scalar), 2)
    cache.set_total(total)

    return TotalResponse(
        total=total,
        cached=False,
        currency="INR",
        message="Cache Miss: Computed from PostgreSQL and cached in Redis",
    )
