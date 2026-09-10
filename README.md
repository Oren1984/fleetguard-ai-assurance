# FleetGuard AI — AI-Assisted Cold-Chain Risk & Incident Response

A lean proof-of-concept showing how AI can watch a fleet of refrigerated
trucks, explain *why* a shipment is at risk, ground that explanation in
retrieved company procedure, recommend one of a small set of actions, and
require a human to approve anything consequential before it happens.

## Business problem

A logistics company runs refrigerated ("reefer") trucks. Temperature
deviations, extreme weather, or route delays can spoil cargo, trigger
insurance claims, and cost real money. Fleet operators need one question
answered continuously:

> **Which shipments are currently at high risk of spoilage, why, and what
> action is recommended?**

FleetGuard AI answers that question end-to-end: ingest → detect → explain →
recommend → **require human approval** → execute → audit.

## What's actually in this POC

- A rule-based, fully explainable **risk engine** (no black-box ML) that
  scores cargo temperature deviation, temperature trend, extreme external
  heat, and route delay into a 0–100 risk score and LOW/MEDIUM/HIGH level.
- A small local **RAG** layer (TF-IDF + cosine similarity, scikit-learn)
  over 5 markdown SOP documents, so every recommendation cites the actual
  procedure it follows — not a hallucinated one.
- A **replaceable LLM provider** (`mock` / `openai` / `anthropic`) for the
  natural-language explanation, with a **grounding validator** that rejects
  any explanation not tied to the real evidence and falls back to the fixed
  string `"Insufficient Evidence"` rather than ever fabricating an answer.
- A **human-in-the-loop approval gate**: route changes and diversions cannot
  execute until an operator approves them. Attempting to execute without
  approval is blocked and audited.
- A **kill switch** that halts all agent operations (new assessments and
  action execution) instantly.
- A complete **audit trail** of every assessment, decision, and execution.
- **Prometheus metrics**, **structured JSON logs**, and a `/health` endpoint.
- A **Streamlit dashboard** for fleet overview, truck drill-down, the
  approval queue, and the audit trail.

## Primary demo scenario

Truck `TRK-014` is seeded with cargo temperature climbing gradually from
4°C to 10°C while it's in an extreme-heat region and experiencing a 45–50
minute route delay. The system:

1. Detects the deviation and rising trend from telemetry.
2. Shows the exact data behind the decision (temperatures, trend, weather,
   delay — each with its point contribution to the score).
3. Classifies the shipment **HIGH risk** (score ~90+/100).
4. Retrieves the matching SOP section (`01_temperature_deviation.md`).
5. Recommends **diverting to the nearest approved refrigerated facility**
   (looked up from `04_diversion_facilities.md`).
6. Opens a **PENDING** human approval — execution is blocked until approved.
7. Once approved, executes the action and records the full chain
   (assessment → approval → execution) in the audit trail.

## Technology stack

Python · FastAPI · Streamlit · PostgreSQL · Docker Compose · Pytest ·
GitHub Actions · Prometheus · Grafana · structured JSON logging · scikit-learn
(local TF-IDF RAG) · a pluggable LLM provider with a full mock mode.

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

That single command:
- starts PostgreSQL, the FastAPI backend, the Streamlit dashboard,
  Prometheus, and Grafana,
- auto-generates 25 synthetic trucks (including the demo truck) and their
  telemetry history,
- runs the risk engine over every truck so the dashboard has data
  immediately.

No API key is required — `LLM_PROVIDER=mock` (the default) produces fully
grounded explanations built directly from the evidence and retrieved SOP
text, with zero external calls.

| Service     | URL                              |
|-------------|-----------------------------------|
| Dashboard   | http://localhost:8501             |
| Backend API | http://localhost:8000/docs        |
| Health      | http://localhost:8000/health      |
| Metrics     | http://localhost:8000/metrics     |
| Prometheus  | http://localhost:9090             |
| Grafana     | http://localhost:3000 (admin/admin, or anonymous viewer) |

### Try the demo scenario

1. Open the dashboard → **Truck Detail** tab → it defaults to `TRK-014`
   (marked "🎬 Primary demo scenario truck").
2. Review the temperature chart, the evidence bullets, the AI explanation,
   and the cited SOP sections.
3. Go to **Approval Queue**, approve the pending diversion, then execute it.
4. Check the **Audit Trail** tab — `risk_assessment_generated` →
   `approval_approved` → `action_executed`, all present.
5. Try the **Kill Switch** in the sidebar: engage it, then try to run a new
   assessment or execute an approval — both are blocked (HTTP 423).

### Run the backend directly (without Docker)

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
DATABASE_URL=sqlite:///./fleetguard.db uvicorn app.main:app --reload
```

### Run the tests

```bash
cd backend
pip install -r requirements.txt
pytest -q                       # 43 tests: risk scoring, data validation,
                                 # weather failure handling, RAG, grounding,
                                 # approval gate, audit trail, kill switch,
                                 # and a full end-to-end happy path.
pytest --cov=app --cov-report=term-missing   # with coverage
```

Tests run against an in-memory SQLite database and `LLM_PROVIDER=mock` —
no Docker, database server, or API key required.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components and data flow.
- [`docs/ASSURANCE.md`](docs/ASSURANCE.md) — guardrails, grounding, HITL,
  kill switch, and the QA test matrix.

## POC limitations (by design)

This is a portfolio-grade proof of concept, not a production system:

- Synthetic data only — no real telematics, weather API, or maps integration.
- Rule-based risk scoring, not a trained ML model (this is deliberate: every
  point on the score is explainable and auditable).
- Single backend service, single database, one Streamlit UI — no
  microservices, no Kubernetes, no multi-tenancy, no mobile app.
- No enterprise auth — actor identity for approvals/audit is a free-text
  field, not an authenticated user system.
- TF-IDF retrieval, not a hosted embeddings/vector database — appropriate
  for 5 SOP documents, not thousands.

See `docs/ASSURANCE.md` for the full guardrail and testing rationale.
