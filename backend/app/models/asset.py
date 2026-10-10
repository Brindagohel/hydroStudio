from app.utils.date_utils import to_date


def asset_to_dict(doc: dict) -> dict:
    """Turn a MongoDB asset document into something the API can return."""
    return {
        "id": str(doc["_id"]),
        "assetId": doc["assetId"],
        "station": doc["station"],
        "assetType": doc["assetType"],
        "serialNumber": doc["serialNumber"],
        "testDate": to_date(doc.get("testDate")),
        "nextDueDate": to_date(doc.get("nextDueDate")),
        "status": doc.get("status", "PENDING"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }
