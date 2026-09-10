from tests.conftest import add_reading, make_truck


def test_run_assessment_without_any_telemetry_returns_422(client, db):
    truck = make_truck(db, truck_id="TRK-NODATA")
    resp = client.post(f"/risk/assessments/run/{truck.id}")
    assert resp.status_code == 422


def test_run_assessment_with_missing_temperature_returns_422(client, db):
    truck = make_truck(db, truck_id="TRK-BADDATA")
    add_reading(db, truck.id, cargo_temp_c=None)
    resp = client.post(f"/risk/assessments/run/{truck.id}")
    assert resp.status_code == 422


def test_run_assessment_with_out_of_range_temperature_returns_422(client, db):
    truck = make_truck(db, truck_id="TRK-INVALIDTEMP")
    add_reading(db, truck.id, cargo_temp_c=500.0)
    resp = client.post(f"/risk/assessments/run/{truck.id}")
    assert resp.status_code == 422


def test_run_assessment_for_unknown_truck_returns_404(client):
    resp = client.post("/risk/assessments/run/TRK-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_get_unknown_truck_returns_404(client):
    resp = client.get("/trucks/TRK-DOES-NOT-EXIST")
    assert resp.status_code == 404
