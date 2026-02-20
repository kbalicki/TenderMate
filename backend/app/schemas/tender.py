from datetime import datetime

from pydantic import BaseModel


class TenderAttachmentOut(BaseModel):
    id: int
    filename: str
    file_size_bytes: int | None = None
    mime_type: str | None = None
    model_config = {"from_attributes": True}


class TenderCreate(BaseModel):
    title: str | None = None
    tender_text: str | None = None


class TenderFromUrl(BaseModel):
    urls: list[str]


class TenderOut(BaseModel):
    id: int
    source_type: str
    source_url: str | None = None
    portal_name: str | None = None
    title: str | None = None
    contracting_authority: str | None = None
    reference_number: str | None = None
    submission_deadline: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class TenderDetailOut(TenderOut):
    tender_text: str | None = None
    attachments: list[TenderAttachmentOut] = []
    model_config = {"from_attributes": True}
