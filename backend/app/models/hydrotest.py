from enum import Enum

from app.utils.date_utils import to_date


class TestResult(str, Enum):
    __test__ = False  # stop pytest from treating this class as a test
    PASS = "Pass"
    FAIL = "Fail"
    PENDING = "Pending"


class HydrotestStatus(str, Enum):
    VALID = "VALID"
    DUE_SOON = "DUE_SOON"
    OVERDUE = "OVERDUE"
    FAILED = "FAILED"
    PENDING = "PENDING"
    NOT_FOUND = "NOT_FOUND"


def record_to_dict(doc: dict) -> dict:
    """Turn a MongoDB hydrotest document into something the API can return."""
    return {
        "id": str(doc["_id"]),
        "assetId": doc["assetId"],
        "testDate": to_date(doc["testDate"]),
        "nextDueDate": to_date(doc.get("nextDueDate")),
        "performedBy": doc["performedBy"],
        "result": doc["result"],
        "notes": doc.get("notes", ""),
        "reportFile": doc.get("reportFile"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }
