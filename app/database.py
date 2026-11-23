import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Tuple

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

# Safe atomic lock release via Lua script (ensures only the token holder can release)
LUA_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


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
        Returns True if duplicate (already exists), False if first seen (recorded).
        """
        key = f"dedup:msg:{message_id}"
        is_first_seen = await self.redis.set(
            name=key,
            value="1",
            ex=self.ttl_seconds,
            nx=True,
        )
        return not bool(is_first_seen)


class DistributedLock:
    """
    Atomic distributed lock manager based on user's phone_number and tenant.
    Uses UUID tokens and Lua script to guarantee safe atomic releases.
    Prevents race conditions caused by rapid clicking or message bursts.
    """

    def __init__(
        self,
        redis: Redis,
        phone_number: str,
        company_id: str = "default",
        timeout: float = 10.0,
        blocking_timeout: float = 2.0,
    ):
        self.redis = redis
        self.phone_number = phone_number
        self.company_id = company_id
        if company_id == "default":
            self.lock_key = f"lock:user:{phone_number}"
        else:
            self.lock_key = f"lock:company:{company_id}:user:{phone_number}"
        self.timeout = timeout
        self.blocking_timeout = blocking_timeout
        self.token = str(uuid.uuid4())

    async def acquire(self) -> bool:
        """Attempt to acquire the lock with spin-wait up to blocking_timeout."""
        start = time.monotonic()
        while True:
            acquired = await self.redis.set(
                name=self.lock_key,
                value=self.token,
                ex=int(self.timeout),
                nx=True,
            )
            if acquired:
                return True
            if (time.monotonic() - start) >= self.blocking_timeout:
                return False
            await asyncio.sleep(0.05)

    async def release(self) -> bool:
        """Safely release the lock via Lua script only if the token matches."""
        try:
            res = await self.redis.eval(LUA_RELEASE_LOCK_SCRIPT, 1, self.lock_key, self.token)
            return bool(res)
        except Exception as exc:
            logger.warning("Error releasing lock for %s: %s", self.lock_key, exc)
            return False

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise LockAcquisitionError(
                f"Could not acquire lock for {self.lock_key} within {self.blocking_timeout}s"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


class MessageDebouncer:
    """
    Message Debouncer for handling fragmented WhatsApp messages in rapid bursts.
    Stores incoming message chunks in Redis and yields to the latest chunk
    to aggregate and execute with up to 65% token savings.
    """

    def __init__(self, redis: Redis, wait_seconds: float = 2.0, ttl_seconds: int = 60):
        self.redis = redis
        self.wait_seconds = wait_seconds
        self.ttl_seconds = ttl_seconds

    def _buffer_key(self, company_id: str, phone: str) -> str:
        return f"buffer:inbound:{company_id}:{phone}"

    def _counter_key(self, company_id: str, phone: str) -> str:
        return f"counter:inbound:{company_id}:{phone}"

    async def buffer_and_wait(
        self,
        phone: str,
        text: str,
        company_id: str = "default",
    ) -> Tuple[bool, str]:
        """
        Appends text to buffer, increments sequence counter, and waits wait_seconds.
        If current sequence is still the latest, merges all chunks and returns (True, full_text).
        If a newer message arrived in the burst, yields and returns (False, "").
        """
        buf_key = self._buffer_key(company_id, phone)
        cnt_key = self._counter_key(company_id, phone)

        await self.redis.rpush(buf_key, text)
        await self.redis.expire(buf_key, self.ttl_seconds)

        current_seq = await self.redis.incr(cnt_key)
        await self.redis.expire(cnt_key, self.ttl_seconds)

        await asyncio.sleep(self.wait_seconds)

        latest_seq = await self.redis.get(cnt_key)
        if latest_seq is not None and int(latest_seq) == current_seq:
            chunks = await self.redis.lrange(buf_key, 0, -1)
            await self.redis.delete(buf_key, cnt_key)
            full_text = " ".join(c.strip() for c in chunks if c and c.strip())
            return True, full_text or text

        return False, ""


class SessionCache:
    """Ephemeral session cache to optimize fast access to current_step and format_type."""

    def __init__(self, redis: Redis, ttl_seconds: int = 1800):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _key_step(self, phone_number: str, company_id: str = "default") -> str:
        return f"session:company:{company_id}:step:{phone_number}"

    def _key_format(self, phone_number: str, company_id: str = "default") -> str:
        return f"session:company:{company_id}:format:{phone_number}"

    async def get_cached_step(self, phone_number: str, company_id: str = "default") -> Optional[str]:
        return await self.redis.get(self._key_step(phone_number, company_id))

    async def set_cached_step(self, phone_number: str, step: str, company_id: str = "default") -> None:
        await self.redis.set(
            name=self._key_step(phone_number, company_id),
            value=step,
            ex=self.ttl_seconds,
        )

    async def get_cached_format(self, phone_number: str, company_id: str = "default") -> Optional[str]:
        return await self.redis.get(self._key_format(phone_number, company_id))

    async def set_cached_format(
        self, phone_number: str, format_type: Optional[str], company_id: str = "default"
    ) -> None:
        if format_type:
            await self.redis.set(
                name=self._key_format(phone_number, company_id),
                value=format_type,
                ex=self.ttl_seconds,
            )
        else:
            await self.redis.delete(self._key_format(phone_number, company_id))

    async def invalidate(self, phone_number: str, company_id: str = "default") -> None:
        await self.redis.delete(
            self._key_step(phone_number, company_id),
            self._key_format(phone_number, company_id),
        )
