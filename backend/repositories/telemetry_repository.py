"""
Telemetry Repository Layer
Direct database persistence operations for telemetry collection. No business logic.
"""
from backend.models.telemetry import TelemetryDTO
from backend.repositories.db import get_db
from backend.utils.logger import logger


class TelemetryRepository:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()

    def save_sample(self, telemetry: TelemetryDTO, run_id: str = None, extra: dict = None):
        doc = {
            "ts": telemetry.ts,
            "seq": telemetry.seq,
            "device_id": telemetry.device_id,
            "run_id": run_id,  # None for live telemetry, set for a replay/recorded run
            "flow": {
                "q_in_lpm": telemetry.flow.q_in_lpm,
                "q_out_lpm": telemetry.flow.q_out_lpm,
                "q_branch_lpm": telemetry.flow.q_branch_lpm,
                "pulses_in": telemetry.flow.pulses_in,
                "pulses_out": telemetry.flow.pulses_out,
                "pulses_branch": telemetry.flow.pulses_branch
            },
            "power": {
                "voltage": telemetry.power.voltage,
                "current_ma": telemetry.power.current_ma
            },
            "actuators": {
                "pump1": telemetry.actuators.pump1,
                "pump2": telemetry.actuators.pump2,
                "servo_deg": telemetry.actuators.servo_deg
            },
            "health": {
                "uptime_s": telemetry.health.uptime_s,
                "wifi_rssi": telemetry.health.wifi_rssi,
                "free_heap": telemetry.health.free_heap
            },
            "vibration": {
                "rms": telemetry.vibration.rms,
                "band_low": telemetry.vibration.band_low,
                "band_mid": telemetry.vibration.band_mid,
                "band_high": telemetry.vibration.band_high,
                "piezo_rms": telemetry.vibration.piezo_rms,
                "piezo_centroid_hz": telemetry.vibration.piezo_centroid_hz,
            } if telemetry.vibration.available() else None,
            "temp": {
                "water_c": telemetry.temp.water_c,
            } if telemetry.temp.water_c is not None else None,
        }
        if extra:
            doc.update(extra)

        self.db.telemetry.insert_one(doc)
        logger.debug(f"[TelemetryRepository] Saved seq={telemetry.seq}")
        return doc

    def get_recent(self, limit=120, run_id: str = None):
        query = {"run_id": run_id}
        cursor = self.db.telemetry.find(query).sort("ts", -1).limit(limit)
        docs = list(cursor)
        docs.reverse()
        return docs

    def get_by_run(self, run_id: str):
        return list(self.db.telemetry.find({"run_id": run_id}).sort("ts", 1))
