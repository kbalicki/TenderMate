from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AnalysisDocument(Base):
    __tablename__ = "analysis_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))

    document_name: Mapped[str] = mapped_column(String(500))
    instruction: Mapped[str | None] = mapped_column(Text)
    suggested_text: Mapped[str | None] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    analysis: Mapped["Analysis"] = relationship(back_populates="documents")  # noqa: F821
