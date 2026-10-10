import re
from collections import Counter
from datetime import date

from pymongo.errors import DuplicateKeyError

from app.errors import DuplicateError, NotFoundError, ValidationFailed
from app.models.asset import asset_to_dict
from app.models.hydrotest import HydrotestStatus
from app.schemas.asset import AssetCreate, AssetUpdate
from app.services import hydrotest_service
from app.services.hydrotest_status_service import decide_status
from app.utils.date_utils import check_due_after_test, to_date, to_datetime, utc_now
from app.utils.plate_utils import normalize_plate

SORTABLE = {"nextDueDate": "nextDueDate", "testDate": "testDate", "assetId": "assetId", "station": "station"}


def _get_doc(db, asset_id: str) -> dict:
    doc = db["assets"].find_one({"assetId": asset_id.strip().upper()})
    if doc is None:
        raise NotFoundError(f"Asset '{asset_id.strip().upper()}' was not found.")
    return doc


def find_by_identifier(db, text: str) -> dict | None:
    """Find an asset by asset ID or serial number (used for number plates)."""
    candidates = {text.strip().upper(), normalize_plate(text)} - {""}
    return db["assets"].find_one({"$or": [{"assetId": {"$in": list(candidates)}}, {"serialNumber": {"$in": list(candidates)}}]})


def create_asset(db, data: AssetCreate) -> dict:
    asset_id = data.assetId.upper()
    serial = data.serialNumber.upper()

    if db["assets"].find_one({"assetId": asset_id}):
        raise DuplicateError(f"Asset '{asset_id}' already exists. Use a different asset ID or update the existing asset.")
    if db["assets"].find_one({"serialNumber": serial}):
        raise DuplicateError(f"Serial/reference number '{serial}' is already used by another asset.")

    now = utc_now()
    doc = {
        "assetId": asset_id,
        "station": data.station,
        "assetType": data.assetType,
        "serialNumber": serial,
        "testDate": to_datetime(data.testDate),
        "nextDueDate": to_datetime(data.nextDueDate),
        "createdAt": now,
        "updatedAt": now,
    }
    doc["status"] = decide_status(doc, None).value
    try:
        doc["_id"] = db["assets"].insert_one(doc).inserted_id
    except DuplicateKeyError:
        # two requests racing each other: the unique index catches the loser
        raise DuplicateError(f"Asset '{asset_id}' already exists.")
    return asset_to_dict(doc)


def list_assets(
    db,
    station: str | None = None,
    asset_type: str | None = None,
    status: HydrotestStatus | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    search: str | None = None,
    sort_by: str = "nextDueDate",
    sort_order: str = "asc",
) -> list[dict]:
    query = {}
    if station:
        query["station"] = station
    if asset_type:
        query["assetType"] = asset_type
    if due_from or due_to:
        query["nextDueDate"] = {}
        if due_from:
            query["nextDueDate"]["$gte"] = to_datetime(due_from)
        if due_to:
            query["nextDueDate"]["$lte"] = to_datetime(due_to)
    if search and search.strip():
        pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
        query["$or"] = [{"assetId": pattern}, {"serialNumber": pattern}, {"station": pattern}, {"assetType": pattern}]

    field = SORTABLE.get(sort_by, "nextDueDate")
    direction = -1 if sort_order == "desc" else 1
    docs = list(db["assets"].find(query).sort([(field, direction), ("assetId", 1)]))

    # status depends on today's date, so it is worked out here rather than trusted from the DB
    latest = hydrotest_service.latest_records_by_asset(db)
    assets = []
    for doc in docs:
        current = decide_status(doc, latest.get(doc["assetId"])).value
        if doc.get("status") != current:
            db["assets"].update_one({"_id": doc["_id"]}, {"$set": {"status": current}})
            doc["status"] = current
        if status is None or current == status.value:
            assets.append(asset_to_dict(doc))
    return assets


def get_asset(db, asset_id: str) -> dict:
    doc = _get_doc(db, asset_id)
    status = decide_status(doc, hydrotest_service.latest_record(db, doc["assetId"])).value
    doc["status"] = status
    return asset_to_dict(doc)


def update_asset(db, asset_id: str, data: AssetUpdate) -> dict:
    doc = _get_doc(db, asset_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationFailed("Send at least one field to update.")
    for field in ("station", "assetType", "serialNumber"):
        if field in changes and changes[field] is None:
            raise ValidationFailed(f"{field} cannot be empty.")

    if "serialNumber" in changes:
        changes["serialNumber"] = changes["serialNumber"].upper()
        other = db["assets"].find_one({"serialNumber": changes["serialNumber"], "_id": {"$ne": doc["_id"]}})
        if other:
            raise DuplicateError(f"Serial/reference number '{changes['serialNumber']}' is already used by another asset.")

    try:
        check_due_after_test(
            to_date(changes.get("testDate", doc.get("testDate"))),
            to_date(changes.get("nextDueDate", doc.get("nextDueDate"))),
        )
    except ValueError as error:
        raise ValidationFailed(str(error))

    for field in ("testDate", "nextDueDate"):
        if field in changes:
            changes[field] = to_datetime(changes[field])

    doc.update(changes)
    changes["status"] = decide_status(doc, hydrotest_service.latest_record(db, doc["assetId"])).value
    changes["updatedAt"] = utc_now()
    db["assets"].update_one({"_id": doc["_id"]}, {"$set": changes})
    return get_asset(db, doc["assetId"])


def get_options(db) -> dict:
    return {
        "stations": sorted(db["assets"].distinct("station")),
        "assetTypes": sorted(db["assets"].distinct("assetType")),
    }


def get_summary(db) -> dict:
    assets = list_assets(db)
    counts = Counter(asset["status"] for asset in assets)

    attention_statuses = {HydrotestStatus.OVERDUE.value, HydrotestStatus.DUE_SOON.value, HydrotestStatus.FAILED.value}
    needs_attention = [a for a in assets if a["status"] in attention_statuses]
    needs_attention.sort(key=lambda a: a["nextDueDate"] or date.max)

    return {
        "totalAssets": len(assets),
        "valid": counts[HydrotestStatus.VALID.value],
        "dueSoon": counts[HydrotestStatus.DUE_SOON.value],
        "overdue": counts[HydrotestStatus.OVERDUE.value],
        "failed": counts[HydrotestStatus.FAILED.value],
        "pending": counts[HydrotestStatus.PENDING.value],
        "needsAttention": needs_attention[:10],
        "recentRecords": hydrotest_service.list_records(db, limit=5),
    }
