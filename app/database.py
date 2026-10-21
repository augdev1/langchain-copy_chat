import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis, from_url
from redis.exceptions import LockError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------
# PostgreSQL / SQLAlchemy 2.0 Async Setup
# ---------------------------------------------------------

async_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL == "DEBUG"),
    future=True,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db(engine: AsyncEngine = async_engine) -> None:
    """Create all relational tables and vector extensions asynchronously."""
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an isolated async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------
# Redis Async Client & Concurrency Primitives
# ---------------------------------------------------------

redis_client: Optional[Redis] = None


def get_redis_client(redis_url: Optional[str] = None) -> Redis:
    """Instantiate or return the global async Redis client."""
    global redis_client
    if redis_client is None:
        url = redis_url or settings.REDIS_URL
        redis_client = from_url(
            url,
            decode_responses=True,
            health_check_interval=30,
        )
    return redis_client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency providing async Redis client."""
    client = get_redis_client()
    yield client


# ---------------------------------------------------------
# Concurrency & Resilience Helpers
# ---------------------------------------------------------


class LockAcquisitionError(Exception):
    """Raised when distributed lock cannot be acquired within blocking timeout."""

    pass


class EventDeduplicator:
    """Ensures idempotent message processing by deduplicating message_id in Redis."""

    def __init__(self, redis: Redis, ttl_seconds: int = 300):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    async def is_duplicate(self, message_id: str) -> bool:
        """
        Check if message_id was already processed within TTL.
        Returns True if it is a duplicate (already exists), False if first seen (recorded).
        """
        key = f"dedup:msg:{message_id}"
        # set with NX=True returns True if key was set, None if key already existed
        is_first_seen = await self.redis.set(
            name=key,
            value="processed",
            ex=self.ttl_seconds,
            nx=True,
        )
        return not bool(is_first_seen)


class DistributedLock:
    """
    Atomic distributed lock manager based on user's phone_number.
    Prevents race conditions caused by rapid clicking or message bursts.
    """

    def __init__(
        self,
        redis: Redis,
        phone_number: str,
        timeout: float = 10.0,
        blocking_timeout: float = 2.0,
    ):
        self.redis = redis
        self.lock_key = f"lock:user:{phone_number}"
        self.timeout = timeout
        self.blocking_timeout = blocking_timeout
        self._lock = self.redis.lock(
            name=self.lock_key,
            timeout=self.timeout,
            blocking_timeout=self.blocking_timeout,
        )

    async def __aenter__(self):
        try:
            acquired = await self._lock.acquire()
            if not acquired:
                raise LockAcquisitionError(
                    f"Could not acquire lock for {self.lock_key} within {self.blocking_timeout}s"
                )
            return self
        except LockError as exc:
            raise LockAcquisitionError(f"Distributed lock failure: {exc}") from exc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self._lock.release()
        except LockError:
            # Lock might have expired or been freed; log and prevent crashing cleanup
            logger.warning(f"Lock for {self.lock_key} was already released or expired")


class SessionCache:
    """Ephemeral session cache to optimize fast access to current_step."""

    def __init__(self, redis: Redis, ttl_seconds: int = 1800):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _key_step(self, phone_number: str) -> str:
        return f"session:step:{phone_number}"

    def _key_format(self, phone_number: str) -> str:
        return f"session:format:{phone_number}"

    async def get_cached_step(self, phone_number: str) -> Optional[str]:
        return await self.redis.get(self._key_step(phone_number))

    async def set_cached_step(self, phone_number: str, step: str) -> None:
        await self.redis.set(
            name=self._key_step(phone_number),
            value=step,
            ex=self.ttl_seconds,
        )

    async def get_cached_format(self, phone_number: str) -> Optional[str]:
        return await self.redis.get(self._key_format(phone_number))

    async def set_cached_format(self, phone_number: str, format_type: Optional[str]) -> None:
        if format_type:
            await self.redis.set(
                name=self._key_format(phone_number),
                value=format_type,
                ex=self.ttl_seconds,
            )
        else:
            await self.redis.delete(self._key_format(phone_number))

    async def invalidate(self, phone_number: str) -> None:
        await self.redis.delete(self._key_step(phone_number), self._key_format(phone_number))

