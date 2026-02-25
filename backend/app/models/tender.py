from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)

    source_type: Mapped[str] = mapped_column(String(20))  # "url" or "manual"
    source_url: Mapped[str | None] = mapped_column(String(2000))
    portal_name: Mapped[str | None] = mapped_column(String(100))

    title: Mapped[str | None] = mapped_column(String(1000))
    contracting_authority: Mapped[str | None] = mapped_column(String(500))
    reference_number: Mapped[str | None] = mapped_column(String(255))
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime)
    tender_text: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)

    authority_type: Mapped[str | None] = mapped_column(String(20))  # "public" or "private"

    status: Mapped[str] = mapped_column(String(50), default="new")
    error_message: Mapped[str | None] = mapped_column(Text)
    data_dir: Mapped[str | None] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="tenders")  # noqa: F821
    attachments: Mapped[list["TenderAttachment"]] = relationship(  # noqa: F821
        back_populates="tender", cascade="all, delete-orphan"
    )
    analysis: Mapped["Analysis | None"] = relationship(  # noqa: F821
        back_populates="tender", uselist=False, cascade="all, delete-orphan"
    )
