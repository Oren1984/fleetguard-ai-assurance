# Architecture

## Components

```
                         ┌─────────────────────┐
                         │   Streamlit UI       │  :8501
                         │   (dashboard/app.py)  │
                         └──────────┬────────────┘
                                    │ HTTP (REST/JSON)
                                    ▼
┌───────────────────────────────────────────────────────────┐
│                    FastAPI backend  :8000                   │
│                                                               │
│  routers/  → trucks, risk, approvals, audit, admin, health   │
│                                                               │
│  synthetic_data.py → seed.py  (startup, idempotent)           │
│                                                               │
│  assessment_service.py                                       │
│     risk_engine.assess()      ── explainable 0-100 score      │
│     rag.SopIndex.search()     ── TF-IDF retrieval over SOPs   │
│     llm_provider.generate_explanation()  ── mock/openai/      │
│                                              anthropic + guard │
│     facilities.facility_for_region()  ── diversion lookup     │
│                                                               │
│  approval_service.py  ── HITL decision + gated execution      │
│  kill_switch.py       ── global halt                          │
│  audit.py              ── every consequential action logged   │
│  metrics.py             ── Prometheus counters/gauges/hist.    │
└───────────────┬───────────────────────────┬─────────────────┘
                │ SQLAlchemy                 │ /metrics
                ▼                             ▼
        ┌───────────────┐             ┌───────────────┐
        │  PostgreSQL    │             │  Prometheus    │ :9090
        └───────────────┘             └───────┬────────┘
                                                ▼
                                         ┌───────────────┐
                                         │   Grafana      │ :3000
                                         └───────────────┘
```

## Data flow: one assessment

1. **Ingest** — synthetic telemetry (cargo temp, external temp, humidity,
   position, speed, route delay) is generated per truck and stored in
   `telemetry_readings`. In production this would be replaced by a real
   telematics feed; the ingestion boundary (`TelemetryReading` rows) is
   unchanged either way.
2. **Detect & score** — `risk_engine.assess()` takes the latest reading plus
   recent history for a truck and computes:
   - a **temperature component** (deviation from setpoint + rising trend),
   - a **weather component** (extreme external heat, excluded entirely and
     flagged if weather data is unavailable — never fabricated),
   - a **route delay component**,
   each contributing an explicit, capped number of points to a 0–100 score.
   The score is classified LOW / MEDIUM / HIGH against configurable
   thresholds (`RISK_LEVEL_MEDIUM_THRESHOLD` / `RISK_LEVEL_HIGH_THRESHOLD`).
3. **Retrieve** — `rag.build_query()` turns the risk factors + classification
   into a short retrieval query; `SopIndex.search()` runs TF-IDF + cosine
   similarity over the 5 SOP markdown documents (chunked by `## Section`) and
   returns the top matches above a minimum similarity threshold. Below that
   threshold, nothing is returned rather than a weak, misleading match.
4. **Explain** — `llm_provider.generate_explanation()` builds a natural
   language explanation from the evidence + retrieved SOP text (mock mode:
   a deterministic template; real mode: a strict prompt sent to OpenAI or
   Anthropic). Every explanation — mock or real — is passed through
   `validate_grounding()`, which rejects text that doesn't engage with the
   actual measured values. A rejected explanation is replaced with the fixed
   string `"Insufficient Evidence"`; the system never presents fabricated
   analysis as if it were grounded.
5. **Recommend** — the risk level deterministically maps to one of three
   actions: `CONTINUE_JOURNEY` (LOW, no approval needed), `CHANGE_ROUTE`
   (MEDIUM), or `DIVERT_TO_FACILITY` (HIGH, with a facility looked up from
   the truck's region against the approved facility list in
   `facilities.py` / SOP-04).
6. **Persist & gate** — the `RiskAssessment` row is written. If the action
   requires approval, an `Approval` row is opened in `PENDING` state. Nothing
   is executed yet.
7. **Human decision** — an operator approves or rejects via the dashboard or
   `POST /approvals/{id}/decision`.
8. **Execute** — `POST /approvals/{id}/execute` runs `approval_service.
   execute_action()`, which re-checks the kill switch and the approval
   status before creating an `ActionExecution` row. Any attempt to execute
   without `APPROVED` status, or while the kill switch is engaged, is
   refused (403 / 423) and audited.
9. **Audit** — every step above writes an `AuditLog` row (event type, actor,
   truck, structured details) through the single `audit.record()` helper, so
   the audit trail is the one place a reviewer needs to look.

## Why rule-based scoring, not ML

The risk score is a deterministic function of documented thresholds (see
`risk_engine.py`), not a trained model. For a cold-chain assurance system,
being able to say *exactly* why a shipment was flagged — in points, per
factor — is more valuable than marginal accuracy gains from a model that
can't explain itself, and it removes an entire class of training/drift risk
from a POC of this scope.

## Why TF-IDF, not a hosted embeddings API

Five SOP documents is not enough content to justify a vector database or a
paid embeddings API, and it keeps the whole RAG path working with zero
external dependencies in mock mode. `SopIndex` uses `TfidfVectorizer` with
unigrams+bigrams and sublinear TF scaling — bigrams matter here because
several SOP sections share the same vocabulary (temperature, setpoint,
extreme heat, route delay) whether they describe when to act or when *not*
to act, and phrase-level matching is what actually distinguishes them (see
the tests in `backend/tests/test_rag.py`).

## Database

Single PostgreSQL instance, six tables: `trucks`, `telemetry_readings`,
`risk_assessments`, `approvals`, `action_executions`, `audit_log`, plus a
one-row `system_state` table for the kill switch. Schema is created via
`SQLAlchemy.Base.metadata.create_all()` on startup — no migration framework,
appropriate for a POC with no existing production data to migrate.

## Observability

- **Metrics** (`/metrics`, Prometheus format): risk assessments by level,
  active high-risk trucks, pending approvals, kill switch state, ungrounded
  responses blocked, action executions by outcome, blocked executions, and a
  scoring-duration histogram. Scraped by Prometheus every 10s; visualized in
  a provisioned Grafana dashboard.
- **Logs**: structured JSON to stdout (`logging_config.py`), one line per
  event, machine-parseable.
- **Health**: `/health` reports database connectivity, kill switch state,
  configured LLM provider, and current fleet size.
