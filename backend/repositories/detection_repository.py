"""Detection & Leak Event Repository — persists fused detection results, ground
truth and work orders to MongoDB.

`leak_events` is now the ground-truth store for the whole project. On the rig a
leak is a human opening a worm-drive clamp on a tee stub; there is no solenoid
and no software injection. What the software contributes is the record: which
tee, how many turns, the calibrated litres-per-minute that corresponds to, and
the millisecond the clamp opened and closed. Every precision, recall and latency
figure is scored against those windows.
"""
from backend.repositories.base import ModeScopedRepository
from backend.utils.logger import logger

#: Physical leak points on the main trunk (spec Part A.1).
TEE_IDS = ("A", "B", "C")
#: Demand regimes. Performance must be reported separately for the two, because
#: detecting a leak against varying demand is the genuinely hard case.
DEMAND_MODES = ("steady", "variable")


class DetectionRepository(ModeScopedRepository):
    def save_response(self, response: dict, run_id: str = None):
        doc = self.stamp(dict(response))
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


class LeakEventRepository(ModeScopedRepository):
    """Operator-logged physical leak windows — the project's ground truth."""

    def open_event(self, open_ts, tee_id, clamp_turns, leak_lpm,
                   demand_mode="steady", run_id=None, notes="", source="operator"):
        """Record that a physical leak was opened.

        `leak_lpm` comes from the tee's volumetric clamp-calibration table, not
        from any detector — it is what the rig was *set* to leak, which is the
        only figure that can honestly be called ground truth.
        """
        doc = self.stamp({
            "open_ts": open_ts,
            "close_ts": None,
            "tee_id": tee_id,
            "clamp_turns": clamp_turns,
            "leak_lpm": leak_lpm,
            "demand_mode": demand_mode,
            "run_id": run_id,
            "is_ground_truth": True,
            #: "operator" for a hand-opened clamp, "generator" for mock. Kept
            #: distinct from `mode` so a mock run can still say which part of it
            #: was scripted versus driven from the bench controls.
            "source": source,
            "notes": notes,
        })
        result = self.db.leak_events.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info(f"[LeakEvents] opened tee={tee_id} {leak_lpm} L/min "
                    f"({clamp_turns} turns, {demand_mode} demand) at {open_ts}")
        return doc

    def close_event(self, event_id, close_ts):
        self.db.leak_events.update_one({"_id": event_id}, {"$set": {"close_ts": close_ts}})
        logger.info(f"[LeakEvents] closed {event_id} at {close_ts}")

    def open_events(self, run_id=None):
        return list(self.db.leak_events.find({"run_id": run_id, "close_ts": None}))

    def get_for_run(self, run_id):
        return list(self.db.leak_events.find({"run_id": run_id}).sort("open_ts", 1))

    def list_recent(self, limit=100):
        return list(self.db.leak_events.find({}).sort("open_ts", -1).limit(int(limit)))


class WorkOrderRepository(ModeScopedRepository):
    def list_all(self):
        # Project out _id — ObjectId is not JSON-serializable and these rows go
        # straight out over the API.
        return list(self.db.work_orders.find({}, {"_id": 0}).sort("scheduled_start", -1))

    def insert(self, work_order: dict):
        self.db.work_orders.insert_one(self.stamp(work_order))
        logger.info(f"[WorkOrderRepository] Stored work order {work_order.get('id')}")
        return work_order
