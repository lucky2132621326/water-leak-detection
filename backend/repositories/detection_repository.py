"""Detection & Leak Event Repository — persists fused detection results and
work orders to MongoDB. Mirrors the shape server.ts's dashboard consumed
previously so the frontend's fetch calls need no shape changes."""
from backend.repositories.db import get_db
from backend.utils.logger import logger


class DetectionRepository:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()

    def save_response(self, response: dict, run_id: str = None):
        doc = dict(response)
        doc["run_id"] = run_id
        self.db.detections.insert_one(doc)
        return doc

    def get_latest(self, run_id: str = None):
        return self.db.detections.find_one({"run_id": run_id}, sort=[("ts", -1)])

    def get_recent(self, limit=50, run_id: str = None):
        cursor = self.db.detections.find({"run_id": run_id}).sort("ts", -1).limit(limit)
        docs = list(cursor)
        docs.reverse()
        return docs


class LeakEventRepository:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()

    def create_event(self, start_ts, location_node, severity_lpm, run_id=None, is_ground_truth=False, notes="", metadata=None):
        doc = {
            "start_ts": start_ts,
            "stop_ts": None,
            "location_node": location_node,
            "severity_lpm": severity_lpm,
            "run_id": run_id,
            "is_ground_truth": is_ground_truth,
            "notes": notes,
            "metadata": metadata or {},
        }
        result = self.db.leak_events.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    def close_event(self, event_id, stop_ts):
        self.db.leak_events.update_one({"_id": event_id}, {"$set": {"stop_ts": stop_ts}})

    def get_for_run(self, run_id):
        return list(self.db.leak_events.find({"run_id": run_id}))


class WorkOrderRepository:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()

    def list_all(self):
        # Project out _id — ObjectId is not JSON-serializable and these rows go
        # straight out over the API.
        return list(self.db.work_orders.find({}, {"_id": 0}).sort("scheduled_start", -1))

    def insert(self, work_order: dict):
        self.db.work_orders.insert_one(work_order)
        logger.info(f"[WorkOrderRepository] Stored work order {work_order.get('id')}")
        return work_order
