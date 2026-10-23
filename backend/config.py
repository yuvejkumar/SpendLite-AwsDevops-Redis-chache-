import os

# PostgreSQL Configuration
POSTGRES_USER = os.getenv("POSTGRES_USER", "spendlite_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "spendlite_password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "spendlite_db")

# Default database URL explicitly using psycopg2 driver
default_db_url = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# Constructed Database URL or explicit override
raw_db_url = os.getenv("DATABASE_URL", default_db_url).strip()

# Ensure SQLAlchemy uses psycopg2 driver if a generic postgresql:// or postgres:// URL is provided
if raw_db_url.startswith("postgresql://"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = raw_db_url

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "60"))
CACHE_KEY_TOTAL = "spendlite:total_expenses"

# Legacy JSON storage path (used for data migration)
DATA_FILE_PATH = os.getenv("DATA_FILE_PATH", "data/expenses.json")

# CORS Origins
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS_RAW == "*":
    CORS_ORIGINS = ["*"]
else:
    CORS_ORIGINS = [orig.strip() for orig in CORS_ORIGINS_RAW.split(",") if orig.strip()]
