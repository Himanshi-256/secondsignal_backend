def headers(user):
    return {"X-Demo-User": user}

def create_request(client, payload):
    response = client.post("/api/requests", headers=headers("alice"), json=payload)
    assert response.status_code == 201, response.text
    return response.json()

def test_health(client):
    assert client.get("/health").json()["status"] == "ok"

def test_create_persists_and_logs_event(client, create_payload):
    req = create_request(client, create_payload)
    assert req["status"] == "PENDING"
    assert req["version"] == 1
    events = client.get(f'/api/requests/{req["id"]}/events', headers=headers("alice"))
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "request_created"

def test_invalid_amount_rejected(client, create_payload):
    create_payload["amount_minor"] = 0
    assert client.post("/api/requests", headers=headers("alice"), json=create_payload).status_code == 422

def test_wrong_approver_cannot_decide(client, create_payload):
    req = create_request(client, create_payload)
    response = client.post(f'/api/requests/{req["id"]}/approve',
                           headers=headers("carol"), json={"expected_version": 1})
    assert response.status_code == 403

def test_approve_once_and_reject_second_decision(client, create_payload):
    req = create_request(client, create_payload)
    url = f'/api/requests/{req["id"]}/approve'
    first = client.post(url, headers=headers("bob"), json={"expected_version": 1})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "APPROVED"
    second = client.post(url, headers=headers("bob"), json={"expected_version": 1})
    assert second.status_code == 409

def test_deny_request(client, create_payload):
    req = create_request(client, create_payload)
    response = client.post(f'/api/requests/{req["id"]}/deny',
                           headers=headers("bob"), json={"expected_version": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "DENIED"

def test_approved_request_change_invalidates_approval(client, create_payload):
    req = create_request(client, create_payload)
    approved = client.post(f'/api/requests/{req["id"]}/approve',
                           headers=headers("bob"), json={"expected_version": 1})
    assert approved.status_code == 200
    changed = client.patch(f'/api/requests/{req["id"]}', headers=headers("alice"),
                           json={"amount_minor": 3000000})
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "PENDING"
    assert changed.json()["version"] == 2
    assert changed.json()["decision_by"] is None
    event_types = [e["event_type"] for e in client.get(
        f'/api/requests/{req["id"]}/events', headers=headers("alice")).json()]
    assert "approval_invalidated" in event_types

def test_unauthorized_user_cannot_read_history(client, create_payload):
    req = create_request(client, create_payload)
    response = client.get(f'/api/requests/{req["id"]}/events', headers=headers("carol"))
    assert response.status_code == 403

def test_stale_version_rejected(client, create_payload):
    req = create_request(client, create_payload)
    response = client.post(f'/api/requests/{req["id"]}/approve',
                           headers=headers("bob"), json={"expected_version": 2})
    assert response.status_code == 409

def test_expired_request_cannot_be_approved(client, create_payload):
    from datetime import datetime, timedelta, timezone
    create_payload["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    response = client.post("/api/requests", headers=headers("alice"), json=create_payload)
    assert response.status_code == 400
