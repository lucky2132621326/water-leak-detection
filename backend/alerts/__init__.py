"""Alert Center

Turns the detection pipeline's per-sample responses into durable, reviewable
leak incidents with a lifecycle (ACTIVE -> RESOLVED / FALSE_POSITIVE), which is
what an operator actually works from. The per-sample response answers "is there
a leak right now?"; an alert answers "which incidents happened, and what did we
do about them?".
"""
from backend.alerts.alert_service import AlertService, ALERT_STATUSES

__all__ = ["AlertService", "ALERT_STATUSES"]
