"""Continuously publish safe synthetic flow telemetry for frontend testing.

The default run repeats one-litre cycles forever. Rates deliberately include
very small positive values (0.01 and 0.03 L/min) and never reach 3 L/min. Qin
and Qout are identical, so the mass-balance detector sees no synthetic leak.

Run from the repository root:

    python scripts/flow_ui_test.py

Stop with Ctrl+C. Use ``--packets 5`` for a finite smoke test or ``--dry-run``
to print packets without publishing them.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import time
from typing import Iterator
from urllib import request

import paho.mqtt.client as mqtt


RATES_LPM = (0.01, 0.03, 0.08, 0.20, 0.45, 0.80, 1.20, 1.75, 2.20, 2.65, 2.90, 2.40, 1.60, 0.90, 0.35)
DEVICE_ID = "flow-ui-test"
PULSES_PER_LITRE = 450.0


def load_local_env(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overwriting the caller's env."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def rate_sequence() -> Iterator[float]:
    while True:
        yield from RATES_LPM


def build_packet(
    *, rate_lpm: float, seq: int, cycle_litres: float,
    cycle_number: int, total_litres: float, timestamp: float,
) -> dict:
    if not 0.0 < rate_lpm < 3.0:
        raise ValueError("test flow rate must be greater than 0 and below 3 L/min")

    # Flow 3 measures a branch contained within Qout on this rig; it must not be
    # subtracted from Qout again. Vary it so all three System Overview values move.
    branch_lpm = round(rate_lpm * (0.25 + 0.10 * ((seq % 4) / 3.0)), 3)
    pulses = int(round(total_litres * PULSES_PER_LITRE))
    branch_pulses = int(round(total_litres * PULSES_PER_LITRE * 0.30))
    return {
        "ts": timestamp,
        "seq": seq,
        "device": DEVICE_ID,
        "mode": "live",
        "clock_synced": True,
        "flow": {
            "q_in_lpm": round(rate_lpm, 3),
            "q_out_lpm": round(rate_lpm, 3),
            "q_branch_lpm": branch_lpm,
            "pulses_in": pulses,
            "pulses_out": pulses,
            "pulses_branch": branch_pulses,
        },
        "power": {"bus_v": None, "current_ma": None, "power_mw": None},
        "vibration": {
            "rms": None, "band_low": None, "band_mid": None,
            "band_high": None, "piezo_rms": None, "piezo_centroid_hz": None,
        },
        "temp": {"water_c": None},
        "actuators": {"pump1": True, "pump2": False, "servo_deg": 0},
        "health": {
            "uptime_s": seq,
            "wifi_rssi": -50,
            "free_heap": 180000,
            "sensors": {"flow_1": True, "flow_2": True, "flow_3": True, "synthetic_test": True},
        },
        "test": {
            "synthetic": True,
            "purpose": "frontend-flow-display",
            "cycle_target_litres": 1.0,
            "cycle_number": cycle_number,
            "cycle_litres": round(cycle_litres, 4),
            "total_litres": round(total_litres, 4),
        },
    }


def switch_backend_to_live(url: str) -> None:
    payload = json.dumps({"mode": "live"}).encode("utf-8")
    req = request.Request(
        url.rstrip("/") + "/api/mode",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"mode switch failed with HTTP {response.status}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a repeating 1-litre flow UI test")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between packets (default: 1)")
    parser.add_argument("--packets", type=int, default=0, help="stop after N packets; 0 runs forever")
    parser.add_argument("--dry-run", action="store_true", help="print packets without MQTT or API access")
    parser.add_argument("--dashboard", default="http://127.0.0.1:3000", help="operator dashboard URL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")
    load_local_env()

    client = None
    if not args.dry_run:
        switch_backend_to_live(args.dashboard)
        client = mqtt.Client(client_id=f"{DEVICE_ID}-{os.getpid()}")
        username = os.getenv("MQTT_DEVICE_USERNAME", "rig_device")
        password = os.getenv("MQTT_DEVICE_PASSWORD", "")
        if username:
            client.username_pw_set(username, password)
        client.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), 30)
        client.loop_start()

    seq = 0
    cycle_number = 1
    cycle_litres = 0.0
    total_litres = 0.0
    next_tick = time.monotonic()
    try:
        for rate_lpm in rate_sequence():
            if args.packets and seq >= args.packets:
                break
            seq += 1
            added_litres = rate_lpm * args.interval / 60.0
            cycle_litres += added_litres
            total_litres += added_litres
            if cycle_litres >= 1.0:
                cycle_number += int(math.floor(cycle_litres))
                cycle_litres %= 1.0

            packet = build_packet(
                rate_lpm=rate_lpm, seq=seq, cycle_litres=cycle_litres,
                cycle_number=cycle_number, total_litres=total_litres,
                timestamp=time.time(),
            )
            encoded = json.dumps(packet, separators=(",", ":"))
            if client is not None:
                info = client.publish(os.getenv("MQTT_TOPIC", "rig/telemetry"), encoded, qos=0)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f"MQTT publish failed with rc={info.rc}")
            print(
                f"cycle={cycle_number} volume={cycle_litres:.4f}/1.0000 L | "
                f"Qin={rate_lpm:.3f} Qout={rate_lpm:.3f} "
                f"Qbranch={packet['flow']['q_branch_lpm']:.3f} L/min",
                flush=True,
            )
            next_tick += args.interval
            time.sleep(max(0.0, next_tick - time.monotonic()))
    except KeyboardInterrupt:
        print("\nFlow UI test stopped.")
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
