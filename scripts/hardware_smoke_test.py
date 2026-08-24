"""Hardware smoke test — a ground-truth table for verifying the real rig end
to end, independent of what the dashboard happens to be rendering.

Polls the backend's own /api/telemetry and /api/status (the same endpoints
the dashboard uses) once a second and prints one row per sample. Use this
whenever you need an unambiguous answer to "is the ESP32 actually still
talking, and are these the real numbers" without needing the browser open.

Run: python scripts/hardware_smoke_test.py [--host http://127.0.0.1:8001] [--count N]
"""
import argparse
import sys
import time

import requests

HEADER = (
    f"{'device':<16} {'transport':<10} {'seq':>6} {'age_s':>6} | "
    f"{'Qin':>7} {'Qout':>7} {'Qbr':>7} | "
    f"{'pIn':>7} {'pOut':>7} {'pBr':>7} | "
    f"{'I_mA':>7} | {'MPU6050':>8} {'piezo':>8} | {'MQTT':>6}"
)


def fetch(host: str):
    telemetry = requests.get(f"{host}/api/telemetry", timeout=3).json()
    status = requests.get(f"{host}/api/status", timeout=3).json()
    return telemetry, status


def format_row(telemetry: dict, status: dict) -> str:
    latest = telemetry.get("latest") or {}
    if not latest:
        device = "—"
        seq = age = qin = qout = qbr = pin = pout = pbr = i_ma = "—"
    else:
        device = latest.get("device", "—")
        seq = latest.get("seq", "—")
        received_at = status.get("rig", {}).get("last_seen_ts")
        age = f"{time.time() - received_at:.1f}" if received_at else "—"
        qin = f"{latest.get('q_in', 0):.3f}"
        qout = f"{latest.get('q_out', 0):.3f}"
        qbr = f"{latest.get('q_branch', 0):.3f}"
        pin = latest.get("pulses_in", "—")
        pout = latest.get("pulses_out", "—")
        pbr = latest.get("pulses_branch", "—")
        current_ma = latest.get("current_ma")
        i_ma = f"{current_ma:.1f}" if current_ma is not None else "null"

    vib_rms = latest.get("vib_rms") if latest else None
    piezo_rms = latest.get("piezo_rms") if latest else None
    mpu_status = "present" if vib_rms is not None else "absent"
    piezo_status = "present" if piezo_rms is not None else "absent"

    transport = "mqtt" if status.get("mode") == "live" else status.get("mode", "—")
    mqtt_ok = "up" if status.get("mqtt", {}).get("connected") else "down"

    publisher = status.get("publisher", {})
    warning = ""
    if publisher.get("duplicate_publisher_suspected"):
        warning = f"  !! second publisher detected: {publisher.get('unexpected_device_ids')}"

    return (
        f"{device:<16} {transport:<10} {str(seq):>6} {str(age):>6} | "
        f"{qin:>7} {qout:>7} {qbr:>7} | "
        f"{str(pin):>7} {str(pout):>7} {str(pbr):>7} | "
        f"{i_ma:>7} | {mpu_status:>8} {piezo_status:>8} | {mqtt_ok:>6}"
        f"{warning}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="http://127.0.0.1:8001")
    ap.add_argument("--count", type=int, default=0, help="0 = run until Ctrl+C")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    print(HEADER)
    print("-" * len(HEADER))

    n = 0
    try:
        while args.count == 0 or n < args.count:
            try:
                telemetry, status = fetch(args.host)
                print(format_row(telemetry, status))
            except requests.RequestException as e:
                print(f"[smoke-test] backend unreachable at {args.host}: {e}")
            n += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
