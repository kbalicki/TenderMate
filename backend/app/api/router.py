from fastapi import APIRouter

from app.api.company_profile import router as company_router
from app.api.tenders import router as tenders_router
from app.api.analysis import router as analysis_router

api_router = APIRouter(prefix="/api")
api_router.include_router(company_router)
api_router.include_router(tenders_router)
api_router.include_router(analysis_router)
