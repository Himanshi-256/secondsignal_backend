import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .models import DemoUser, VerificationRequest, RequestEvent, utc_now
from .schemas import RequestCreate, RequestPatch, DecisionInput

MAX_EXPIRY_HOURS = 72

def aware(dt: datetime) -> datetime:
    # SQLite may return naive datetimes even when timezone=True.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def add_event(db: Session, req: VerificationRequest, event_type: str, actor_id: str | None, metadata=None):
    db.add(RequestEvent(
        request_id=req.id, event_type=event_type, actor_id=actor_id,
        request_version=req.version, timestamp_utc=utc_now(),
        metadata_json=json.dumps(metadata or {}, separators=(",", ":"))
    ))

def get_request_or_404(db: Session, request_id: str):
    req = db.get(VerificationRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    return req

def authorize_read(req: VerificationRequest, actor_id: str):
    if actor_id not in (req.requester_id, req.approver_id):
        raise HTTPException(403, "You are not authorized to access this request")

def refresh_expiry(db: Session, req: VerificationRequest):
    if req.status == "PENDING" and aware(req.expires_at) <= utc_now():
        req.status = "EXPIRED"
        req.updated_at = utc_now()
        req.decision_by = None
        req.decided_at = None
        req.decision_note = None
        add_event(db, req, "request_expired", None)
        db.commit()
        db.refresh(req)
    return req

def validate_expiry(expires_at: datetime):
    now = utc_now()
    expiry = aware(expires_at)
    if expiry <= now:
        raise HTTPException(400, "expires_at must be in the future")
    if (expiry - now).total_seconds() > MAX_EXPIRY_HOURS * 3600:
        raise HTTPException(400, f"expires_at cannot be more than {MAX_EXPIRY_HOURS} hours ahead")

def create_request(db: Session, actor_id: str, data: RequestCreate):
    if actor_id == data.approver_id:
        raise HTTPException(400, "Requester and approver must be different demo users")
    if not db.get(DemoUser, actor_id):
        raise HTTPException(401, "Unknown demo user. Use a seeded demo identity.")
    if not db.get(DemoUser, data.approver_id):
        raise HTTPException(400, "approver_id is not a known demo user")
    validate_expiry(data.expires_at)
    req = VerificationRequest(
        requester_id=actor_id, approver_id=data.approver_id,
        amount_minor=data.amount_minor, currency=data.currency,
        payee=data.payee, purpose=data.purpose, status="PENDING",
        version=1, expires_at=data.expires_at, created_at=utc_now(),
        updated_at=utc_now()
    )
    db.add(req)
    db.flush()
    add_event(db, req, "request_created", actor_id, {"currency": req.currency})
    db.commit()
    db.refresh(req)
    return req

def list_requests(db: Session, actor_id: str):
    if not db.get(DemoUser, actor_id):
        raise HTTPException(401, "Unknown demo user. Use a seeded demo identity.")
    rows = db.scalars(select(VerificationRequest).where(
        (VerificationRequest.requester_id == actor_id) |
        (VerificationRequest.approver_id == actor_id)
    ).order_by(VerificationRequest.created_at.desc())).all()
    return [refresh_expiry(db, r) for r in rows]

def read_request(db: Session, actor_id: str, request_id: str):
    req = get_request_or_404(db, request_id)
    authorize_read(req, actor_id)
    return refresh_expiry(db, req)

def decide(db: Session, actor_id: str, request_id: str, data: DecisionInput, outcome: str):
    req = get_request_or_404(db, request_id)
    if actor_id != req.approver_id:
        raise HTTPException(403, "Only the assigned trusted contact can decide")
    req = refresh_expiry(db, req)
    if req.status == "EXPIRED":
        raise HTTPException(410, "Request has expired")
    if req.status != "PENDING":
        raise HTTPException(409, f"Request is already {req.status.lower()}")
    if data.expected_version != req.version:
        raise HTTPException(409, "Stale request version; refresh and review the current details")
    if aware(req.expires_at) <= utc_now():
        req.status = "EXPIRED"
        req.updated_at = utc_now()
        add_event(db, req, "request_expired", None)
        db.commit()
        raise HTTPException(410, "Request has expired")
    # Conditional update prevents two concurrent decisions from both succeeding.
    result = db.execute(update(VerificationRequest).where(
        VerificationRequest.id == req.id,
        VerificationRequest.status == "PENDING",
        VerificationRequest.version == data.expected_version
    ).values(status=outcome, decision_by=actor_id, decided_at=utc_now(),
             decision_note=(data.decision_note.strip() if data.decision_note else None),
             updated_at=utc_now()))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Request changed or was decided concurrently; refresh and retry")
    db.expire(req)
    db.refresh(req)
    add_event(db, req, "request_approved" if outcome == "APPROVED" else "request_denied",
              actor_id, {"note_provided": bool(data.decision_note)})
    db.commit()
    db.refresh(req)
    return req

def patch_request(db: Session, actor_id: str, request_id: str, patch: RequestPatch):
    req = get_request_or_404(db, request_id)
    if actor_id != req.requester_id:
        raise HTTPException(403, "Only the requester can edit this request")
    req = refresh_expiry(db, req)
    if req.status in ("DENIED", "EXPIRED"):
        raise HTTPException(409, f"Cannot edit a {req.status.lower()} request; create a new request")
    changes = patch.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return req
    if "approver_id" in changes and not db.get(DemoUser, changes["approver_id"]):
        raise HTTPException(400, "approver_id is not a known demo user")
    if "approver_id" in changes and changes["approver_id"] == req.requester_id:
        raise HTTPException(400, "Requester and approver must be different demo users")
    if "expires_at" in changes:
        validate_expiry(changes["expires_at"])
    changed_fields = [k for k, v in changes.items() if getattr(req, k) != v]
    if not changed_fields:
        return req
    was_decided = req.status == "APPROVED"
    for key in changed_fields:
        setattr(req, key, changes[key])
    req.version += 1
    req.updated_at = utc_now()
    req.decision_by = None
    req.decided_at = None
    req.decision_note = None
    req.status = "PENDING"
    add_event(db, req, "request_changed", actor_id, {"changed_fields": changed_fields})
    if was_decided:
        add_event(db, req, "approval_invalidated", actor_id, {"changed_fields": changed_fields})
    db.commit()
    db.refresh(req)
    return req
