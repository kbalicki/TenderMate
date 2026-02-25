import io
import logging
import math
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, func, case, nulls_last
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.tender import Tender
from app.models.tender_attachment import TenderAttachment
from app.models.analysis import Analysis
from app.schemas.tender import (
    TenderFromUrl,
    TenderFromUrlResult,
    TenderFromUrlResponse,
    TenderOut,
    TenderDetailOut,
    TenderAttachmentOut,
    TenderListItemOut,
    PaginatedTendersOut,
    AnalysisSummary,
)
from app.services import scraper_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenders", tags=["tenders"])

# Allowed sort columns
_SORT_COLUMNS = {
    "submission_deadline": Tender.submission_deadline,
    "created_at": Tender.created_at,
    "title": Tender.title,
    "status": Tender.status,
    "contracting_authority": Tender.contracting_authority,
}


def _extract_analysis_summary(analysis: Analysis | None, attachment_count: int) -> AnalysisSummary | None:
    """Build a compact analysis summary from the Analysis model for the list view."""
    if analysis is None:
        return None

    eligible = None
    eligibility_summary = None
    step0 = analysis.step0_result
    if isinstance(step0, dict):
        eligible = step0.get("eligible")
        # Build eligibility summary: why not eligible + what to do
        if eligible is False:
            reasons = []
            actions = []
            for cond in step0.get("conditions", []):
                if not cond.get("met"):
                    if cond.get("reason"):
                        reasons.append(cond["reason"])
                    if cond.get("fix_options"):
                        actions.extend(cond["fix_options"][:1])  # first fix option
            summary_parts = []
            if reasons:
                summary_parts.append("; ".join(reasons[:2]))
            if actions:
                summary_parts.append("Rozwiązanie: " + "; ".join(actions[:2]))
            eligibility_summary = " | ".join(summary_parts) if summary_parts else None

    go_no_go = None
    go_no_go_rationale = None
    step4 = analysis.step4_result
    if isinstance(step4, dict):
        go_no_go = step4.get("go_no_go_recommendation")
        go_no_go_rationale = step4.get("recommendation_rationale")

    total_net_pln = None
    step3 = analysis.step3_result
    if isinstance(step3, dict):
        total_net_pln = step3.get("total_net_pln")

    scope_description = None
    if isinstance(step0, dict):
        scope_description = step0.get("scope_description")

    return AnalysisSummary(
        eligible=eligible,
        eligibility_summary=eligibility_summary,
        go_no_go=go_no_go,
        go_no_go_rationale=go_no_go_rationale,
        total_net_pln=total_net_pln,
        scope_description=scope_description,
        analysis_status=analysis.status,
        user_decision=analysis.user_decision,
        attachment_count=attachment_count,
    )


@router.get("", response_model=PaginatedTendersOut)
async def list_tenders(
    status: str | None = None,
    search: str | None = None,
    sort_by: str = Query("submission_deadline", enum=list(_SORT_COLUMNS.keys())),
    sort_dir: str = Query("asc", enum=["asc", "desc"]),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    # Base query
    base = select(Tender)
    if status:
        if status == "archived":
            from datetime import datetime
            base = base.where(
                Tender.submission_deadline < datetime.utcnow(),
                Tender.status.notin_(["completed", "rejected"]),
            )
        else:
            base = base.where(Tender.status == status)
    if search:
        like_pattern = f"%{search}%"
        base = base.where(
            Tender.title.ilike(like_pattern)
            | Tender.contracting_authority.ilike(like_pattern)
            | Tender.reference_number.ilike(like_pattern)
        )

    # Count total
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sorting — nulls last for nullable columns
    sort_col = _SORT_COLUMNS.get(sort_by, Tender.submission_deadline)
    if sort_dir == "desc":
        order = nulls_last(sort_col.desc())
    else:
        order = nulls_last(sort_col.asc())

    # Paginate
    query = (
        base
        .options(selectinload(Tender.analysis), selectinload(Tender.attachments))
        .order_by(order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    tenders = result.scalars().unique().all()

    # Build response items
    items = []
    for t in tenders:
        att_count = len(t.attachments) if t.attachments else 0
        summary = _extract_analysis_summary(t.analysis, att_count)
        item = TenderListItemOut(
            id=t.id,
            source_type=t.source_type,
            source_url=t.source_url,
            portal_name=t.portal_name,
            title=t.title,
            contracting_authority=t.contracting_authority,
            authority_type=t.authority_type,
            reference_number=t.reference_number,
            submission_deadline=t.submission_deadline,
            status=t.status,
            error_message=t.error_message,
            ai_summary=t.ai_summary,
            created_at=t.created_at,
            updated_at=t.updated_at,
            analysis_summary=summary,
            attachment_count=att_count,
        )
        items.append(item)

    return PaginatedTendersOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.post("/from-url", response_model=TenderFromUrlResponse, status_code=201)
async def create_from_url(data: TenderFromUrl, db: AsyncSession = Depends(get_db)):
    if not data.urls:
        raise HTTPException(400, "At least one URL is required")

    results: list[TenderFromUrlResult] = []

    for url in data.urls:
        url = url.strip()
        if not url:
            continue

        # Check for duplicate by source_url
        existing = await db.execute(
            select(Tender).where(Tender.source_url == url).limit(1)
        )
        existing_tender = existing.scalars().first()
        if existing_tender:
            results.append(TenderFromUrlResult(
                url=url,
                status="duplicate",
                tender_id=existing_tender.id,
                message=f"Przetarg już istnieje (ID: {existing_tender.id})",
            ))
            continue

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

        # Launch scraping in background
        await scraper_service.launch_scraping(tender.id)

        results.append(TenderFromUrlResult(
            url=url,
            status="created",
            tender_id=tender.id,
        ))

    if not results:
        raise HTTPException(400, "No valid URLs provided")

    return TenderFromUrlResponse(results=results)


@router.post("/{tender_id}/rescrape", response_model=TenderOut)
async def rescrape_tender(tender_id: int, db: AsyncSession = Depends(get_db)):
    """Re-run scraping for a tender (e.g. after scrape failure)."""
    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")
    if tender.source_type != "url" or not tender.source_url:
        raise HTTPException(400, "Tender has no source URL")

    tender.status = "scraping"
    tender.error_message = None
    await db.commit()
    await db.refresh(tender)

    await scraper_service.launch_scraping(tender.id)
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


@router.post("/{tender_id}/attachments/upload", response_model=list[TenderAttachmentOut])
async def upload_attachments(
    tender_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload additional files to a tender. ZIP files are auto-extracted.
    Duplicates (by filename) are skipped."""
    from app.services.scraper_service import _sanitize_filename, _extract_zip_files, _guess_mime

    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    data_dir = Path(tender.data_dir) if tender.data_dir else settings.data_dir / "tenders" / str(tender_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    att_dir = data_dir / "attachments"
    att_dir.mkdir(exist_ok=True)

    if not tender.data_dir:
        tender.data_dir = str(data_dir)

    # Get existing filenames for duplicate detection
    existing_result = await db.execute(
        select(TenderAttachment.filename).where(TenderAttachment.tender_id == tender_id)
    )
    existing_names = {row[0] for row in existing_result.all()}

    saved_files: list[Path] = []
    for f in files:
        safe_name = _sanitize_filename(f.filename or "attachment")
        file_path = att_dir / safe_name

        # Skip duplicates
        if safe_name in existing_names:
            logger.info(f"[Upload] Pominięto duplikat: {safe_name}")
            continue

        content = await f.read()
        file_path.write_bytes(content)
        saved_files.append(file_path)
        logger.info(f"[Upload] Zapisano: {safe_name} ({len(content)} B)")

    # Extract ZIP files
    extracted = _extract_zip_files(saved_files, att_dir)
    if extracted:
        saved_files.extend(extracted)
        logger.info(f"[Upload] Wyekstrahowano {len(extracted)} plików z ZIP-ów")

    # Register in DB (skip duplicates)
    new_attachments = []
    for fp in saved_files:
        if fp.name in existing_names:
            logger.info(f"[Upload] Pominięto duplikat (z ZIP): {fp.name}")
            continue
        if not fp.exists():
            continue

        att = TenderAttachment(
            tender_id=tender_id,
            filename=fp.name,
            file_path=str(fp.relative_to(data_dir)),
            file_size_bytes=fp.stat().st_size,
            mime_type=_guess_mime(fp.name),
        )
        db.add(att)
        new_attachments.append(att)
        existing_names.add(fp.name)

    await db.commit()
    for att in new_attachments:
        await db.refresh(att)

    logger.info(f"[Upload] Dodano {len(new_attachments)} nowych załączników do tender_id={tender_id}")
    return new_attachments


@router.get("/{tender_id}/attachments", response_model=list[TenderAttachmentOut])
async def list_attachments(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenderAttachment).where(TenderAttachment.tender_id == tender_id)
    )
    return result.scalars().all()


@router.get("/{tender_id}/attachments/download-all")
async def download_all_attachments(tender_id: int, db: AsyncSession = Depends(get_db)):
    """Download all attachments as a single ZIP file."""
    tender_result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = tender_result.scalar_one_or_none()
    if not tender:
        raise HTTPException(404, "Tender not found")

    result = await db.execute(
        select(TenderAttachment).where(TenderAttachment.tender_id == tender_id)
    )
    attachments = result.scalars().all()
    if not attachments:
        raise HTTPException(404, "No attachments to download")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for att in attachments:
            file_path = Path(tender.data_dir) / att.file_path
            if file_path.exists():
                zf.write(file_path, att.filename)

    buf.seek(0)
    zip_name = f"przetarg_{tender_id}_zalaczniki.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


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
