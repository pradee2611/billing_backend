import re

from bson import ObjectId
from bson.errors import InvalidId

from config.mongo import get_db


def present(doc):
    return {
        "id": str(doc["_id"]),
        "code": doc["code"],
        "category": doc["category"],
        "name": doc["name"],
        "name_ta": doc.get("name_ta", ""),
        "mrp": doc["mrp"],
        "price": doc["price"],
    }


def list_active(search=""):
    query = {"is_active": True, "code": {"$exists": True}}
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"name_ta": pattern}]
        if search.isdigit():
            query["$or"].append({"code": int(search)})
    return [present(doc) for doc in get_db().products.find(query).sort("code", 1)]


def get_active(product_id):
    try:
        oid = ObjectId(product_id)
    except (InvalidId, TypeError):
        return None
    return get_db().products.find_one({"_id": oid, "is_active": True})
