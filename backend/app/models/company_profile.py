from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)

    company_name: Mapped[str] = mapped_column(String(500), default="")
    nip: Mapped[str | None] = mapped_column(String(20))
    regon: Mapped[str | None] = mapped_column(String(20))
    krs: Mapped[str | None] = mapped_column(String(20))

    address_street: Mapped[str | None] = mapped_column(String(500))
    address_city: Mapped[str | None] = mapped_column(String(255))
    address_postal_code: Mapped[str | None] = mapped_column(String(20))
    address_country: Mapped[str] = mapped_column(String(100), default="Polska")

    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)

    technologies: Mapped[dict | list | None] = mapped_column(JSON, default=list)
    certifications: Mapped[dict | list | None] = mapped_column(JSON, default=list)

    preferences_min_budget: Mapped[int | None] = mapped_column(Integer)
    preferences_max_budget: Mapped[int | None] = mapped_column(Integer)
    preferences_categories: Mapped[dict | list | None] = mapped_column(JSON, default=list)
    preferences_excluded_keywords: Mapped[dict | list | None] = mapped_column(JSON, default=list)

    hourly_rate_pln: Mapped[int] = mapped_column(Integer, default=200)
    qa_buffer_pct: Mapped[int] = mapped_column(Integer, default=20)
    risk_buffer_pct: Mapped[int] = mapped_column(Integer, default=20)

    bank_account: Mapped[str | None] = mapped_column(String(100))
    contact_person: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="company_profiles")  # noqa: F821
    team_members: Mapped[list["TeamMember"]] = relationship(  # noqa: F821
        back_populates="company_profile", cascade="all, delete-orphan"
    )
    portfolio_projects: Mapped[list["PortfolioProject"]] = relationship(  # noqa: F821
        back_populates="company_profile", cascade="all, delete-orphan"
    )
