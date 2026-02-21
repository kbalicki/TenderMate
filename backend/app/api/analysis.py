import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.analysis import Analysis
from app.models.analysis_document import AnalysisDocument
from app.models.tender import Tender
from app.schemas.analysis import (
    AnalysisOut,
    FixEligibilityRequest,
    DecisionRequest,
    AnalysisDocumentOut,
)
from app.services import analysis_service

router = APIRouter(prefix="/tenders/{tender_id}/analysis", tags=["analysis"])


@router.post("/start", response_model=AnalysisOut, status_code=201)
async def start_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    # Check if analysis already exists — restart if failed
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.status in ("failed", "waiting_user"):
            # Reset so user can retry
            existing.status = "running"
            existing.current_step = 0
            existing.error_message = None
            existing.step0_result = None
            existing.step0_eligible = None
            existing.step0_fix_actions = None
            existing.user_decision = None
            existing.step1_result = None
            existing.step2_result = None
            existing.step3_result = None
            existing.step4_result = None
            existing.step5_result = None
            tender.status = "analyzing"
            await db.commit()
            await db.refresh(existing)
            await analysis_service.launch_step(existing.id, 0)
            return existing
        return existing

    analysis = Analysis(tender_id=tender_id, current_step=0, status="running")
    db.add(analysis)
    tender.status = "analyzing"
    await db.commit()
    await db.refresh(analysis)

    # Launch step 0 in background
    await analysis_service.launch_step(analysis.id, 0)

    return analysis


@router.get("", response_model=AnalysisOut)
async def get_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


@router.get("/stream")
async def stream_analysis(tender_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SSE endpoint for real-time analysis progress."""
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    queue = analysis_service.subscribe(analysis.id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": msg["event"],
                        "data": json.dumps(msg["data"], ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": ""}
        finally:
            analysis_service.unsubscribe(analysis.id, queue)

    return EventSourceResponse(event_generator())


@router.post("/restart", response_model=AnalysisOut, status_code=200)
async def restart_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    """Force-restart analysis from step 0, regardless of current state."""
    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(404, "Analysis not found — use /start first")

    # Reset all fields
    existing.status = "running"
    existing.current_step = 0
    existing.error_message = None
    existing.step0_result = None
    existing.step0_eligible = None
    existing.step0_fix_actions = None
    existing.user_decision = None
    existing.step1_result = None
    existing.step2_result = None
    existing.step3_result = None
    existing.step4_result = None
    existing.step5_result = None
    tender.status = "analyzing"
    await db.commit()
    await db.refresh(existing)

    await analysis_service.launch_step(existing.id, 0)
    return existing


@router.post("/fix-eligibility", response_model=AnalysisOut)
async def fix_eligibility(
    tender_id: int,
    data: FixEligibilityRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    analysis.step0_fix_actions = data.fix_actions
    analysis.status = "running"
    await db.commit()
    await db.refresh(analysis)

    # Re-run step 0 with fix context
    await analysis_service.launch_step(analysis.id, 0)

    return analysis


@router.post("/decision", response_model=AnalysisOut)
async def submit_decision(
    tender_id: int,
    data: DecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    if data.decision not in ("go", "no_go"):
        raise HTTPException(400, "Decision must be 'go' or 'no_go'")

    analysis.user_decision = data.decision
    if data.decision == "no_go":
        analysis.status = "completed"
        tender = await db.get(Tender, tender_id)
        if tender:
            tender.status = "rejected"
        await db.commit()
    else:
        analysis.status = "running"
        analysis.current_step = 1
        await db.commit()
        # Launch steps 1-5 sequentially in background
        await analysis_service.launch_remaining_steps(analysis.id, 1)

    await db.refresh(analysis)
    return analysis


@router.post("/continue", response_model=AnalysisOut)
async def continue_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    if analysis.current_step >= 5:
        raise HTTPException(400, "Analysis already completed")

    next_step = analysis.current_step + 1
    analysis.current_step = next_step
    analysis.status = "running"
    await db.commit()
    await db.refresh(analysis)

    # Launch next step
    await analysis_service.launch_step(analysis.id, next_step)

    return analysis


@router.get("/documents", response_model=list[AnalysisDocumentOut])
async def list_documents(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    docs_result = await db.execute(
        select(AnalysisDocument)
        .where(AnalysisDocument.analysis_id == analysis.id)
        .order_by(AnalysisDocument.order_index)
    )
    return docs_result.scalars().all()


@router.put("/documents/{doc_id}", response_model=AnalysisDocumentOut)
async def toggle_document(
    tender_id: int, doc_id: int, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AnalysisDocument).where(AnalysisDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    doc.is_completed = not doc.is_completed
    await db.commit()
    await db.refresh(doc)
    return doc
