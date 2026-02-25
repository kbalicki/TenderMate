from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.app_settings import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])

# Default values for all settings
DEFAULTS = {
    "max_concurrent_tasks": "3",
}


async def _get_setting(db: AsyncSession, key: str) -> str:
    setting = await db.get(AppSetting, key)
    if setting:
        return setting.value
    return DEFAULTS.get(key, "")


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    setting = await db.get(AppSetting, key)
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    await db.commit()


class SettingsOut(BaseModel):
    max_concurrent_tasks: int = 3


class SettingsUpdate(BaseModel):
    max_concurrent_tasks: int | None = None


@router.get("", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    mct = await _get_setting(db, "max_concurrent_tasks")
    return SettingsOut(max_concurrent_tasks=int(mct) if mct else 3)


@router.put("", response_model=SettingsOut)
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    if data.max_concurrent_tasks is not None:
        val = max(1, min(10, data.max_concurrent_tasks))
        await _set_setting(db, "max_concurrent_tasks", str(val))
        # Update the in-memory semaphore
        from app.services.concurrency import set_max_concurrent
        set_max_concurrent(val)

    return await get_settings(db)
