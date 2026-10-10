from datetime import date, timedelta

import numpy as np
import pytest

from app.errors import UpstreamError
from app.models.cng import CngStatus
from app.schemas.cng import CylinderTestCreate
from app.services import cng_service, number_plate_service, vehicle_provider
from app.services.number_plate_service import NoPlateFound, PlateReading

TODAY = date(2026, 10, 8)


def record(**changes):
    data = {
        "vehicleNumber": "GJ01AB1001",
        "cylinderSerial": "CYL-1",
        "testDate": (date.today() - timedelta(days=200)).isoformat(),
        "result": "Pass",
    }
    data.update(changes)
    return data


def add(client, **changes):
    response = client.post("/api/cng/cylinder-tests", json=record(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def verify(client, plate):
    response = client.get(f"/api/cng/verify/{plate}")
    assert response.status_code == 200, response.text
    return response.json()


# ---------- pure rules ----------

@pytest.mark.parametrize(
    "due, result, expected",
    [
        (date(2027, 1, 1), "Pass", CngStatus.VALID),
        (date(2026, 10, 8), "Pass", CngStatus.DUE_SOON),   # due today
        (date(2026, 11, 7), "Pass", CngStatus.DUE_SOON),   # exactly 30 days
        (date(2026, 11, 8), "Pass", CngStatus.VALID),      # 31 days
        (date(2026, 10, 7), "Pass", CngStatus.EXPIRED),    # yesterday
        (date(2027, 1, 1), "Fail", CngStatus.FAILED),      # fail beats a future date
    ],
)
def test_cylinder_status_rules(due, result, expected):
    test = {"result": result, "testDate": date(2024, 1, 1), "nextDueDate": due}
    assert cng_service.decide_cylinder_status(test, TODAY) == expected


def test_due_date_defaults_to_test_date_plus_validity(monkeypatch):
    monkeypatch.setattr(cng_service.config, "CNG_TEST_VALIDITY_YEARS", 3)
    assert cng_service.cylinder_due_date({"testDate": date(2024, 2, 29)}) == date(2027, 2, 28)


def test_worst_status_wins():
    assert cng_service.worst_status([CngStatus.VALID, CngStatus.EXPIRED, CngStatus.DUE_SOON]) == CngStatus.EXPIRED
    assert cng_service.worst_status([CngStatus.VALID, CngStatus.FAILED]) == CngStatus.FAILED


# ---------- verify endpoint ----------

def test_valid_cng_vehicle(client):
    add(client)
    body = verify(client, "GJ01AB1001")
    assert body["status"] == "VALID"
    assert body["vehicle"]["fuelType"] == "CNG"
    assert body["cylinders"][0]["cylinderSerial"] == "CYL-1"


def test_plate_is_normalised(client):
    add(client)
    assert verify(client, "gj-01 ab-1001")["plateNumber"] == "GJ01AB1001"


def test_owner_name_is_masked(client):
    add(client)
    assert verify(client, "GJ01AB1001")["vehicle"]["ownerName"] == "D*** O**** O**"


def test_expired_and_due_soon(client):
    add(client, vehicleNumber="GJ01CD2002", nextDueDate=(date.today() + timedelta(days=10)).isoformat())
    assert verify(client, "GJ01CD2002")["status"] == "DUE_SOON"
    add(client, vehicleNumber="GJ05EF3003", testDate="2020-01-01", nextDueDate="2023-01-01")
    assert verify(client, "GJ05EF3003")["status"] == "EXPIRED"


def test_default_validity_when_no_next_due_date(client):
    add(client, testDate=(date.today() - timedelta(days=4 * 365)).isoformat())  # older than 3 years
    assert verify(client, "GJ01AB1001")["status"] == "EXPIRED"


def test_newer_pass_replaces_older_fail_for_same_cylinder(client):
    add(client, testDate="2025-01-01", result="Fail")
    add(client)  # 200 days ago, Pass
    body = verify(client, "GJ01AB1001")
    assert body["status"] == "VALID" and len(body["cylinders"]) == 1


def test_one_failed_cylinder_fails_the_vehicle(client):
    add(client, vehicleNumber="GJ05GH4004", cylinderSerial="CYL-A")
    add(client, vehicleNumber="GJ05GH4004", cylinderSerial="CYL-B", result="Fail")
    body = verify(client, "GJ05GH4004")
    assert body["status"] == "FAILED" and len(body["cylinders"]) == 2


def test_cng_vehicle_without_records(client):
    assert verify(client, "GJ05JK5005")["status"] == "NO_RECORD"


def test_petrol_vehicle_is_not_cng(client):
    body = verify(client, "GJ06LM6006")
    assert body["status"] == "NOT_CNG" and "PETROL" in body["message"]


def test_dual_fuel_counts_as_cng(client):
    add(client, vehicleNumber="GJ05EF3003")
    assert verify(client, "GJ05EF3003")["status"] == "VALID"


def test_unknown_vehicle(client):
    assert verify(client, "XX99ZZ9999")["status"] == "VEHICLE_NOT_FOUND"


def test_blank_plate_rejected(client):
    assert client.get("/api/cng/verify/--").status_code == 400


def test_provider_failure_gives_502_not_a_guess(client, monkeypatch):
    class Broken:
        def fetch(self, plate):
            raise UpstreamError("The vehicle information service could not be reached. Please try again.")

    monkeypatch.setattr(cng_service, "get_provider", lambda: Broken())
    response = client.get("/api/cng/verify/GJ01AB1001")
    assert response.status_code == 502 and "could not be reached" in response.json()["detail"]


def test_missing_fuel_type_is_an_error_not_not_cng(client, monkeypatch):
    class NoFuel:
        def fetch(self, plate):
            return vehicle_provider.VehicleDetails(plate, fuel_type=None)

    monkeypatch.setattr(cng_service, "get_provider", lambda: NoFuel())
    assert client.get("/api/cng/verify/GJ01AB1001").status_code == 502


# ---------- cylinder test records ----------

def test_create_rejects_bad_data(client):
    assert client.post("/api/cng/cylinder-tests", json=record(testDate="2999-01-01")).status_code == 422
    assert client.post("/api/cng/cylinder-tests", json=record(nextDueDate="2000-01-01")).status_code == 422
    assert client.post("/api/cng/cylinder-tests", json=record(result="Maybe")).status_code == 422
    assert client.post("/api/cng/cylinder-tests", json=record(manufactureDate="2030-01-01")).status_code == 422


def test_list_filters_by_vehicle(client):
    add(client)
    add(client, vehicleNumber="GJ05GH4004")
    rows = client.get("/api/cng/cylinder-tests", params={"vehicle_number": "gj01ab1001"}).json()
    assert [r["vehicleNumber"] for r in rows] == ["GJ01AB1001"]


# ---------- real-API adapter ----------

def test_http_provider_maps_common_field_names():
    payload = {"data": {"fuel_type": "CNG", "owner_name": "A B", "vehicle_class": "LMV", "fitness_upto": "2030-01-01"}}
    vehicle = vehicle_provider.HttpVehicleProvider.map_response(payload, "GJ01AB1001")
    assert vehicle.is_cng and vehicle.fitness_valid_upto == "2030-01-01"


def test_http_provider_error_handling(monkeypatch):
    import httpx

    monkeypatch.setattr(vehicle_provider.config, "VEHICLE_API_URL", "https://example.test/rc/{plate}")
    provider = vehicle_provider.HttpVehicleProvider()

    def respond(status, body=None):
        return lambda url, headers, timeout: httpx.Response(status, json=body or {}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", respond(404))
    assert provider.fetch("GJ01AB1001") is None
    monkeypatch.setattr(httpx, "get", respond(401))
    with pytest.raises(UpstreamError):
        provider.fetch("GJ01AB1001")
    monkeypatch.setattr(httpx, "get", respond(200, {"data": {"fuel_type": "CNG"}}))
    assert provider.fetch("GJ01AB1001").is_cng

    def timeout(url, headers, timeout):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(httpx, "get", timeout)
    with pytest.raises(UpstreamError):
        provider.fetch("GJ01AB1001")


# ---------- camera / image scan ----------

def jpeg_bytes():
    import cv2

    ok, buffer = cv2.imencode(".jpg", np.full((60, 120, 3), 128, dtype=np.uint8))
    return buffer.tobytes()


@pytest.fixture
def fake_models(monkeypatch):
    monkeypatch.setattr(number_plate_service, "get_model", lambda: object())
    monkeypatch.setattr(number_plate_service, "check_ocr_available", lambda: None)


def scan(client, data=None, content_type="image/jpeg"):
    return client.post("/api/cng/scan", files={"file": ("capture.jpg", data or jpeg_bytes(), content_type)})


def test_scan_reads_plate_and_verifies(client, fake_models, monkeypatch):
    add(client)
    reading = PlateReading("GJ01AB1001", "GJ01 AB1001", 0.91, 0.88, np.zeros((5, 5, 3), np.uint8))
    monkeypatch.setattr(number_plate_service, "find_plate_in_frame", lambda frame: reading)
    body = scan(client).json()
    assert body["plateDetected"] and body["plateFormatValid"] and not body["lowConfidence"]
    assert body["verification"]["status"] == "VALID"


def test_scan_low_confidence_is_flagged(client, fake_models, monkeypatch):
    reading = PlateReading("GJ01AB1001", "GJ01AB1001", 0.30, 0.9, np.zeros((5, 5, 3), np.uint8))
    monkeypatch.setattr(number_plate_service, "find_plate_in_frame", lambda frame: reading)
    body = scan(client).json()
    assert body["lowConfidence"] and "check the number" in body["message"]


def test_scan_without_plate_is_not_an_error(client, fake_models, monkeypatch):
    def nothing(frame):
        raise NoPlateFound("No number plate could be detected in this image.")

    monkeypatch.setattr(number_plate_service, "find_plate_in_frame", nothing)
    response = scan(client)
    assert response.status_code == 200 and response.json()["plateDetected"] is False


def test_scan_keeps_plate_when_vehicle_lookup_fails(client, fake_models, monkeypatch):
    class Broken:
        def fetch(self, plate):
            raise UpstreamError("Vehicle service down.")

    monkeypatch.setattr(cng_service, "get_provider", lambda: Broken())
    reading = PlateReading("GJ01AB1001", "GJ01AB1001", 0.9, 0.9, np.zeros((5, 5, 3), np.uint8))
    monkeypatch.setattr(number_plate_service, "find_plate_in_frame", lambda frame: reading)
    body = scan(client).json()
    assert body["plateNumber"] == "GJ01AB1001" and body["verification"] is None and "down" in body["message"]


def test_scan_rejects_bad_files(client, fake_models):
    assert scan(client, data=b"not an image").status_code == 400
    assert scan(client, content_type="text/plain").status_code == 400


def test_scan_without_model_is_503(client, monkeypatch):
    monkeypatch.setattr(number_plate_service.config, "YOLO_MODEL_PATH", number_plate_service.config.BASE_DIR / "nope.pt")
    monkeypatch.setattr(number_plate_service, "_model", None)
    assert scan(client).status_code == 503


# ---------- seed data ----------

def test_seed_gives_every_status(db):
    from app import seed

    seed.seed_cylinders(db, date.today())
    provider = vehicle_provider.MockVehicleProvider()
    expected = {
        "GJ01AB1001": "VALID", "GJ01CD2002": "DUE_SOON", "GJ05EF3003": "EXPIRED",
        "GJ05GH4004": "FAILED", "GJ05JK5005": "NO_RECORD", "GJ06LM6006": "NOT_CNG",
    }
    for plate, status in expected.items():
        assert cng_service.verify(db, plate, provider)["status"].value == status
