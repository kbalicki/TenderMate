from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.company_profile import CompanyProfile
from app.models.team_member import TeamMember
from app.models.portfolio_project import PortfolioProject
from app.schemas.company_profile import (
    CompanyProfileOut,
    CompanyProfileUpdate,
    TeamMemberCreate,
    TeamMemberOut,
    PortfolioProjectCreate,
    PortfolioProjectOut,
)

router = APIRouter(prefix="/company-profile", tags=["company-profile"])


async def _get_or_create_profile(db: AsyncSession) -> CompanyProfile:
    result = await db.execute(
        select(CompanyProfile)
        .options(selectinload(CompanyProfile.team_members), selectinload(CompanyProfile.portfolio_projects))
        .where(CompanyProfile.user_id == 1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = CompanyProfile(user_id=1)
        db.add(profile)
        await db.commit()
        await db.refresh(profile, ["team_members", "portfolio_projects"])
    return profile


@router.get("", response_model=CompanyProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db)):
    return await _get_or_create_profile(db)


@router.put("", response_model=CompanyProfileOut)
async def update_profile(
    data: CompanyProfileUpdate, db: AsyncSession = Depends(get_db)
):
    profile = await _get_or_create_profile(db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile, ["team_members", "portfolio_projects"])
    return profile


# --- Team Members ---


@router.get("/team", response_model=list[TeamMemberOut])
async def list_team(db: AsyncSession = Depends(get_db)):
    profile = await _get_or_create_profile(db)
    return profile.team_members


@router.post("/team", response_model=TeamMemberOut, status_code=201)
async def add_team_member(
    data: TeamMemberCreate, db: AsyncSession = Depends(get_db)
):
    profile = await _get_or_create_profile(db)
    member = TeamMember(company_profile_id=profile.id, **data.model_dump())
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.put("/team/{member_id}", response_model=TeamMemberOut)
async def update_team_member(
    member_id: int, data: TeamMemberCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TeamMember).where(TeamMember.id == member_id))
    member = result.scalar_one()
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(member, key, value)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/team/{member_id}", status_code=204)
async def delete_team_member(member_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamMember).where(TeamMember.id == member_id))
    member = result.scalar_one()
    await db.delete(member)
    await db.commit()


# --- Portfolio Projects ---


@router.get("/portfolio", response_model=list[PortfolioProjectOut])
async def list_portfolio(db: AsyncSession = Depends(get_db)):
    profile = await _get_or_create_profile(db)
    return profile.portfolio_projects


@router.post("/portfolio", response_model=PortfolioProjectOut, status_code=201)
async def add_portfolio_project(
    data: PortfolioProjectCreate, db: AsyncSession = Depends(get_db)
):
    profile = await _get_or_create_profile(db)
    project = PortfolioProject(company_profile_id=profile.id, **data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.put("/portfolio/{project_id}", response_model=PortfolioProjectOut)
async def update_portfolio_project(
    project_id: int, data: PortfolioProjectCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PortfolioProject).where(PortfolioProject.id == project_id)
    )
    project = result.scalar_one()
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/portfolio/{project_id}", status_code=204)
async def delete_portfolio_project(
    project_id: int, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PortfolioProject).where(PortfolioProject.id == project_id)
    )
    project = result.scalar_one()
    await db.delete(project)
    await db.commit()
