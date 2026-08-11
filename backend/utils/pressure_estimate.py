"""Pressure Estimation

No physical pressure sensor exists on this rig (see docs/MQTT_SPEC.md). This
derives a proxy pressure_bar from flow behavior: a leak opens an additional
path to atmosphere, so downstream pressure sags roughly in proportion to the
unaccounted (residual) flow. This is intentionally simple and clearly labeled
as an estimate — it is not a substitute for a real transducer reading.
"""

BASELINE_PRESSURE_BAR = 2.5
PRESSURE_DROP_PER_LPM = 0.35  # bar of drop per L/min of unaccounted residual flow


def estimate_pressure_bar(residual_lpm: float, pump_on: bool) -> dict:
    if not pump_on:
        return {"pressure_bar": 0.0, "source": "estimated"}

    drop = max(0.0, residual_lpm) * PRESSURE_DROP_PER_LPM
    pressure_bar = max(0.0, BASELINE_PRESSURE_BAR - drop)
    return {"pressure_bar": round(pressure_bar, 2), "source": "estimated"}
