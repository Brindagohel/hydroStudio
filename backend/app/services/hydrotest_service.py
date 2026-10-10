from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId

from app import config
from app.errors import NotFoundError, ValidationFailed
from app.models.hydrotest import TestResult, record_to_dict
from app.schemas.hydrotest import HydrotestCreate, HydrotestUpdate
from app.services.hydrotest_status_service import decide_status
from app.utils.date_utils import check_due_after_test, to_date, to_datetime, utc_now


def latest_record(db, asset_id: str) -> dict | None:
    return db["hydrotests"].find_one({"assetId": asset_id}, sort=[("testDate", -1), ("createdAt", -1)])


def latest_records_by_asset(db) -> dict:
    """Newest hydrotest document for every asset, keyed by assetId."""
    latest = {}
    for doc in db["hydrotests"].find().sort([("testDate", -1), ("createdAt", -1)]):
        latest.setdefault(doc["assetId"], doc)
    return latest


def list_records(db, asset_id: str | None = None, result: TestResult | None = None, limit: int = 500) -> list[dict]:
    query = {}
    if asset_id:
        query["assetId"] = asset_id.strip().upper()
    if result:
        query["result"] = result.value
    docs = db["hydrotests"].find(query).sort([("testDate", -1), ("createdAt", -1)]).limit(limit)
    return [record_to_dict(doc) for doc in docs]


def _get_doc(db, record_id: str) -> dict:
    try:
        doc = db["hydrotests"].find_one({"_id": ObjectId(record_id)})
    except (InvalidId, TypeError):
        doc = None
    if doc is None:
        raise NotFoundError("Hydrotest record not found.")
    return doc


def get_record(db, record_id: str) -> dict:
    return record_to_dict(_get_doc(db, record_id))


def create_record(db, data: HydrotestCreate) -> dict:
    asset_id = data.assetId.upper()
    if db["assets"].find_one({"assetId": asset_id}) is None:
        raise NotFoundError(f"Asset '{asset_id}' was not found. Create the asset first.")

    next_due = data.nextDueDate
    if next_due is None and data.result == TestResult.PASS:
        next_due = data.testDate + timedelta(days=config.TEST_VALIDITY_DAYS)

    now = utc_now()
    doc = {
        "assetId": asset_id,
        "testDate": to_datetime(data.testDate),
        "nextDueDate": to_datetime(next_due),
        "performedBy": data.performedBy,
        "result": data.result.value,
        "notes": data.notes,
        "reportFile": data.reportFile,
        "createdAt": now,
        "updatedAt": now,
    }
    doc["_id"] = db["hydrotests"].insert_one(doc).inserted_id
    sync_asset(db, asset_id)
    return record_to_dict(doc)


def update_record(db, record_id: str, data: HydrotestUpdate) -> dict:
    doc = _get_doc(db, record_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationFailed("Send at least one field to update.")

    if "result" in changes and changes["result"] is not None:
        changes["result"] = changes["result"].value
    for field in ("testDate", "nextDueDate"):
        if field in changes:
            changes[field] = to_datetime(changes[field])
    for field in ("testDate", "performedBy", "result"):
        if field in changes and changes[field] is None:
            raise ValidationFailed(f"{field} cannot be empty.")

    # PATCH may send only one of the two dates, so check the merged values
    try:
        check_due_after_test(
            to_date(changes.get("testDate", doc["testDate"])),
            to_date(changes.get("nextDueDate", doc.get("nextDueDate"))),
        )
    except ValueError as error:
        raise ValidationFailed(str(error))

    changes["updatedAt"] = utc_now()
    db["hydrotests"].update_one({"_id": doc["_id"]}, {"$set": changes})
    sync_asset(db, doc["assetId"])
    return get_record(db, record_id)


def sync_asset(db, asset_id: str) -> None:
    """Copy the latest test onto the asset and refresh its stored status."""
    asset = db["assets"].find_one({"assetId": asset_id})
    if asset is None:
        return
    latest = latest_record(db, asset_id)

    changes = {}
    if latest is not None:
        changes["testDate"] = latest["testDate"]
        changes["nextDueDate"] = latest.get("nextDueDate")
    asset.update(changes)

    changes["status"] = decide_status(asset, latest).value
    changes["updatedAt"] = utc_now()
    db["assets"].update_one({"_id": asset["_id"]}, {"$set": changes})
