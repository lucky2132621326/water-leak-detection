"""Live leak control for Mock Data Mode.

Holds the operator's current leak intent — on/off, rate, branch — and is read by
the generator on *every* sample, so changes take effect on the next telemetry
tick rather than requiring a restart.

Why this exists as an override rather than as scenario edits: a ScenarioSpec is
a fixed script, which is the right shape for reproducible benchmarking but the
wrong shape for exploration. This lets the same generator serve both — follow
the script when no override is set, obey the operator when one is.

The guard that used to reject leak commands in Mock Data Mode was a mistake: it
imported a hardware constraint into software that has none. A generator can
change its leak rate mid-stream as easily as it can follow a script.
"""
import threading
import time

MAIN = "Main_Trunk"
BRANCH_A = "Branch_A"
BRANCH_B = "Branch_B"
VALID_LOCATIONS = (MAIN, BRANCH_A, BRANCH_B)

#: Bench presets, matching the physical rig's calibrated orifices.
PRESETS = {"small": 0.5, "medium": 1.25, "large": 2.5}


class MockLeakControl:
    """Mutable leak state, safe to read from the generator thread while the API
    thread writes it."""

    def __init__(self):
        self._lock = threading.RLock()
        self.active = False
        self.rate_lpm = 0.0
        self.location = MAIN
        self.ramp_sec = 0.0
        self.opened_at = None
        self.closed_at = None
        # Set while an override is in force, so the generator knows to ignore
        # the scenario's scripted leaks entirely rather than summing the two.
        self.overriding = False

    # --- commands ---------------------------------------------------------
    def open(self, rate_lpm: float, location: str = MAIN, ramp_sec: float = 0.0):
        location = location if location in VALID_LOCATIONS else MAIN
        rate = max(0.0, float(rate_lpm))
        with self._lock:
            self.active = True
            self.overriding = True
            self.rate_lpm = rate
            self.location = location
            self.ramp_sec = max(0.0, float(ramp_sec))
            self.opened_at = time.time()
            self.closed_at = None
        return self.snapshot()

    def close(self):
        with self._lock:
            self.active = False
            # `overriding` stays True: once the operator has taken manual
            # control, a closed valve must mean zero leak, not "fall back to
            # whatever the script says". Otherwise stopping a leak could
            # silently restart a scripted one.
            self.rate_lpm = 0.0
            self.closed_at = time.time()
        return self.snapshot()

    def release(self):
        """Hand control back to the scenario script."""
        with self._lock:
            self.active = False
            self.overriding = False
            self.rate_lpm = 0.0
            self.opened_at = self.closed_at = None
        return self.snapshot()

    def set_rate(self, rate_lpm: float):
        with self._lock:
            self.rate_lpm = max(0.0, float(rate_lpm))
            if self.rate_lpm > 0:
                self.active = True
                self.overriding = True
                if self.opened_at is None:
                    self.opened_at = time.time()
        return self.snapshot()

    def set_location(self, location: str):
        with self._lock:
            if location in VALID_LOCATIONS:
                self.location = location
        return self.snapshot()

    # --- read model -------------------------------------------------------
    def current_rate(self) -> float:
        """Effective leak rate now, applying the ramp if one was requested."""
        with self._lock:
            if not self.active or self.rate_lpm <= 0:
                return 0.0
            if self.ramp_sec <= 0 or self.opened_at is None:
                return self.rate_lpm
            elapsed = time.time() - self.opened_at
            return self.rate_lpm * min(1.0, elapsed / self.ramp_sec)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self.active,
                "overriding": self.overriding,
                "rate_lpm": round(self.rate_lpm, 3),
                "effective_rate_lpm": round(self.current_rate(), 3),
                "location": self.location,
                "ramp_sec": self.ramp_sec,
                "opened_at": self.opened_at,
                "closed_at": self.closed_at,
                "presets": PRESETS,
                "locations": list(VALID_LOCATIONS),
            }
