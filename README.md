# SecondSignal Backend

A hackathon MVP for the SecondSignal verification workflow, built with FastAPI, SQLAlchemy, SQLite, Pydantic, and pytest.

## Requirements
- Python 3.11+
- VS Code
- Python extension for VS Code

## 1. Create and activate a virtual environment

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

## 2. Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Start the API
```bash
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for Swagger UI. Health check: http://127.0.0.1:8000/health

The SQLite file `secondsignal.db` is created in the backend directory. The demo users are:
- `alice`: requester
- `bob`: assigned trusted contact in the example
- `carol`: unrelated user for authorization testing

## Demo identity warning
For easy local integration, the prototype accepts `X-Demo-User: alice` (or bob/carol). This is NOT authentication: anyone able to call the API can impersonate a demo user. Do not expose this backend publicly or use real personal/financial data. Production use requires a reviewed authentication/session system.

## API contract

All request endpoints require the `X-Demo-User` header.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/demo-users` | List synthetic demo identities |
| POST | `/api/requests` | Create request |
| GET | `/api/requests` | List requests visible to actor |
| GET | `/api/requests/{id}` | Read request |
| POST | `/api/requests/{id}/approve` | Approve as assigned contact |
| POST | `/api/requests/{id}/deny` | Deny as assigned contact |
| PATCH | `/api/requests/{id}` | Requester edits protected details |
| GET | `/api/requests/{id}/events` | Authorized event history |

Money is stored as integer paise. Example `2500000` means ₹25,000.

## Example end-to-end flow

1. Create a request as Alice in `/docs`:
```json
{
  "approver_id": "bob",
  "amount_minor": 2500000,
  "currency": "INR",
  "payee": "Demo recipient",
  "purpose": "Emergency travel",
  "expires_at": "2027-01-01T12:00:00+05:30"
}
```
Use `X-Demo-User: alice` in Swagger's Authorize/header interface (or use curl below). Use an expiry in the near future and no more than 72 hours ahead.

2. Read the request using `GET /api/requests/{id}` as Alice or Bob.
3. Approve with `X-Demo-User: bob` and body:
```json
{"expected_version": 1, "decision_note": "Confirmed through a separate channel"}
```
4. Edit the request as Alice with `PATCH /api/requests/{id}`:
```json
{"amount_minor": 3000000}
```
The version becomes 2, status returns to `PENDING`, and the previous decision is cleared.
5. Fetch `GET /api/requests/{id}/events` to inspect the event history.

## curl examples

Create request (replace expiry with a future timestamp):
```bash
curl -X POST http://127.0.0.1:8000/api/requests \
  -H 'Content-Type: application/json' -H 'X-Demo-User: alice' \
  -d '{"approver_id":"bob","amount_minor":2500000,"currency":"INR","payee":"Demo recipient","purpose":"Emergency travel","expires_at":"2027-01-01T12:00:00+05:30"}'
```

Approve (replace REQUEST_ID):
```bash
curl -X POST http://127.0.0.1:8000/api/requests/REQUEST_ID/approve \
  -H 'Content-Type: application/json' -H 'X-Demo-User: bob' \
  -d '{"expected_version":1,"decision_note":"Confirmed separately"}'
```

## Run tests
```bash
pytest -q
```
Tests use a temporary SQLite database and do not need real data.

## Important prototype limitations
- Demo identity header is not authentication.
- CORS restricts browser origins, but CORS is not an access-control/security boundary.
- This does not detect deepfakes, prove identity, integrate with UPI/banks, or guarantee a request is safe.
- Use synthetic data only.
