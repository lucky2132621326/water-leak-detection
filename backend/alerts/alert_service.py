"""Alert Service

Aggregates per-sample detection responses into leak incidents and manages their
lifecycle. Backed by MongoDB (`alerts` collection) with an authoritative
in-memory mirror, so the dashboard stays responsive and the prototype keeps
working if Mongo is briefly unreachable — writes are best-effort persisted and
reloaded on restart.

Lifecycle
---------
ACTIVE          incident raised, not yet dealt with
RESOLVED        operator confirmed the leak was repaired (counts toward savings)
FALSE_POSITIVE  operator confirmed no leak was present (counts toward FP rate)

`is_open` is separate from `status`: it tracks whether the detector *currently*
still sees the anomaly. An alert whose alarm has cleared can still be ACTIVE —
the water stopped registering, but nobody has verified or repaired anything yet.
"""
import threading
import time

from backend.config.config_loader import impact_loader
from backend.impact.impact_service import ImpactService
from backend.impact.water_loss import WaterLossCalculator
from backend.utils.logger import logger

ALERT_STATUSES = ("ACTIVE", "RESOLVED", "FALSE_POSITIVE")

MINUTES_PER_DAY = 60 * 24


class AlertService:
    def __init__(self, db=None, impact_service: ImpactService = None, enable_persistence: bool = True):
        """`enable_persistence=False` gives a pure in-memory service that never
        touches MongoDB — used by the test suite so it neither requires a running
        database nor reads/writes real incident data."""
        self._lock = threading.RLock()
        self._alerts = []           # authoritative, newest-last
        self._next_seq = 1
        self._db = db
        # Reusing the failure flag means every persistence path is already
        # short-circuited; there is no second code path to keep in sync.
        self._db_failed = not enable_persistence
        self.impact = impact_service or ImpactService()
        self.merge_gap_sec = float(impact_loader.get("alerts.merge_gap_sec", 30))
        self.prevented_horizon_days = float(impact_loader.get("savings.prevented_horizon_days", 30))
        self._load_from_db()

    # --- persistence ------------------------------------------------------
    def _collection(self):
        if self._db_failed:
            return None
        try:
            if self._db is None:
                from backend.repositories.db import get_db
                self._db = get_db()
            return self._db.alerts
        except Exception as e:  # Mongo unreachable — degrade to memory-only
            logger.warning(f"[AlertService] MongoDB unavailable, using in-memory alerts: {e}")
            self._db_failed = True
            return None

    def _load_from_db(self):
        col = self._collection()
        if col is None:
            return
        try:
            docs = list(col.find({}, {"_id": 0}).sort("seq", 1))
        except Exception as e:
            logger.warning(f"[AlertService] Could not load stored alerts: {e}")
            self._db_failed = True
            return
        with self._lock:
            self._alerts = docs
            self._next_seq = max((d.get("seq", 0) for d in docs), default=0) + 1
        logger.info(f"[AlertService] Loaded {len(docs)} stored alerts")

    def _persist(self, alert: dict):
        col = self._collection()
        if col is None:
            return
        try:
            col.replace_one({"alert_id": alert["alert_id"]}, dict(alert), upsert=True)
        except Exception as e:
            logger.warning(f"[AlertService] Failed to persist {alert['alert_id']}: {e}")
            self._db_failed = True

    # --- ingestion --------------------------------------------------------
    @staticmethod
    def leak_rate_from(response: dict) -> float:
        """The residual (Qin - Qout - Qbranch) IS the estimated leak rate — that
        is exactly the water entering the zone that never left it."""
        return max(0.0, float(response.get("residual") or 0.0))

    def ingest(self, response: dict, source: str = "replay", run_id: str = None):
        """Feed one shaped detection response in. Returns the affected alert, or
        None if the sample was not in alarm and no incident was open."""
        if not response:
            return None

        ts = float(response.get("ts") or time.time())
        in_alarm = bool(response.get("is_alarm"))

        with self._lock:
            open_alert = self._find_open(source, run_id)

            if not in_alarm:
                # Alarm cleared — close the detection window but leave the
                # incident ACTIVE until an operator dispositions it.
                if open_alert and (ts - open_alert["last_seen_ts"]) >= 0:
                    open_alert["is_open"] = False
                    open_alert["end_ts"] = open_alert["last_seen_ts"]
                    open_alert["duration_sec"] = round(max(0.0, open_alert["end_ts"] - open_alert["start_ts"]), 1)
                    self._persist(open_alert)
                    return open_alert
                return None

            rate = self.leak_rate_from(response)

            if open_alert and (ts - open_alert["last_seen_ts"]) <= self.merge_gap_sec:
                return self._update(open_alert, response, ts, rate)

            # The replay player loops the same stored run continuously, so the
            # same sample arrives again on every pass. Re-ingesting a timestamp
            # already covered by an incident updates that incident instead of
            # spawning a duplicate, so one stored leak window yields one alert
            # however many times it is replayed. Matching on window overlap
            # rather than an exact onset matters because detector warm-up state
            # carries across loops, so the confirmed onset drifts slightly.
            existing = self._find_covering(source, run_id, ts)
            if existing:
                # Re-open the detection window so the rest of this replay pass
                # merges into the same incident instead of spawning one alert
                # per sample. The operator's status (RESOLVED / FALSE_POSITIVE)
                # is untouched — replaying evidence never undoes a disposition.
                existing["is_open"] = True
                return self._update(existing, response, ts, rate)

            return self._create(response, ts, rate, source, run_id)

    def _find_open(self, source, run_id):
        for a in reversed(self._alerts):
            if a.get("is_open") and a.get("source") == source and a.get("run_id") == run_id:
                return a
        return None

    def _find_covering(self, source, run_id, ts):
        """An existing incident for the same source/run whose detection window
        (widened by the merge gap) already contains `ts`."""
        for a in reversed(self._alerts):
            if a.get("source") != source or a.get("run_id") != run_id:
                continue
            window_end = a.get("end_ts") or a.get("last_seen_ts")
            if (a["start_ts"] - self.merge_gap_sec) <= ts <= (window_end + self.merge_gap_sec):
                return a
        return None

    def _create(self, response, ts, rate, source, run_id):
        seq = self._next_seq
        self._next_seq += 1

        alert = {
            "alert_id": f"LEAK-{seq:04d}",
            "seq": seq,
            "source": source,
            "run_id": run_id,
            "status": "ACTIVE",
            "is_open": True,
            "zone": response.get("zone") or "UNKNOWN",
            "confidence_tier": response.get("confidence_tier") or "NONE",
            "likelihood_score": response.get("likelihood_score") or 0.0,
            "start_ts": ts,
            "last_seen_ts": ts,
            "end_ts": None,
            "duration_sec": 0.0,
            "sample_count": 1,
            "leak_rate_lpm": round(rate, 3),
            "peak_leak_rate_lpm": round(rate, 3),
            "evidence": response.get("evidence") or "",
            "active_methods": list(response.get("active_methods") or []),
            "false_positive_warning": response.get("false_positive_warning"),
            "work_order_summary": response.get("work_order_summary"),
            "impact": self.impact.summarize(rate),
            "created_at": time.time(),
            "resolved_at": None,
            "resolution_note": None,
            "water_saved_litres": 0.0,
            "cost_saved": 0.0,
        }
        self._alerts.append(alert)
        self._persist(alert)
        logger.info(f"[AlertService] Raised {alert['alert_id']} in {alert['zone']} at {rate:.2f} L/min")
        return alert

    def _update(self, alert, response, ts, rate):
        alert["last_seen_ts"] = ts
        alert["duration_sec"] = round(max(0.0, ts - alert["start_ts"]), 1)
        alert["sample_count"] += 1
        alert["leak_rate_lpm"] = round(rate, 3)
        alert["evidence"] = response.get("evidence") or alert["evidence"]
        alert["active_methods"] = list(response.get("active_methods") or alert["active_methods"])

        # Track the worst observed rate — severity and savings should reflect
        # the peak of the incident, not whatever the last sample happened to be.
        if rate > alert["peak_leak_rate_lpm"]:
            alert["peak_leak_rate_lpm"] = round(rate, 3)
            alert["impact"] = self.impact.summarize(rate)

        if (response.get("likelihood_score") or 0.0) > alert["likelihood_score"]:
            alert["likelihood_score"] = response["likelihood_score"]
            alert["confidence_tier"] = response.get("confidence_tier") or alert["confidence_tier"]

        if response.get("work_order_summary"):
            alert["work_order_summary"] = response["work_order_summary"]
        if response.get("zone") and response["zone"] != "NONE":
            alert["zone"] = response["zone"]

        self._persist(alert)
        return alert

    # --- lifecycle transitions -------------------------------------------
    def resolve(self, alert_id: str, note: str = "", repaired: bool = True):
        """Mark an incident RESOLVED (repaired). Credits the prevented loss to
        the savings counter, based on the incident's peak rate."""
        with self._lock:
            alert = self.get(alert_id)
            if not alert:
                return None
            if alert["status"] == "RESOLVED":
                return alert

            rate = alert["peak_leak_rate_lpm"]
            prevented_minutes = self.prevented_horizon_days * MINUTES_PER_DAY
            litres = WaterLossCalculator.litres_over(rate, prevented_minutes) if repaired else 0.0

            alert["status"] = "RESOLVED"
            alert["is_open"] = False
            alert["resolved_at"] = time.time()
            alert["resolution_note"] = note or "Leak repaired and verified in the field."
            alert["water_saved_litres"] = round(litres, 1)
            alert["cost_saved"] = round(self.impact.estimator.cost_of(litres), 2)
            alert["savings_horizon_days"] = self.prevented_horizon_days
            if alert["end_ts"] is None:
                alert["end_ts"] = alert["last_seen_ts"]
                alert["duration_sec"] = round(max(0.0, alert["end_ts"] - alert["start_ts"]), 1)
            self._persist(alert)
            logger.info(f"[AlertService] {alert_id} resolved — {litres:.0f} L prevented over {self.prevented_horizon_days:.0f} days")
            return alert

    def mark_false_positive(self, alert_id: str, note: str = ""):
        with self._lock:
            alert = self.get(alert_id)
            if not alert:
                return None
            alert["status"] = "FALSE_POSITIVE"
            alert["is_open"] = False
            alert["resolved_at"] = time.time()
            alert["resolution_note"] = note or "Operator inspection found no leak present."
            # A false positive prevented nothing — never credit it as savings.
            alert["water_saved_litres"] = 0.0
            alert["cost_saved"] = 0.0
            if alert["end_ts"] is None:
                alert["end_ts"] = alert["last_seen_ts"]
                alert["duration_sec"] = round(max(0.0, alert["end_ts"] - alert["start_ts"]), 1)
            self._persist(alert)
            logger.info(f"[AlertService] {alert_id} dismissed as a false positive")
            return alert

    def reopen(self, alert_id: str):
        with self._lock:
            alert = self.get(alert_id)
            if not alert:
                return None
            alert["status"] = "ACTIVE"
            alert["resolved_at"] = None
            alert["resolution_note"] = None
            alert["water_saved_litres"] = 0.0
            alert["cost_saved"] = 0.0
            self._persist(alert)
            return alert

    # --- queries ----------------------------------------------------------
    def get(self, alert_id: str):
        for a in self._alerts:
            if a["alert_id"] == alert_id:
                return a
        return None

    def query(self, status=None, zone=None, severity=None, min_confidence=None,
              since_ts=None, until_ts=None, search=None, limit=200):
        """History explorer. All filters optional and AND-combined."""
        with self._lock:
            rows = list(self._alerts)

        def keep(a):
            if status and status != "ALL" and a["status"] != status:
                return False
            if zone and zone != "ALL" and a["zone"] != zone:
                return False
            if severity and severity != "ALL" and (a.get("impact") or {}).get("severity") != severity:
                return False
            if min_confidence is not None and (a.get("likelihood_score") or 0.0) < float(min_confidence):
                return False
            if since_ts is not None and a["start_ts"] < float(since_ts):
                return False
            if until_ts is not None and a["start_ts"] > float(until_ts):
                return False
            if search:
                blob = f"{a['alert_id']} {a['zone']} {a.get('evidence', '')} {a.get('resolution_note') or ''}".lower()
                if search.lower() not in blob:
                    return False
            return True

        rows = [a for a in rows if keep(a)]
        rows.sort(key=lambda a: a["start_ts"], reverse=True)
        return rows[: int(limit)]

    def counts(self):
        with self._lock:
            rows = list(self._alerts)
        return {
            "total": len(rows),
            "active": sum(1 for a in rows if a["status"] == "ACTIVE"),
            "resolved": sum(1 for a in rows if a["status"] == "RESOLVED"),
            "false_positive": sum(1 for a in rows if a["status"] == "FALSE_POSITIVE"),
            "open_now": sum(1 for a in rows if a.get("is_open")),
        }

    def zones(self):
        with self._lock:
            return sorted({a["zone"] for a in self._alerts if a.get("zone")})

    # --- savings ----------------------------------------------------------
    def savings(self):
        """Water Savings Counter — the utility-KPI view of repaired leaks."""
        with self._lock:
            resolved = [a for a in self._alerts if a["status"] == "RESOLVED"]
            false_positives = [a for a in self._alerts if a["status"] == "FALSE_POSITIVE"]
            total_alerts = len(self._alerts)

        litres = sum(a.get("water_saved_litres", 0.0) for a in resolved)
        money = sum(a.get("cost_saved", 0.0) for a in resolved)
        dispositioned = len(resolved) + len(false_positives)

        return {
            "leaks_prevented": len(resolved),
            "water_saved_litres": round(litres, 1),
            "money_saved": round(money, 2),
            "currency_symbol": self.impact.estimator.currency_symbol,
            "false_positives": len(false_positives),
            "total_alerts": total_alerts,
            "detection_precision": round(len(resolved) / dispositioned, 3) if dispositioned else None,
            "horizon_days": self.prevented_horizon_days,
            "equivalents": self.impact.calculator.equivalents_for(litres),
            "basis": (
                f"Savings credit each repaired leak with the water it would have lost over the "
                f"next {self.prevented_horizon_days:.0f} days at its peak observed rate. "
                "Dismissed false positives are never credited."
            ),
        }

    def timeline(self, buckets: int = 12):
        """Monthly leak counts for the history explorer's trend strip."""
        with self._lock:
            rows = list(self._alerts)
        if not rows:
            return []

        grouped = {}
        for a in rows:
            key = time.strftime("%Y-%m", time.localtime(a["start_ts"]))
            g = grouped.setdefault(key, {"month": key, "total": 0, "resolved": 0, "false_positive": 0, "active": 0})
            g["total"] += 1
            if a["status"] == "RESOLVED":
                g["resolved"] += 1
            elif a["status"] == "FALSE_POSITIVE":
                g["false_positive"] += 1
            else:
                g["active"] += 1

        return sorted(grouped.values(), key=lambda g: g["month"])[-int(buckets):]


# Shared instance — the API, the replay player and the live ingestor must all
# see the same incident list.
_default_alert_service = None


def get_alert_service() -> AlertService:
    global _default_alert_service
    if _default_alert_service is None:
        _default_alert_service = AlertService()
    return _default_alert_service
