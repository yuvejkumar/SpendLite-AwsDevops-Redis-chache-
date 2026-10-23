import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from cache import RedisCacheManager
import config
from models import Expense, ExpenseCreate, TotalResponse
from storage import JSONStorage

# Configure logging to console with clear timestamp and formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spendlite.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup storage and cache on startup
    logger.info("Initializing SpendLite Backend...")
    app.state.storage = JSONStorage(config.DATA_FILE_PATH)
    app.state.cache = RedisCacheManager(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        ttl=config.REDIS_TTL,
        key=config.CACHE_KEY_TOTAL,
    )
    logger.info("SpendLite Backend started successfully.")
    yield
    logger.info("SpendLite Backend shutting down.")


app = FastAPI(
    title="SpendLite — Expense Tracker API",
    version="1.0.0",
    description="FastAPI Backend with Redis caching and JSON file persistence",
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


def get_storage(request: Request) -> JSONStorage:
    # Allows fallback if instantiated directly without lifespan (e.g., in some test runners)
    if hasattr(request.app.state, "storage"):
        return request.app.state.storage
    return JSONStorage(config.DATA_FILE_PATH)


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
    storage: JSONStorage = Depends(get_storage),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Check health of application, storage, and Redis connectivity."""
    redis_status = cache.is_connected()
    return {
        "status": "healthy",
        "app": "SpendLite — Expense Tracker",
        "storage": "ok",
        "redis_connected": redis_status,
    }


@app.get("/expenses", response_model=List[Expense], summary="List All Expenses")
def list_expenses(storage: JSONStorage = Depends(get_storage)):
    """Return all tracked expenses, sorted latest first."""
    expenses = storage.get_all()
    # Sort by date descending, then created_at descending
    expenses.sort(key=lambda x: (x.get("date", ""), x.get("created_at", "")), reverse=True)
    return expenses


@app.post(
    "/expenses",
    response_model=Expense,
    status_code=status.HTTP_201_CREATED,
    summary="Create Expense",
)
def create_expense(
    payload: ExpenseCreate,
    storage: JSONStorage = Depends(get_storage),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Create a new expense, persist to JSON, and invalidate cached total."""
    expense = Expense(
        title=payload.title,
        amount=payload.amount,
        category=payload.category,
        date=payload.date,
    )
    saved = storage.add(expense.model_dump())
    # Invalidate cache so next /expenses/total reflects new expense
    cache.invalidate_total()
    return saved


@app.delete("/expenses/{id}", summary="Delete Expense")
def delete_expense(
    id: str,
    storage: JSONStorage = Depends(get_storage),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Delete an expense by ID and invalidate cached total."""
    deleted = storage.delete(id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense with ID '{id}' was not found.",
        )
    # Invalidate cache so next /expenses/total reflects removed expense
    cache.invalidate_total()
    return {"message": "Expense deleted successfully", "id": id}


@app.get("/expenses/total", response_model=TotalResponse, summary="Get Total Spending")
def get_total_expenses(
    storage: JSONStorage = Depends(get_storage),
    cache: RedisCacheManager = Depends(get_cache),
):
    """Calculate or retrieve cached total spending.

    - Checks Redis first.
    - If CACHE HIT: returns cached total immediately.
    - If CACHE MISS: calculates from JSON, caches in Redis with 60s TTL, and returns.
    """
    cached_val = cache.get_total()
    if cached_val is not None:
        return TotalResponse(
            total=cached_val,
            cached=True,
            currency="INR",
            message="Cache Hit: Retrieved from Redis",
        )

    # Cache miss - calculate from JSON storage
    total = storage.calculate_total()
    cache.set_total(total)

    return TotalResponse(
        total=total,
        cached=False,
        currency="INR",
        message="Cache Miss: Computed from JSON and cached in Redis",
    )
