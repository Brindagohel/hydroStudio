from datetime import date, timedelta

from tests.conftest import asset_payload, record_payload

ASSETS = "/api/hydrotests/assets"
RECORDS = "/api/hydrotests/records"


def add(client, number, result, due_in_days):
    asset_id = f"T-{number}"
    client.post(ASSETS, json=asset_payload(assetId=asset_id, serialNumber=f"SN-{number}"))
    today = date.today()
    due = None if due_in_days is None else str(today + timedelta(days=due_in_days))
    client.post(RECORDS, json=record_payload(assetId=asset_id, testDate=str(today - timedelta(days=100)), result=result, nextDueDate=due))


def test_empty_summary(client):
    body = client.get("/api/hydrotests/summary").json()
    assert body["totalAssets"] == 0
    assert body["needsAttention"] == []


def test_summary_counts_every_status(client):
    add(client, 1, "Pass", 200)    # valid
    add(client, 2, "Pass", 10)     # due soon
    add(client, 3, "Pass", -5)     # overdue
    add(client, 4, "Fail", None)   # failed
    add(client, 5, "Pending", None)  # pending
    add(client, 6, "Pass", 400)    # valid

    body = client.get("/api/hydrotests/summary").json()
    assert body["totalAssets"] == 6
    assert body["valid"] == 2
    assert body["dueSoon"] == 1
    assert body["overdue"] == 1
    assert body["failed"] == 1
    assert body["pending"] == 1
    assert len(body["recentRecords"]) == 5
    attention = {a["assetId"] for a in body["needsAttention"]}
    assert attention == {"T-2", "T-3", "T-4"}


def test_summary_changes_after_new_record(client):
    add(client, 1, "Pass", 200)
    assert client.get("/api/hydrotests/summary").json()["failed"] == 0
    client.post(RECORDS, json=record_payload(assetId="T-1", testDate=str(date.today()), result="Fail", nextDueDate=None))
    body = client.get("/api/hydrotests/summary").json()
    assert body["failed"] == 1
    assert body["valid"] == 0
