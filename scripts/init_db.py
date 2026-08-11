"""Create collections and indexes in BOTH mode databases.

Live and mock are physically separate databases (backend/repositories/db.py), so
indexing only one would leave the other doing collection scans — and would hide
the omission, because the app would still work, just slowly.

The schema is identical in both. That is the point of the split: the two modes
must be functionally identical in every respect except where the data comes from.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

from backend.repositories.db import DB_NAMES

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")


def init_one(db, name: str):
    db.telemetry.create_index([("ts", -1)])
    db.telemetry.create_index([("run_id", 1), ("ts", 1)])
    db.detections.create_index([("ts", -1)])
    db.detections.create_index([("is_alarm", 1), ("ts", -1)])
    db.detections.create_index([("run_id", 1), ("ts", 1)])
    # Ground truth is now scored by time-window overlap against these records,
    # so the window bounds carry the query load.
    db.leak_events.create_index([("open_ts", -1)])
    db.leak_events.create_index([("run_id", 1), ("open_ts", 1)])
    db.experiment_runs.create_index([("run_id", 1)], unique=True)
    db.work_orders.create_index([("id", 1)], unique=True)
    db.alerts.create_index([("start_ts", -1)])
    db.events.create_index([("ts", -1)])
    # Redundant with the database itself, and indexed anyway so a mis-stamped
    # record is cheap to find.
    for coll in ("telemetry", "detections", "leak_events", "alerts", "experiment_runs"):
        db[coll].create_index([("mode", 1)])
    print(f"[MongoDB] Initialized collections & indexes in '{name}'")


def init_db():
    print(f"[MongoDB] Connecting to {MONGO_URI}...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        for mode, name in DB_NAMES.items():
            init_one(client[name], f"{name}  ({mode} mode)")
    except Exception as e:
        print(f"[MongoDB] Could not reach the server: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(init_db())
