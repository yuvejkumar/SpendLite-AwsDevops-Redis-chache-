import logging
from typing import Optional

logger = logging.getLogger("spendlite.cache")

try:
    import redis
except ImportError:
    redis = None


class RedisCacheManager:
    """Manages Redis caching for SpendLite expense calculations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        ttl: int = 60,
        key: str = "spendlite:total_expenses",
        client=None,
    ):
        self.host = host
        self.port = port
        self.ttl = ttl
        self.key = key
        self._client = client

        if self._client is None and redis is not None:
            self._connect()

    def _connect(self) -> None:
        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Ping to verify connection
            self._client.ping()
            logger.info("Connected to Redis at %s:%d", self.host, self.port)
        except Exception as e:
            logger.warning("Could not establish immediate Redis connection (%s:%d): %s", self.host, self.port, e)

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def get_total(self) -> Optional[float]:
        """Check Redis cache for total spending.

        Returns float on CACHE HIT, None on CACHE MISS.
        """
        if self._client is None:
            logger.info("[CACHE MISS] Redis client is not available")
            return None
        try:
            val = self._client.get(self.key)
            if val is not None:
                cached_total = float(val)
                logger.info("[CACHE HIT] Total spending retrieved from Redis: ₹%.2f (Key: '%s')", cached_total, self.key)
                return cached_total
            else:
                logger.info("[CACHE MISS] Total spending key '%s' not found in Redis", self.key)
                return None
        except Exception as e:
            logger.warning("[CACHE ERROR] Error reading key '%s' from Redis: %s", self.key, e)
            return None

    def set_total(self, total: float) -> bool:
        """Cache total spending in Redis with configured TTL."""
        if self._client is None:
            return False
        try:
            self._client.setex(self.key, self.ttl, str(total))
            logger.info(
                "[CACHE SET] Total spending (₹%.2f) cached in Redis with TTL=%ds (Key: '%s')",
                total,
                self.ttl,
                self.key,
            )
            return True
        except Exception as e:
            logger.warning("[CACHE ERROR] Error writing to Redis: %s", e)
            return False

    def invalidate_total(self) -> bool:
        """Invalidate the cached total in Redis (invoked on expense add or delete)."""
        if self._client is None:
            return False
        try:
            deleted = self._client.delete(self.key)
            logger.info(
                "[CACHE INVALIDATED] Total spending cache key '%s' cleared from Redis (keys removed: %d)",
                self.key,
                deleted,
            )
            return True
        except Exception as e:
            logger.warning("[CACHE ERROR] Error deleting key '%s' from Redis: %s", self.key, e)
            return False
