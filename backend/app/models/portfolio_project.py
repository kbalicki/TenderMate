from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_profile_id: Mapped[int] = mapped_column(ForeignKey("company_profiles.id"))

    project_name: Mapped[str] = mapped_column(String(500))
    client_name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    contract_value_pln: Mapped[int | None] = mapped_column(Integer)
    year_started: Mapped[int | None] = mapped_column(Integer)
    year_completed: Mapped[int | None] = mapped_column(Integer)
    technologies_used: Mapped[dict | list | None] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    company_profile: Mapped["CompanyProfile"] = relationship(back_populates="portfolio_projects")  # noqa: F821
