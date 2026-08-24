"""
Detector State Machine
Prevents false alarms by filtering transient air bubbles or pump startup surges.
States: NORMAL -> SUSPECTED -> CONFIRMED -> RECOVERING -> NORMAL
"""
from enum import Enum
from backend.utils.logger import logger

class DetectionState(Enum):
    NORMAL = "NORMAL"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    RECOVERING = "RECOVERING"

class DetectionStateMachine:
    def __init__(self, persistence_samples=10, recovery_samples=5):
        self.state = DetectionState.NORMAL
        self.suspect_count = 0
        self.recovery_count = 0
        self.persistence_samples = persistence_samples
        self.recovery_samples = recovery_samples

    def update(self, raw_alarm: bool, residual: float) -> dict:
        prev_state = self.state

        if self.state == DetectionState.NORMAL:
            if raw_alarm:
                self.suspect_count = 1
                if self.persistence_samples <= 1:
                    self.state = DetectionState.CONFIRMED
                    logger.warning("[StateMachine] Alarm persisted for configured sample window -> Transition to CONFIRMED LEAK")
                else:
                    self.state = DetectionState.SUSPECTED
                    logger.info("[StateMachine] Alarm candidate triggered -> Transition to SUSPECTED")

        elif self.state == DetectionState.SUSPECTED:
            if raw_alarm:
                self.suspect_count += 1
                if self.suspect_count >= self.persistence_samples:
                    self.state = DetectionState.CONFIRMED
                    logger.warning(f"[StateMachine] Alarm sustained for {self.suspect_count}s -> Transition to CONFIRMED LEAK")
            else:
                self.suspect_count = 0
                self.state = DetectionState.NORMAL
                logger.info("[StateMachine] Transient anomaly cleared -> Transition back to NORMAL")

        elif self.state == DetectionState.CONFIRMED:
            if not raw_alarm:
                self.recovery_count = 1
                if self.recovery_samples <= 1:
                    self.state = DetectionState.NORMAL
                    self.suspect_count = 0
                    logger.info("[StateMachine] Recovery confirmed -> Return to NORMAL")
                else:
                    self.state = DetectionState.RECOVERING
                    logger.info("[StateMachine] Leak anomaly dropped -> Transition to RECOVERING")
            else:
                self.recovery_count = 0

        elif self.state == DetectionState.RECOVERING:
            if not raw_alarm:
                self.recovery_count += 1
                if self.recovery_count >= self.recovery_samples:
                    self.state = DetectionState.NORMAL
                    self.suspect_count = 0
                    logger.info("[StateMachine] Recovery confirmed -> Return to NORMAL")
            else:
                self.state = DetectionState.CONFIRMED
                self.recovery_count = 0

        return {
            "state": self.state.value,
            "previous_state": prev_state.value,
            "suspect_count": self.suspect_count,
            "is_confirmed": self.state == DetectionState.CONFIRMED
        }
