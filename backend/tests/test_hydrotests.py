from datetime import date, timedelta

from tests.conftest import asset_payload, record_payload

ASSETS = "/api/hydrotests/assets"
RECORDS = "/api/hydrotests/records"


def make_asset(client):
    client.post(ASSETS, json=asset_payload())


def test_create_record(client):
    make_asset(client)
    response = client.post(RECORDS, json=record_payload())
    assert response.status_code == 201
    assert response.json()["result"] == "Pass"


def test_pass_without_due_date_gets_default_validity(client):
    make_asset(client)
    response = client.post(RECORDS, json=record_payload(nextDueDate=None))
    assert response.json()["nextDueDate"] == "2027-01-10"


def test_record_for_unknown_asset_returns_404(client):
    response = client.post(RECORDS, json=record_payload(assetId="NOPE"))
    assert response.status_code == 404


def test_invalid_result_value(client):
    make_asset(client)
    assert client.post(RECORDS, json=record_payload(result="Maybe")).status_code == 422


def test_next_due_before_test_date(client):
    make_asset(client)
    response = client.post(RECORDS, json=record_payload(testDate="2026-05-01", nextDueDate="2026-04-01"))
    assert response.status_code == 422


def test_report_file_cannot_be_a_path(client):
    make_asset(client)
    assert client.post(RECORDS, json=record_payload(reportFile="../../etc/passwd")).status_code == 422


def test_get_and_patch_record(client):
    make_asset(client)
    record_id = client.post(RECORDS, json=record_payload()).json()["id"]
    assert client.get(f"{RECORDS}/{record_id}").json()["performedBy"] == "Test Inspector"

    response = client.patch(f"{RECORDS}/{record_id}", json={"notes": "updated"})
    assert response.status_code == 200
    assert response.json()["notes"] == "updated"


def test_patch_with_bad_dates_returns_422(client):
    make_asset(client)
    record_id = client.post(RECORDS, json=record_payload()).json()["id"]
    assert client.patch(f"{RECORDS}/{record_id}", json={"nextDueDate": "2025-01-01"}).status_code == 422


def test_unknown_record_returns_404(client):
    assert client.get(f"{RECORDS}/not-an-id").status_code == 404
    assert client.get(f"{RECORDS}/64b64b64b64b64b64b64b64b").status_code == 404


def test_new_record_updates_asset_dates_and_status(client):
    make_asset(client)
    today = date.today()
    client.post(RECORDS, json=record_payload(testDate=str(today - timedelta(days=10)), nextDueDate=str(today + timedelta(days=10))))
    asset = client.get(f"{ASSETS}/TEST-001").json()
    assert asset["status"] == "DUE_SOON"
    assert asset["nextDueDate"] == str(today + timedelta(days=10))


def test_failed_then_pending_then_pass(client):
    make_asset(client)
    today = date.today()
    client.post(RECORDS, json=record_payload(testDate=str(today - timedelta(days=5)), result="Fail", nextDueDate=None))
    assert client.get(f"{ASSETS}/TEST-001").json()["status"] == "FAILED"

    client.post(RECORDS, json=record_payload(testDate=str(today - timedelta(days=2)), result="Pending", nextDueDate=None))
    assert client.get(f"{ASSETS}/TEST-001").json()["status"] == "PENDING"

    client.post(RECORDS, json=record_payload(testDate=str(today), result="Pass", nextDueDate=str(today + timedelta(days=300))))
    assert client.get(f"{ASSETS}/TEST-001").json()["status"] == "VALID"


def test_list_records_for_asset(client):
    make_asset(client)
    client.post(RECORDS, json=record_payload())
    assert len(client.get(RECORDS, params={"asset_id": "test-001"}).json()) == 1
    assert client.get(RECORDS, params={"asset_id": "OTHER"}).json() == []
