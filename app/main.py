import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Base, engine, get_db, SessionLocal
from .models import DemoUser, RequestEvent
from .schemas import RequestCreate, RequestPatch, DecisionInput, RequestOut, EventOut
from . import services

def initialize_database():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        demo_users = [
            ("alice", "Demo Requester Alice"),
            ("bob", "Demo Trusted Contact Bob"),
            ("carol", "Demo Unrelated User Carol"),
        ]
        for user_id, name in demo_users:
            if not db.get(DemoUser, user_id):
                db.add(DemoUser(id=user_id, display_name=name))
        db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="SecondSignal Backend API",
    description="Demo verification workflow. X-Demo-User is a prototype-only identity header, not real authentication.",
    version="1.0.0",
    lifespan=lifespan,
)
raw_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
for default_origin in ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]:
    if default_origin not in allowed_origins:
        allowed_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-User"],
)

def current_actor(x_demo_user: str | None = Header(default=None, alias="X-Demo-User")):
    if not x_demo_user:
        raise HTTPException(401, "Missing X-Demo-User header. Demo identities: alice, bob, carol.")
    return x_demo_user

@app.get("/health")
def health():
    return {"status": "ok", "service": "secondsignal-backend"}

@app.get("/api/demo-users")
def demo_users(db: Session = Depends(get_db)):
    return [{"id": u.id, "display_name": u.display_name}
            for u in db.scalars(select(DemoUser).order_by(DemoUser.id)).all()]

@app.post("/api/requests", response_model=RequestOut, status_code=201)
def create_verification_request(data: RequestCreate, actor: str = Depends(current_actor),
                                db: Session = Depends(get_db)):
    return services.create_request(db, actor, data)

@app.get("/api/requests", response_model=list[RequestOut])
def get_requests(actor: str = Depends(current_actor), db: Session = Depends(get_db)):
    return services.list_requests(db, actor)

@app.get("/api/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: str, actor: str = Depends(current_actor), db: Session = Depends(get_db)):
    return services.read_request(db, actor, request_id)

@app.post("/api/requests/{request_id}/approve", response_model=RequestOut)
def approve_request(request_id: str, data: DecisionInput, actor: str = Depends(current_actor),
                    db: Session = Depends(get_db)):
    return services.decide(db, actor, request_id, data, "APPROVED")

@app.post("/api/requests/{request_id}/deny", response_model=RequestOut)
def deny_request(request_id: str, data: DecisionInput, actor: str = Depends(current_actor),
                 db: Session = Depends(get_db)):
    return services.decide(db, actor, request_id, data, "DENIED")

@app.patch("/api/requests/{request_id}", response_model=RequestOut)
def edit_request(request_id: str, data: RequestPatch, actor: str = Depends(current_actor),
                 db: Session = Depends(get_db)):
    return services.patch_request(db, actor, request_id, data)

@app.get("/api/requests/{request_id}/events", response_model=list[EventOut])
def get_events(request_id: str, actor: str = Depends(current_actor), db: Session = Depends(get_db)):
    req = services.read_request(db, actor, request_id)
    events = db.scalars(select(RequestEvent).where(
        RequestEvent.request_id == req.id
    ).order_by(RequestEvent.timestamp_utc.asc(), RequestEvent.id.asc())).all()
    return [{
        "id": e.id, "request_id": e.request_id, "event_type": e.event_type,
        "actor_id": e.actor_id, "request_version": e.request_version,
        "timestamp_utc": e.timestamp_utc,
        "metadata": json.loads(e.metadata_json or "{}")
    } for e in events]
