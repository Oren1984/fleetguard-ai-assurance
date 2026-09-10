# Assurance: Guardrails, Grounding, HITL, Kill Switch, and Testing

This document exists because a cold-chain risk system that recommends
diverting a truck is only trustworthy if you can point to exactly why it
made that call, prove nothing executes without a human saying yes, and stop
it instantly if it misbehaves. This is where that evidence lives.

## 1. Explainability

Every `RiskAssessment` stores:
- `risk_score` (0–100) and `risk_level` (LOW/MEDIUM/HIGH),
- `reasons`: a list of `{factor, value, detail, score_contribution}` —
  the exact data and point contribution behind the number,
- `evidence_snapshot`: the raw inputs (cargo temp, setpoint, external temp,
  route delay, weather availability) the score was computed from,
- `sop_sources`: which SOP document/section was retrieved and its
  similarity score,
- `explanation`: the natural-language summary, and `grounded`: whether it
  passed the grounding check.

Nothing is scored or explained "because the model said so" — every number
traces back to `risk_engine.py`, which is plain, documented, testable
arithmetic (see `docs/ARCHITECTURE.md` → "Why rule-based scoring, not ML").

## 2. Grounding — never fabricate

`llm_provider.validate_grounding()` runs on every generated explanation
(mock or real provider) before it's persisted:
- empty output fails,
- output must reference the actual measured cargo temperature,
- if risk factors were found, the explanation must engage with at least one
  of them.

If validation fails, the system substitutes the fixed string
**`"Insufficient Evidence"`** and marks `grounded=False` — it does not
retry with looser rules, and it does not show the rejected text to the user.
The same applies when SOP retrieval finds nothing above the similarity
threshold (`SOP_MIN_SIMILARITY`, default 0.08): the assessment proceeds with
an empty `sop_sources` list rather than inventing a citation.

Real-provider failures (network error, missing key, non-2xx response) are
caught and degrade to `"Insufficient Evidence"` rather than crashing the
pipeline or silently scoring without an explanation.

## 3. Human-in-the-loop (HITL)

Action → approval requirement:

| Risk level | Recommended action   | Approval required? |
|------------|-----------------------|---------------------|
| LOW        | Continue journey       | No                  |
| MEDIUM     | Change route           | Yes                 |
| HIGH       | Divert to facility     | Yes                 |

When approval is required, an `Approval` row is opened `PENDING` at the same
time as the assessment — no action is taken yet. `POST
/approvals/{id}/execute`:
1. Refuses (423) if the kill switch is engaged.
2. Refuses (403, `ApprovalRequiredError`) unless `Approval.status ==
   APPROVED`.
3. Only then creates the `ActionExecution` row.

Both refusal paths write an audit entry (`execution_blocked_no_approval` /
`execution_blocked_kill_switch`) before raising, so a blocked attempt is
itself part of the trail, not silent.

## 4. Kill switch

A single-row `system_state` table holds `kill_switch_engaged`. Every entry
point that performs agent work checks it first:
- `assessment_service.run_assessment()` → `kill_switch.assert_not_engaged()`
  before scoring a new reading.
- `approval_service.execute_action()` → same check before executing.

Engaging or disengaging (`POST /admin/kill-switch`) is itself audited
(`kill_switch_engaged` / `kill_switch_disengaged`) and exposed as a
Prometheus gauge (`fleetguard_kill_switch_engaged`). It is also a one-click
toggle in the dashboard sidebar for the demo.

## 5. Audit trail

`audit.record()` is the single write path for the `audit_log` table — every
consequential action goes through it:
`risk_assessment_generated`, `approval_approved` / `approval_rejected`,
`execution_blocked_no_approval`, `execution_blocked_kill_switch`,
`action_executed`, `kill_switch_engaged` / `kill_switch_disengaged`,
`synthetic_data_loaded`. There is no update or delete endpoint for audit
entries — the log is append-only by construction (no route exists to
mutate it).

## 6. Test matrix (`backend/tests/`, 43 tests)

| Requirement                                   | Test file                     |
|------------------------------------------------|--------------------------------|
| Risk score calculation (LOW/MEDIUM/HIGH, each factor) | `test_risk_engine.py`   |
| Missing / invalid / out-of-range data           | `test_risk_engine.py`, `test_data_validation.py` |
| Temperature anomalies (deviation + trend)       | `test_risk_engine.py`          |
| Weather API failure                             | `test_weather_failure.py`      |
| SOP document not found / empty directory        | `test_rag.py`                  |
| Ungrounded AI responses rejected                | `test_grounding.py`            |
| Execution attempted without approval            | `test_approval_gate.py`, `test_audit_trail.py` |
| Audit trail correctness                         | `test_audit_trail.py`          |
| Kill switch blocks assessment + execution        | `test_kill_switch.py`          |
| Full end-to-end happy path (primary demo scenario) | `test_e2e_happy_path.py`    |

Run: `cd backend && pytest -q` (SQLite in-memory, `LLM_PROVIDER=mock`, no
external services required — same as CI in `.github/workflows/ci.yml`).

## 7. What this POC does *not* claim

- No authentication/authorization system — `actor` on approvals/audit is a
  free-text field, not a verified identity. Not appropriate to carry into
  production as-is.
- The grounding validator is a heuristic (keyword/number presence), not a
  formal proof of factual correctness. It catches fabrication and
  non-engagement with evidence; it does not catch a subtly wrong but
  plausible-sounding number.
- Weather and telemetry are synthetic. The `WeatherProvider` abstraction and
  the `fetch_weather_safely()` failure-handling path are real and tested,
  but there is no live weather integration in this POC.
