from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AnalysisOut(BaseModel):
    id: int
    tender_id: int
    current_step: int
    status: str
    step0_result: dict | None = None
    step0_eligible: bool | None = None
    step0_fix_actions: list | None = None
    user_decision: str | None = None
    step1_result: dict | None = None
    step2_result: dict | None = None
    step3_result: dict | None = None
    step4_result: dict | None = None
    step5_result: dict | None = None
    step6_result: dict | None = None
    error_message: str | None = None
    model_config = {"from_attributes": True}


class CustomFixInput(BaseModel):
    condition_index: int
    text: str
    add_to_profile: bool = False
    add_to_portfolio: bool = False


class FixEligibilityRequest(BaseModel):
    fix_actions: list[dict[str, Any]] = []
    custom_inputs: list[CustomFixInput] = []


class DecisionRequest(BaseModel):
    decision: str  # "go" or "no_go"


class AnalysisDocumentOut(BaseModel):
    id: int
    document_name: str
    instruction: str | None = None
    suggested_text: str | None = None
    is_completed: bool = False
    order_index: int = 0
    model_config = {"from_attributes": True}


class VerificationFileOut(BaseModel):
    id: int
    original_filename: str
    file_size_bytes: int
    uploaded_at: datetime
    model_config = {"from_attributes": True}
