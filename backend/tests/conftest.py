import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("SEED_ON_STARTUP", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import TelemetryReading, Truck  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_truck(db, truck_id="TRK-TEST", region="South", setpoint=4.0, cargo_type="Fresh Produce"):
    truck = Truck(
        id=truck_id,
        driver_name="Test Driver",
        cargo_type=cargo_type,
        temp_setpoint_c=setpoint,
        route_name="Origin -> Destination",
        origin="Origin",
        destination="Destination",
        region=region,
        is_demo_scenario=False,
    )
    db.add(truck)
    db.commit()
    db.refresh(truck)
    return truck


def add_reading(db, truck_id, minutes_ago=0, **kwargs):
    defaults = dict(
        cargo_temp_c=4.0,
        external_temp_c=20.0,
        humidity_pct=50.0,
        latitude=30.0,
        longitude=-90.0,
        speed_kmh=80.0,
        route_delay_minutes=0.0,
        weather_condition="clear",
        weather_data_available=True,
    )
    defaults.update(kwargs)
    reading = TelemetryReading(
        truck_id=truck_id,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        **defaults,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading
