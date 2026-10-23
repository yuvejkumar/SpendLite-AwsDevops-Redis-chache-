import os

DATA_FILE_PATH = os.getenv("DATA_FILE_PATH", "data/expenses.json")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "60"))
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*")

if CORS_ORIGINS_RAW == "*":
    CORS_ORIGINS = ["*"]
else:
    CORS_ORIGINS = [orig.strip() for orig in CORS_ORIGINS_RAW.split(",") if orig.strip()]

CACHE_KEY_TOTAL = "spendlite:total_expenses"
