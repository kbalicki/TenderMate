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


class TenderFromUrlResult(BaseModel):
    url: str
    status: str  # "created", "duplicate"
    tender_id: int
    message: str | None = None


class TenderFromUrlResponse(BaseModel):
    results: list[TenderFromUrlResult]


class TenderOut(BaseModel):
    id: int
    source_type: str
    source_url: str | None = None
    portal_name: str | None = None
    title: str | None = None
    contracting_authority: str | None = None
    authority_type: str | None = None
    reference_number: str | None = None
    submission_deadline: datetime | None = None
    status: str
    error_message: str | None = None
    ai_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class TenderDetailOut(TenderOut):
    tender_text: str | None = None
    attachments: list[TenderAttachmentOut] = []
    model_config = {"from_attributes": True}


# Extended list item with analysis summary for the table view
class AnalysisSummary(BaseModel):
    eligible: bool | None = None
    eligibility_summary: str | None = None
    go_no_go: str | None = None
    go_no_go_rationale: str | None = None
    total_net_pln: float | None = None
    scope_description: str | None = None
    analysis_status: str | None = None
    user_decision: str | None = None
    attachment_count: int = 0


class TenderListItemOut(TenderOut):
    analysis_summary: AnalysisSummary | None = None
    attachment_count: int = 0
    model_config = {"from_attributes": True}


class PaginatedTendersOut(BaseModel):
    items: list[TenderListItemOut]
    total: int
    page: int
    page_size: int
    total_pages: int
