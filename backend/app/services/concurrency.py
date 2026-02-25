"""Global concurrency limiter for background tasks (scraping + analysis)."""

import asyncio
import logging

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_max_concurrent: int = 3


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_max_concurrent)
    return _semaphore


def set_max_concurrent(n: int) -> None:
    """Update the max concurrent tasks. Takes effect for new tasks only."""
    global _semaphore, _max_concurrent
    _max_concurrent = max(1, min(10, n))
    _semaphore = asyncio.Semaphore(_max_concurrent)
    logger.info(f"[Concurrency] Max concurrent tasks set to {_max_concurrent}")


async def acquire() -> None:
    """Acquire a slot (blocks until one is available)."""
    await _get_semaphore().acquire()


def release() -> None:
    """Release a slot."""
    _get_semaphore().release()


async def init_from_db() -> None:
    """Load max_concurrent setting from database on startup."""
    try:
        from app.database import async_session
        from app.models.app_settings import AppSetting

        async with async_session() as db:
            setting = await db.get(AppSetting, "max_concurrent_tasks")
            if setting:
                set_max_concurrent(int(setting.value))
            else:
                set_max_concurrent(3)
    except Exception as e:
        logger.warning(f"[Concurrency] Failed to load setting from DB: {e}")
        set_max_concurrent(3)
