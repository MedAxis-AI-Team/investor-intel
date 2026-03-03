## Plan
- Install dependencies and set environment variables.
- Run the FastAPI server locally.
- Use the Phase 1 endpoints with `X-API-Key`.
- Run tests and coverage (80%+ required).

## Investor Intelligence API (Jerome)
Stateless FastAPI service intended to be called from N8N workflows.

### Requirements
- Python 3.12+

### Setup
```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
```

Set these env vars in `.env`:
- `API_KEY`
- `ANTHROPIC_API_KEY`

### Run
```bash
uvicorn app.main:app --reload
```

Docs UI is available at `/` (root).

### Endpoints
- `GET /health` (no auth)
- `POST /score-investors` (auth + rate limited)
- `POST /analyze-signal` (auth + rate limited)
- `POST /generate-digest` (auth + rate limited)

Example request (PowerShell):
```powershell
$headers = @{ "X-API-Key" = "your-api-key" }
$body = @{
  client = @{ name = "NovaBio"; thesis = "Diagnostics" }
  investors = @(@{ name = "Firm A" }, @{ name = "Firm B" })
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/score-investors" -Headers $headers -Body $body -ContentType "application/json"
```

### Tests
```bash
python -m pytest
coverage run -m pytest
coverage report -m
```
