from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.models import *  # noqa: F401,F403 — ensure all models registered
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    # Create tables if they don't exist (dev convenience; use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
