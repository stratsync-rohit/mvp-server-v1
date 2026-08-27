from datetime import date, datetime

from bson import ObjectId
from bson.decimal128 import Decimal128


def serialize_mongo_value(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, Decimal128):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: serialize_mongo_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [serialize_mongo_value(item) for item in value]

    return value


def serialize_mongo_document(document: dict) -> dict:
    serialized = serialize_mongo_value(dict(document))

    if "_id" in serialized:
        serialized["id"] = str(serialized.pop("_id"))

    return serialized
