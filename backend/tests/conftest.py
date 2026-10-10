import sys
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import create_indexes, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db():
    client = mongomock.MongoClient()
    client.drop_database("hydrotest_test")
    database = client["hydrotest_test"]
    create_indexes(database)
    return database


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def asset_payload(**changes):
    data = {
        "assetId": "TEST-001",
        "station": "Demo Station A",
        "assetType": "Storage Tank",
        "serialNumber": "TEST-SN-001",
    }
    data.update(changes)
    return data


def record_payload(**changes):
    data = {
        "assetId": "TEST-001",
        "testDate": "2026-01-10",
        "performedBy": "Test Inspector",
        "result": "Pass",
        "nextDueDate": "2027-01-10",
    }
    data.update(changes)
    return data
