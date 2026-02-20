from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/tenders/{tender_id}/analysis", tags=["analysis"])


@router.post("/start", response_model=AnalysisOut, status_code=201)
async def start_analysis(tender_id: int, db: AsyncSession = Depends(get_db)):
    tender = await db.get(Tender, tender_id)
    if not tender:
        raise HTTPException(404, "Tender not found")

    # Check if analysis already exists
    result = await db.execute(
        select(Analysis).where(Analysis.tender_id == tender_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    analysis = Analysis(tender_id=tender_id, current_step=0, status="pending")
    db.add(analysis)
    tender.status = "analyzing"
    await db.commit()
    await db.refresh(analysis)

    # TODO: Launch background analysis task via analysis_service
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

    # TODO: Re-run step 0 with fix context
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
    else:
        analysis.current_step = 1
        analysis.status = "running"
        # TODO: Continue analysis from step 1

    await db.commit()
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

    analysis.current_step += 1
    analysis.status = "running"
    await db.commit()
    await db.refresh(analysis)

    # TODO: Run next step via analysis_service
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
