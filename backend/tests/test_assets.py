from tests.conftest import asset_payload, record_payload

URL = "/api/hydrotests/assets"


def test_create_asset(client):
    response = client.post(URL, json=asset_payload(assetId="  test-001 "))
    assert response.status_code == 201
    body = response.json()
    assert body["assetId"] == "TEST-001"
    assert body["status"] == "PENDING"


def test_duplicate_asset_id_returns_409(client):
    client.post(URL, json=asset_payload())
    response = client.post(URL, json=asset_payload(serialNumber="OTHER-SN"))
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_duplicate_serial_returns_409(client):
    client.post(URL, json=asset_payload())
    response = client.post(URL, json=asset_payload(assetId="TEST-002"))
    assert response.status_code == 409


def test_duplicate_does_not_overwrite(client):
    client.post(URL, json=asset_payload())
    client.post(URL, json=asset_payload(station="Demo Station C", serialNumber="X"))
    assert client.get(f"{URL}/TEST-001").json()["station"] == "Demo Station A"


def test_missing_required_field(client):
    payload = asset_payload()
    del payload["station"]
    response = client.post(URL, json=payload)
    assert response.status_code == 422
    assert "station" in response.json()["detail"]


def test_invalid_date_format(client):
    response = client.post(URL, json=asset_payload(testDate="not-a-date"))
    assert response.status_code == 422


def test_next_due_before_test_date(client):
    response = client.post(URL, json=asset_payload(testDate="2026-05-01", nextDueDate="2026-04-01"))
    assert response.status_code == 422
    assert "earlier" in response.json()["detail"]


def test_patch_checks_dates_against_stored_values(client):
    client.post(URL, json=asset_payload(testDate="2026-05-01", nextDueDate="2027-05-01"))
    response = client.patch(f"{URL}/TEST-001", json={"nextDueDate": "2026-01-01"})
    assert response.status_code == 422


def test_update_asset(client):
    client.post(URL, json=asset_payload())
    response = client.patch(f"{URL}/TEST-001", json={"station": "Demo Station B"})
    assert response.status_code == 200
    assert response.json()["station"] == "Demo Station B"


def test_get_missing_asset_returns_404(client):
    assert client.get(f"{URL}/NOPE").status_code == 404


def test_filters_search_and_sort(client):
    client.post(URL, json=asset_payload(assetId="A-1", serialNumber="S1", station="Demo Station A", nextDueDate="2027-03-01"))
    client.post(URL, json=asset_payload(assetId="A-2", serialNumber="S2", station="Demo Station B", assetType="Hose", nextDueDate="2027-01-01"))
    client.post(URL, json=asset_payload(assetId="A-3", serialNumber="S3", station="Demo Station A", nextDueDate="2027-02-01"))

    ids = lambda params: [a["assetId"] for a in client.get(URL, params=params).json()]
    assert ids({"station": "Demo Station A"}) == ["A-3", "A-1"]
    assert ids({"asset_type": "Hose"}) == ["A-2"]
    assert ids({"sort_order": "desc"}) == ["A-1", "A-3", "A-2"]
    assert ids({"due_from": "2027-02-01", "due_to": "2027-02-28"}) == ["A-3"]
    assert ids({"search": "a-2"}) == ["A-2"]


def test_bad_status_filter_is_rejected(client):
    assert client.get(URL, params={"status": "BROKEN"}).status_code == 422


def test_status_filter(client):
    client.post(URL, json=asset_payload())
    client.post(f"/api/hydrotests/records", json=record_payload(result="Fail", nextDueDate=None))
    assert len(client.get(URL, params={"status": "FAILED"}).json()) == 1
    assert client.get(URL, params={"status": "VALID"}).json() == []
