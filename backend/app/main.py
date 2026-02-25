import contextvars
import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.models import *  # noqa: F401,F403 — ensure all models registered
from app.api.router import api_router

# ── Request-scoped context ──────────────────────────────────────────
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
)
# Attach the filter to all existing handlers (basicConfig creates one)
for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())


async def _try_alter(conn, column_sql: str, table: str) -> None:
    """Try to add a column; ignore if it already exists (SQLite)."""
    try:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_sql}"))
    except Exception:
        pass  # column already exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    # Create tables if they don't exist (dev convenience; use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migrations — add columns that may not exist yet
        await _try_alter(conn, "error_message TEXT", "tenders")
        await _try_alter(conn, "ai_summary TEXT", "tenders")
        await _try_alter(conn, "authority_type VARCHAR(20)", "tenders")
        await _try_alter(conn, "annual_revenue_pln INTEGER", "company_profiles")

    # Seed default user
    from app.database import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == 1))
        if not result.scalar_one_or_none():
            session.add(User(id=1, name="Default User"))
            await session.commit()

    yield


app = FastAPI(title="TenderMate", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

logger = logging.getLogger(__name__)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    request.state.request_id = rid
    t0 = time.perf_counter()
    response = await call_next(request)
    dt = (time.perf_counter() - t0) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({dt:.0f}ms)")
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception on {request.method} {request.url}:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
