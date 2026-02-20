from datetime import datetime

from sqlalchemy import ForeignKey, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TenderAttachment(Base):
    __tablename__ = "tender_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"))

    filename: Mapped[str] = mapped_column(String(500))
    original_url: Mapped[str | None] = mapped_column(String(2000))
    file_path: Mapped[str] = mapped_column(String(1000))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    tender: Mapped["Tender"] = relationship(back_populates="attachments")  # noqa: F821
