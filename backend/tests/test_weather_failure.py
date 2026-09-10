from app.exceptions import WeatherServiceError
from app.weather import MockWeatherProvider, fetch_weather_safely


def test_weather_provider_raises_on_forced_failure():
    provider = MockWeatherProvider(force_failure=True)
    try:
        provider.get_conditions(30.0, -90.0)
        assert False, "expected WeatherServiceError"
    except WeatherServiceError:
        pass


def test_fetch_weather_safely_degrades_gracefully_on_failure():
    provider = MockWeatherProvider(force_failure=True)
    conditions, available = fetch_weather_safely(provider, 30.0, -90.0)
    assert conditions is None
    assert available is False


def test_fetch_weather_safely_returns_data_when_provider_healthy():
    provider = MockWeatherProvider(force_failure=False)
    conditions, available = fetch_weather_safely(provider, 30.0, -90.0)
    assert conditions is not None
    assert available is True


def test_risk_engine_does_not_crash_when_weather_unavailable(db):
    from app import risk_engine
    from tests.conftest import add_reading, make_truck

    truck = make_truck(db)
    reading = add_reading(db, truck.id, cargo_temp_c=5.0, external_temp_c=None, weather_data_available=False)
    result = risk_engine.assess(truck.temp_setpoint_c, reading, [reading])
    assert result.evidence_snapshot["weather_data_available"] is False
    assert result.evidence_snapshot["component_scores"]["weather"] == 0.0
