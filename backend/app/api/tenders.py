import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.tender import Tender
from app.models.tender_attachment import TenderAttachment
from app.schemas.tender import (
    TenderFromUrl,
    TenderOut,
    TenderDetailOut,
    TenderAttachmentOut,
)

router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.get("", response_model=list[TenderOut])
async def list_tenders(
    status: str | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(Tender).order_by(Tender.created_at.desc())
    if status:
        query = query.where(Tender.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/from-url", response_model=TenderOut, status_code=201)
async def create_from_url(data: TenderFromUrl, db: AsyncSession = Depends(get_db)):
    # For now, create one tender per URL; scraping will be added later
    if not data.urls:
        raise HTTPException(400, "At least one URL is required")

    url = data.urls[0]  # TODO: handle multiple URLs
    tender = Tender(
        source_type="url",
        source_url=url,
        status="new",
    )
    db.add(tender)
    await db.commit()
    await db.refresh(tender)

    # Create data directory
    data_dir = settings.data_dir / "tenders" / str(tender.id)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "attachments").mkdir(exist_ok=True)
    tender.data_dir = str(data_dir)
    await db.commit()
    await db.refresh(tender)

    return tender


@router.post("/manual", response_model=TenderOut, status_code=201)
async def create_manual(
    title: str = Form(None),
    tender_text: str = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    tender = Tender(
        source_type="manual",
        title=title,
        tender_text=tender_text,
        status="scraped",  # manual = already has content
    )
    db.add(tender)
    await db.commit()
    await db.refresh(tender)

    # Create data directory and save attachments
    data_dir = settings.data_dir / "tenders" / str(tender.id)
    data_dir.mkdir(parents=True, exist_ok=True)
    att_dir = data_dir / "attachments"
    att_dir.mkdir(exist_ok=True)
    tender.data_dir = str(data_dir)

    for f in files:
        file_path = att_dir / f.filename
        content = await f.read()
        file_path.write_bytes(content)

        attachment = TenderAttachment(
            tender_id=tender.id,
            filename=f.filename,
            file_path=str(file_path.relative_to(data_dir)),
            file_size_bytes=len(content),
            mime_type=f.content_type,
        )
        db.add(attachment)

    await db.commit()
    await db.refresh(tender)
    return tender


@router.get("/{tender_id}", response_model=TenderDetailOut)
async def get_tender(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tender)
        .options(selectinload(Tender.attachments))
        .where(Tender.id == tender_id)
    )
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(404, "Tender not found")
    return tender


@router.delete("/{tender_id}", status_code=204)
async def delete_tender(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(404, "Tender not found")

    # Remove data directory
    if tender.data_dir:
        data_dir = Path(tender.data_dir)
        if data_dir.exists():
            shutil.rmtree(data_dir)

    await db.delete(tender)
    await db.commit()


@router.get("/{tender_id}/attachments", response_model=list[TenderAttachmentOut])
async def list_attachments(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenderAttachment).where(TenderAttachment.tender_id == tender_id)
    )
    return result.scalars().all()


@router.get("/{tender_id}/attachments/{attachment_id}/download")
async def download_attachment(
    tender_id: int, attachment_id: int, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TenderAttachment).where(
            TenderAttachment.id == attachment_id,
            TenderAttachment.tender_id == tender_id,
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Attachment not found")

    tender_result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = tender_result.scalar_one()
    file_path = Path(tender.data_dir) / att.file_path
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(file_path, filename=att.filename)
