import os
import sys
import tempfile
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient

@pytest.fixture()
def client():
    # Each test gets a fresh SQLite file and freshly initialized demo users.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    # Reload modules so the engine uses this test database.
    import app.database as database
    import app.models as models
    import app.main as main
    database.engine.dispose()
    database.DATABASE_URL = os.environ["DATABASE_URL"]
    database.engine = database.create_engine(database.DATABASE_URL, connect_args={"check_same_thread": False}, future=True)
    database.SessionLocal.configure(bind=database.engine)
    main.engine = database.engine
    main.Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as db:
        for uid, name in [("alice", "Demo Requester Alice"), ("bob", "Demo Trusted Contact Bob"), ("carol", "Demo Unrelated User Carol")]:
            db.add(models.DemoUser(id=uid, display_name=name))
        db.commit()
    with TestClient(main.app) as test_client:
        yield test_client
    database.engine.dispose()
    try:
        os.unlink(path)
    except OSError:
        pass

@pytest.fixture()
def create_payload():
    from datetime import datetime, timedelta, timezone
    return {
        "approver_id": "bob",
        "amount_minor": 2500000,
        "currency": "INR",
        "payee": "Demo recipient",
        "purpose": "Emergency travel",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    }
