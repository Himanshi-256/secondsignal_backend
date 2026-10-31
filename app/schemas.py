from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class RequestCreate(BaseModel):
    approver_id: str = Field(min_length=1, max_length=80)
    amount_minor: int = Field(gt=0, le=100_000_000)  # paise; max ₹10,00,000
    currency: Literal["INR"] = "INR"
    payee: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    expires_at: datetime

    @field_validator("payee", "purpose")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must include a timezone, e.g. +05:30 or Z")
        return value.astimezone(timezone.utc)

class DecisionInput(BaseModel):
    expected_version: int = Field(ge=1)
    decision_note: str | None = Field(default=None, max_length=300)

class RequestPatch(BaseModel):
    amount_minor: int | None = Field(default=None, gt=0, le=100_000_000)
    currency: Literal["INR"] | None = None
    payee: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    approver_id: str | None = Field(default=None, min_length=1, max_length=80)
    expires_at: datetime | None = None

    @field_validator("payee", "purpose")
    @classmethod
    def trim_patch_text(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def patch_expiry_timezone(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("expires_at must include a timezone")
            return value.astimezone(timezone.utc)
        return value

class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    requester_id: str
    approver_id: str
    amount_minor: int
    currency: str
    payee: str
    purpose: str
    status: str
    version: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    decision_by: str | None
    decided_at: datetime | None
    decision_note: str | None

class EventOut(BaseModel):
    id: str
    request_id: str
    event_type: str
    actor_id: str | None
    request_version: int
    timestamp_utc: datetime
    metadata: dict
