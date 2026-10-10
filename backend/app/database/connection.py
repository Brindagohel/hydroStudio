from pymongo import MongoClient

from app import config

_client: MongoClient | None = None


def get_database():
    global _client
    if _client is None:
        # short timeout so a missing MongoDB gives a quick error instead of hanging
        _client = MongoClient(config.MONGODB_URL, serverSelectionTimeoutMS=3000)
    return _client[config.DATABASE_NAME]


def get_db():
    """FastAPI dependency. Tests replace this with an in-memory database."""
    return get_database()


def create_indexes(db) -> None:
    db["assets"].create_index("assetId", unique=True)
    db["assets"].create_index("serialNumber", unique=True)
    db["assets"].create_index([("station", 1), ("assetType", 1)])
    db["assets"].create_index("nextDueDate")
    db["hydrotests"].create_index([("assetId", 1), ("testDate", -1)])
    db["inspection_results"].create_index("createdAt")
    db["cylinder_tests"].create_index([("vehicleNumber", 1), ("testDate", -1)])
