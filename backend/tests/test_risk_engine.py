import pytest

from app import risk_engine
from app.exceptions import InvalidTelemetryError
from app.models import RiskLevel
from tests.conftest import add_reading, make_truck


def test_low_risk_nominal_conditions(db):
    truck = make_truck(db)
    reading = add_reading(db, truck.id, cargo_temp_c=4.0, external_temp_c=20.0, route_delay_minutes=0)

    result = risk_engine.assess(truck.temp_setpoint_c, reading, [reading])
    assert result.risk_level == RiskLevel.LOW.value
    assert result.risk_score < 40
    assert result.recommended_action == "CONTINUE_JOURNEY"
    assert result.requires_approval is False


def test_high_risk_matches_primary_demo_scenario(db):
    """Cargo climbing 4C -> 10C, extreme heat, route delay => HIGH risk."""
    truck = make_truck(db, setpoint=4.0)

    history = []
    temps = [4.0, 5.2, 6.4, 7.6, 8.8, 10.0]
    for i, t in enumerate(temps):
        r = add_reading(
            db,
            truck.id,
            minutes_ago=(len(temps) - 1 - i) * 20,
            cargo_temp_c=t,
            external_temp_c=39.0,
            route_delay_minutes=45,
        )
        history.append(r)

    result = risk_engine.assess(truck.temp_setpoint_c, history[-1], history)

    assert result.risk_level == RiskLevel.HIGH.value
    assert result.risk_score >= 70
    assert result.recommended_action == "DIVERT_TO_FACILITY"
    assert result.requires_approval is True
    factors = {r["factor"] for r in result.reasons}
    assert "temperature_deviation" in factors
    assert "extreme_weather" in factors
    assert "route_delay" in factors


def test_medium_risk_moderate_deviation(db):
    truck = make_truck(db)
    reading = add_reading(db, truck.id, cargo_temp_c=8.0, external_temp_c=32.0, route_delay_minutes=40)
    result = risk_engine.assess(truck.temp_setpoint_c, reading, [reading])
    assert result.risk_level == RiskLevel.MEDIUM.value
    assert result.recommended_action == "CHANGE_ROUTE"
    assert result.requires_approval is True


def test_missing_temperature_raises_invalid_telemetry(db):
    truck = make_truck(db)
    reading = add_reading(db, truck.id, cargo_temp_c=None)
    with pytest.raises(InvalidTelemetryError):
        risk_engine.assess(truck.temp_setpoint_c, reading, [reading])


def test_out_of_range_temperature_raises_invalid_telemetry(db):
    truck = make_truck(db)
    reading = add_reading(db, truck.id, cargo_temp_c=999.0)
    with pytest.raises(InvalidTelemetryError):
        risk_engine.assess(truck.temp_setpoint_c, reading, [reading])


def test_weather_unavailable_excluded_from_score_not_fabricated(db):
    truck = make_truck(db)
    reading = add_reading(
        db, truck.id, cargo_temp_c=4.2, external_temp_c=None, weather_data_available=False, route_delay_minutes=0
    )
    result = risk_engine.assess(truck.temp_setpoint_c, reading, [reading])
    assert result.evidence_snapshot["component_scores"]["weather"] == 0.0
    factors = {r["factor"] for r in result.reasons}
    assert "weather_data_unavailable" in factors
