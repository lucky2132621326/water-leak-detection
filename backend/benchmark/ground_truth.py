"""Ground-truth scoring against operator-logged leak windows.

On this rig a leak is a person opening a worm-drive clamp. There is no solenoid
and no software injection, so there is no per-sample "was it leaking" flag to
read. Ground truth is a set of `leak_events` windows — `open_ts` to `close_ts`,
with the tee and the calibrated litres-per-minute that clamp position produces —
and every metric is scored against those.

The grace window
----------------
A detection counts as a true positive if it lands inside a leak window extended
by `scoring.grace_sec`. The grace exists because the physical event and the
logged timestamp are not the same instant: a clamp takes a moment to back off,
the operator's hand is not on the stopwatch, and the residual has to propagate
past the meters. Without it, correct detections at the very start and end of a
leak would be scored as false alarms.

The grace is applied at BOTH ends and is deliberately small. Making it large
would flatter the numbers by forgiving genuinely late detections, so it is
configurable and reported alongside every metric that used it.

False alarms
------------
Any confirmed alarm outside every leak window is a false positive. On a control
run — no leaks logged at all — every alarm is one. That count divided by the run
duration is the false-alarms-per-hour figure, which is the number an operator
actually cares about: not "how precise", but "how often will this wake me at 3am
for nothing".
"""
from backend.config.config_loader import thresholds_loader


def grace_sec() -> float:
    return float(thresholds_loader.get("scoring.grace_sec", 5.0))


def normalise_windows(events) -> list:
    """Accept either operator-logged (`open_ts`/`close_ts`) or legacy
    (`start_ts`/`stop_ts`) records, and drop anything without a usable start."""
    windows = []
    for e in events or []:
        open_ts = e.get("open_ts", e.get("start_ts"))
        if open_ts is None:
            continue
        close_ts = e.get("close_ts", e.get("stop_ts"))
        windows.append({
            "open_ts": float(open_ts),
            # An unclosed leak is still running: treat it as open-ended rather
            # than as a zero-length window, which would score every subsequent
            # correct detection as a false alarm.
            "close_ts": float(close_ts) if close_ts is not None else float("inf"),
            "tee_id": e.get("tee_id"),
            "leak_lpm": e.get("leak_lpm", e.get("severity_lpm")),
            "demand_mode": e.get("demand_mode", "steady"),
            "id": str(e.get("_id", e.get("id", len(windows)))),
        })
    return sorted(windows, key=lambda w: w["open_ts"])


def matching_window(ts: float, windows, grace: float = None):
    """The leak window this timestamp falls in, or None."""
    g = grace_sec() if grace is None else grace
    for w in windows:
        if (w["open_ts"] - g) <= ts <= (w["close_ts"] + g):
            return w
    return None


class GroundTruthScorer:
    """Accumulates per-sample verdicts against a fixed set of leak windows."""

    def __init__(self, events, grace: float = None):
        self.windows = normalise_windows(events)
        self.grace = grace_sec() if grace is None else grace
        self.tp = self.fp = self.fn = self.tn = 0
        self.first_detection = {}
        self.false_alarm_ts = []
        self._first_ts = None
        self._last_ts = None

    def observe(self, ts: float, is_alarm: bool):
        ts = float(ts)
        self._first_ts = ts if self._first_ts is None else min(self._first_ts, ts)
        self._last_ts = ts if self._last_ts is None else max(self._last_ts, ts)

        window = matching_window(ts, self.windows, self.grace)
        if is_alarm and window:
            self.tp += 1
            self.first_detection.setdefault(window["id"], ts)
        elif is_alarm:
            self.fp += 1
            self.false_alarm_ts.append(ts)
        elif window:
            self.fn += 1
        else:
            self.tn += 1

    # --- derived metrics --------------------------------------------------
    def latencies(self) -> list:
        """Seconds from each leak opening to its first confirmed detection.

        Measured from `open_ts` itself, never from the grace-extended bound —
        crediting the grace would understate latency by up to `grace_sec`.
        """
        return [round(self.first_detection[w["id"]] - w["open_ts"], 2)
                for w in self.windows if w["id"] in self.first_detection]

    def duration_hours(self) -> float:
        if self._first_ts is None or self._last_ts is None:
            return 0.0
        return max(0.0, (self._last_ts - self._first_ts)) / 3600.0

    def summary(self) -> dict:
        precision = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0
        recall = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        lat = self.latencies()
        hours = self.duration_hours()
        detected = len(self.first_detection)

        return {
            "true_positives": self.tp,
            "false_positives": self.fp,
            "false_negatives": self.fn,
            "true_negatives": self.tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1_score": round(f1, 3),
            "leak_windows": len(self.windows),
            "leaks_detected": detected,
            "detection_latency_sec": round(sum(lat) / len(lat), 2) if lat else None,
            "median_latency_sec": _median(lat),
            "worst_latency_sec": max(lat) if lat else None,
            # The number an operator actually feels. Precision says nothing about
            # rate: 99% precision on a busy rig can still mean an alarm an hour.
            "false_alarms_per_hour": round(self.fp / hours, 2) if hours > 0 else None,
            "run_duration_hours": round(hours, 4),
            "grace_sec": self.grace,
        }


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 2)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)
