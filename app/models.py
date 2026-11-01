import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utc_now():
    return datetime.now(timezone.utc)

def new_id():
    return str(uuid.uuid4())

class DemoUser(Base):
    __tablename__ = "demo_users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requester_id: Mapped[str] = mapped_column(ForeignKey("demo_users.id"), index=True)
    approver_id: Mapped[str] = mapped_column(ForeignKey("demo_users.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payee: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decision_by: Mapped[str | None] = mapped_column(ForeignKey("demo_users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    events: Mapped[list["RequestEvent"]] = relationship(back_populates="request", cascade="all, delete-orphan")

class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("verification_requests.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    request: Mapped[VerificationRequest] = relationship(back_populates="events")

Index("ix_events_request_time", RequestEvent.request_id, RequestEvent.timestamp_utc)
