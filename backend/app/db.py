import os
from motor.motor_asyncio import AsyncIOMotorClient

_db = None

def get_db():
    global _db
    if _db is None:
        _db = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "acme")]
    return _db

def set_db(db):  # tests
    global _db
    _db = db
