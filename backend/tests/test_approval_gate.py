import pytest

from app import approval_service, assessment_service
from app.exceptions import ApprovalRequiredError
from app.models import ApprovalStatus
from tests.conftest import add_reading, make_truck


def _high_risk_assessment(db):
    truck = make_truck(db)
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        add_reading(db, truck.id, minutes_ago=(len(temps) - 1 - i) * 20, cargo_temp_c=t, external_temp_c=39.0, route_delay_minutes=45)
    return assessment_service.run_assessment(db, truck)


def test_high_risk_assessment_opens_pending_approval(db):
    assessment = _high_risk_assessment(db)
    assert assessment.requires_approval is True
    assert assessment.approval is not None
    assert assessment.approval.status == ApprovalStatus.PENDING.value


def test_execute_action_blocked_without_approval(db):
    assessment = _high_risk_assessment(db)
    approval = assessment.approval

    with pytest.raises(ApprovalRequiredError):
        approval_service.execute_action(db, approval, actor="operator")


def test_execute_action_succeeds_after_approval(db):
    assessment = _high_risk_assessment(db)
    approval = assessment.approval

    approval_service.decide(db, approval, "approve", actor="fleet_manager")
    execution = approval_service.execute_action(db, approval, actor="operator")

    assert execution.outcome == "SUCCESS"
    assert execution.approval_id == approval.id


def test_execute_action_blocked_after_rejection(db):
    assessment = _high_risk_assessment(db)
    approval = assessment.approval

    approval_service.decide(db, approval, "reject", actor="fleet_manager")
    with pytest.raises(ApprovalRequiredError):
        approval_service.execute_action(db, approval, actor="operator")


def test_low_risk_does_not_require_approval(db):
    truck = make_truck(db)
    add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0, route_delay_minutes=0)
    assessment = assessment_service.run_assessment(db, truck)
    assert assessment.requires_approval is False
    assert assessment.approval is None
