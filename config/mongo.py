from django.conf import settings
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

_db = None


def get_db():
    """Return the shared Mongo database, creating the client and indexes on first use."""
    global _db
    if _db is None:
        client = MongoClient(settings.MONGODB_URI, tz_aware=True, serverSelectionTimeoutMS=8000)
        _db = client[settings.MONGODB_DB]
        ensure_indexes(_db)
    return _db


def ensure_indexes(db):
    try:
        db.products.drop_index("name_1")  # names are no longer unique; the item code is
    except OperationFailure:
        pass
    db.products.create_index(
        [("code", ASCENDING)], unique=True, partialFilterExpression={"code": {"$exists": True}}
    )
    db.orders.create_index([("created_at", -1)])
