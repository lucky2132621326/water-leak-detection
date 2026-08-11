"""
Telemetry Repository Layer
Direct database persistence operations for telemetry collection. No business logic.
"""
from backend.models.telemetry import TelemetryDTO
from backend.repositories.base import ModeScopedRepository
from backend.utils.logger import logger


class TelemetryRepository(ModeScopedRepository):
    def save_sample(self, telemetry: TelemetryDTO, run_id: str = None, extra: dict = None):
        doc = self.stamp({
            "ts": telemetry.ts,
            "seq": telemetry.seq,
            "device": telemetry.device,
            "run_id": run_id,  # None outside a run; set while an experiment or scenario is recording
            "flow": {
                "q_in_lpm": telemetry.flow.q_in_lpm,
                "q_out_lpm": telemetry.flow.q_out_lpm,
                "q_branch_lpm": telemetry.flow.q_branch_lpm,
                # Raw counts are stored alongside the converted rates so a later
                # K-factor correction can be applied to every historical
                # experiment by recomputation, instead of by re-running physical
                # tests that may no longer be reproducible.
                "pulses_in": telemetry.flow.pulses_in,
                "pulses_out": telemetry.flow.pulses_out,
                "pulses_branch": telemetry.flow.pulses_branch
            },
            "power": {
                "bus_v": telemetry.power.bus_v,
                "current_ma": telemetry.power.current_ma,
                "power_mw": telemetry.power.power_mw
            },
            "vibration": {
                "rms": telemetry.vibration.rms,
                "band_low": telemetry.vibration.band_low,
                "band_mid": telemetry.vibration.band_mid,
                "band_high": telemetry.vibration.band_high,
                # None when no piezo is fitted — the disc is optional hardware.
                "piezo_rms": telemetry.vibration.piezo_rms,
                "piezo_centroid_hz": telemetry.vibration.piezo_centroid_hz
            },
            "temp": {"water_c": telemetry.temp.water_c},
            "actuators": {
                "pump1": telemetry.actuators.pump1,
                "pump2": telemetry.actuators.pump2,
                "servo_deg": telemetry.actuators.servo_deg
                # No solenoid_state: this rig has no solenoid. Leaks are opened
                # physically by an operator, and the ground truth for a run lives
                # in `leak_events` as an operator-logged time window.
            },
            "health": {
                "uptime_s": telemetry.health.uptime_s,
                "wifi_rssi": telemetry.health.wifi_rssi,
                "free_heap": telemetry.health.free_heap
            }
        })
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
