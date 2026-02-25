import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import get_db
from app.models.analysis import Analysis
from app.models.analysis_document import AnalysisDocument
from app.models.verification_file import VerificationFile
from app.models.tender import Tender
from app.schemas.analysis import (
    AnalysisOut,
    FixEligibilityRequest,
    DecisionRequest,
    AnalysisDocumentOut,
    VerificationFileOut,
)
from app.services import analysis_service
from app.services.claude_service import _extract_text_from_file

router = APIRouter(prefix="/tenders/{tender_id}/analysis", tags=["analysis"])


@router.post("/start", response_model=AnalysisOut, status_code=201)
async def start_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.status == "failed":
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
            existing.step6_result = None
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
    existing.step6_result = None
    tender.status = "analyzing"

    # Delete old verification files
    vf_result = await db.execute(
        select(VerificationFile).where(VerificationFile.analysis_id == existing.id)
    )
    for vf in vf_result.scalars().all():
        await db.delete(vf)

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

    # Build combined fix context from radio selections + custom text inputs
    all_fix_actions = list(data.fix_actions)
    for ci in data.custom_inputs:
        all_fix_actions.append({
            "condition_index": ci.condition_index,
            "custom_text": ci.text,
            "add_to_profile": ci.add_to_profile,
            "add_to_portfolio": ci.add_to_portfolio,
        })

    # Enrich company profile if requested
    for ci in data.custom_inputs:
        if ci.text.strip() and (ci.add_to_profile or ci.add_to_portfolio):
            await analysis_service.enrich_profile_from_text(
                text=ci.text,
                add_to_portfolio=ci.add_to_portfolio,
            )

    analysis.step0_fix_actions = all_fix_actions
    analysis.status = "running"
    await db.commit()
    await db.refresh(analysis)

    await analysis_service.launch_step(analysis.id, 0)
    return analysis


@router.post("/cancel", response_model=AnalysisOut)
async def cancel_analysis(
    tender_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    await analysis_service.cancel_analysis(analysis.id)
    await db.refresh(analysis)
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
        raise HTTPException(400, "Analysis already completed — use /verify for step 6")

    next_step = analysis.current_step + 1
    analysis.current_step = next_step
    analysis.status = "running"
    await db.commit()
    await db.refresh(analysis)

    await analysis_service.launch_step(analysis.id, next_step)
    return analysis


@router.post("/verify", response_model=AnalysisOut)
async def verify_documents(
    tender_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload prepared offer documents for AI verification (step 6)."""
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found — run analysis first")

    if not analysis.step5_result:
        raise HTTPException(400, "Complete steps 0-5 before verification")

    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    # Save files and extract text
    data_dir = Path(tender.data_dir) if tender.data_dir else settings.data_dir / "tenders" / str(tender_id)
    verify_dir = data_dir / "verification"
    verify_dir.mkdir(parents=True, exist_ok=True)

    # Delete old verification files for this analysis
    old_vf = await db.execute(
        select(VerificationFile).where(VerificationFile.analysis_id == analysis.id)
    )
    for vf in old_vf.scalars().all():
        await db.delete(vf)

    uploaded = []
    for f in files:
        content = await f.read()
        filepath = verify_dir / f.filename
        filepath.write_bytes(content)

        text = _extract_text_from_file(filepath)
        if text and len(text) > 50_000:
            text = text[:50_000] + "\n[...obcięto ze względu na długość...]"

        vf = VerificationFile(
            analysis_id=analysis.id,
            original_filename=f.filename,
            stored_path=str(filepath),
            file_size_bytes=len(content),
            extracted_text=text,
        )
        db.add(vf)
        uploaded.append({
            "filename": f.filename,
            "content": text or "(nie udało się wyekstrahować tekstu z tego pliku)",
        })

    analysis.status = "running"
    analysis.current_step = 6
    analysis.step6_result = None
    await db.commit()
    await db.refresh(analysis)

    # Launch verification in background
    await analysis_service.run_verification(analysis.id, uploaded)

    return analysis


@router.get("/verification-files", response_model=list[VerificationFileOut])
async def list_verification_files(tender_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    vf_result = await db.execute(
        select(VerificationFile)
        .where(VerificationFile.analysis_id == analysis.id)
        .order_by(VerificationFile.uploaded_at)
    )
    return vf_result.scalars().all()


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
