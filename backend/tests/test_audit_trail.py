from sqlalchemy import select

from app import approval_service, assessment_service
from app.models import AuditLog
from tests.conftest import add_reading, make_truck


def _event_types(db):
    return [e.event_type for e in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()]


def test_risk_assessment_creates_audit_entry(db):
    truck = make_truck(db)
    add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0)
    assessment_service.run_assessment(db, truck, actor="system")

    events = _event_types(db)
    assert "risk_assessment_generated" in events

    entry = db.execute(select(AuditLog).where(AuditLog.event_type == "risk_assessment_generated")).scalars().first()
    assert entry.truck_id == truck.id
    assert entry.actor == "system"
    assert "risk_score" in entry.details


def test_approval_decision_creates_audit_entry(db):
    truck = make_truck(db)
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        add_reading(db, truck.id, minutes_ago=(len(temps) - 1 - i) * 20, cargo_temp_c=t, external_temp_c=39.0, route_delay_minutes=45)
    assessment = assessment_service.run_assessment(db, truck)

    approval_service.decide(db, assessment.approval, "approve", actor="fleet_manager", comments="looks right")

    events = _event_types(db)
    assert "approval_approved" in events
    entry = db.execute(select(AuditLog).where(AuditLog.event_type == "approval_approved")).scalars().first()
    assert entry.actor == "fleet_manager"
    assert entry.details["comments"] == "looks right"


def test_execution_blocked_without_approval_is_audited(db):
    truck = make_truck(db)
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        add_reading(db, truck.id, minutes_ago=(len(temps) - 1 - i) * 20, cargo_temp_c=t, external_temp_c=39.0, route_delay_minutes=45)
    assessment = assessment_service.run_assessment(db, truck)

    try:
        approval_service.execute_action(db, assessment.approval, actor="operator")
    except Exception:
        pass

    events = _event_types(db)
    assert "execution_blocked_no_approval" in events


def test_audit_entries_are_immutable_append_only(db):
    """The audit log has no update/delete endpoint - entries can only be added."""
    truck = make_truck(db)
    add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0)
    assessment_service.run_assessment(db, truck)
    count_before = db.execute(select(AuditLog)).scalars().all()

    assessment_service.run_assessment(db, truck)
    count_after = db.execute(select(AuditLog)).scalars().all()

    assert len(count_after) > len(count_before)
