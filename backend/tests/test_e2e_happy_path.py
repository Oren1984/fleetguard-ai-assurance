"""End-to-end happy path mirroring the primary demo scenario:
a truck's cargo temperature climbs from 4C to 10C during extreme heat and a
route delay. The system must detect it, explain it, retrieve the SOP,
recommend diversion, require approval, and record the full audit trail."""
from tests.conftest import add_reading, make_truck


def test_primary_demo_scenario_end_to_end(client, db):
    truck = make_truck(db, truck_id="TRK-DEMO", region="South")
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        add_reading(
            db,
            truck.id,
            minutes_ago=(len(temps) - 1 - i) * 20,
            cargo_temp_c=t,
            external_temp_c=39.5,
            route_delay_minutes=45,
        )

    # 1. Detect the deviation and classify the shipment.
    resp = client.post(f"/risk/assessments/run/{truck.id}")
    assert resp.status_code == 200
    assessment = resp.json()

    assert assessment["risk_level"] == "HIGH"
    assert assessment["risk_score"] >= 70

    # 2. The data that led to the decision must be visible.
    factors = {r["factor"] for r in assessment["reasons"]}
    assert {"temperature_deviation", "extreme_weather", "route_delay"}.issubset(factors)
    assert assessment["evidence_snapshot"]["cargo_temp_c"] == 10.0

    # 3. The relevant SOP must be retrieved and cited.
    assert assessment["sop_sources"]
    assert assessment["grounded"] is True
    assert assessment["explanation"] != "Insufficient Evidence"

    # 4. Diversion is recommended and requires human approval.
    assert assessment["recommended_action"] == "DIVERT_TO_FACILITY"
    assert assessment["requires_approval"] is True
    assert assessment["approval_status"] == "PENDING"
    approval_id = assessment["approval_id"]

    # Executing before approval must be refused.
    exec_resp = client.post(f"/approvals/{approval_id}/execute", params={"actor": "operator"})
    assert exec_resp.status_code == 403

    # 5. Human approval is granted.
    decision_resp = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "approve", "actor": "fleet_manager", "comments": "Confirmed, divert to facility"},
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "APPROVED"

    # 6. The approved action is executed.
    exec_resp = client.post(f"/approvals/{approval_id}/execute", params={"actor": "operator"})
    assert exec_resp.status_code == 200
    assert exec_resp.json()["outcome"] == "SUCCESS"

    # 7. The complete audit trail is persisted.
    audit_resp = client.get("/audit", params={"truck_id": truck.id})
    events = {e["event_type"] for e in audit_resp.json()}
    assert {"risk_assessment_generated", "approval_approved", "action_executed"}.issubset(events)


def test_health_endpoint_reports_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"


def test_metrics_endpoint_exposes_prometheus_format(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "fleetguard_risk_assessments_total" in resp.text
