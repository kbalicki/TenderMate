from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), unique=True)

    current_step: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")

    step0_result: Mapped[dict | None] = mapped_column(JSON)
    step0_eligible: Mapped[bool | None] = mapped_column(Boolean)
    step0_fix_actions: Mapped[dict | list | None] = mapped_column(JSON)
    user_decision: Mapped[str | None] = mapped_column(String(20))

    step1_result: Mapped[dict | None] = mapped_column(JSON)
    step2_result: Mapped[dict | None] = mapped_column(JSON)
    step3_result: Mapped[dict | None] = mapped_column(JSON)
    step4_result: Mapped[dict | None] = mapped_column(JSON)
    step5_result: Mapped[dict | None] = mapped_column(JSON)

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tender: Mapped["Tender"] = relationship(back_populates="analysis")  # noqa: F821
    documents: Mapped[list["AnalysisDocument"]] = relationship(  # noqa: F821
        back_populates="analysis", cascade="all, delete-orphan"
    )
