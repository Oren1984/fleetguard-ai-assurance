import pytest

from app import approval_service, assessment_service, kill_switch
from app.exceptions import KillSwitchEngagedError
from tests.conftest import add_reading, make_truck


def test_kill_switch_starts_disengaged(db):
    assert kill_switch.is_engaged(db) is False


def test_kill_switch_blocks_new_risk_assessments(db):
    truck = make_truck(db)
    add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0)

    kill_switch.set_engaged(db, True, actor="admin")

    with pytest.raises(KillSwitchEngagedError):
        assessment_service.run_assessment(db, truck)


def test_kill_switch_blocks_action_execution(db):
    truck = make_truck(db)
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        add_reading(db, truck.id, minutes_ago=(len(temps) - 1 - i) * 20, cargo_temp_c=t, external_temp_c=39.0, route_delay_minutes=45)
    assessment = assessment_service.run_assessment(db, truck)
    approval_service.decide(db, assessment.approval, "approve", actor="fleet_manager")

    kill_switch.set_engaged(db, True, actor="admin")

    with pytest.raises(KillSwitchEngagedError):
        approval_service.execute_action(db, assessment.approval, actor="operator")


def test_kill_switch_can_be_disengaged_to_resume_operations(db):
    truck = make_truck(db)
    add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0)

    kill_switch.set_engaged(db, True, actor="admin")
    kill_switch.set_engaged(db, False, actor="admin")

    assessment = assessment_service.run_assessment(db, truck)
    assert assessment is not None
