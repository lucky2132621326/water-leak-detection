"""Mock Telemetry Publisher

Emits the exact rig/telemetry schema from HARDWARE_INTEGRATION_SPEC.md section
5.3 at a configurable rate, so the backend/UI can be built and tested before
the physical rig is wired. This does NOT talk to real hardware — it's a
stand-in publisher for the same MQTT topic the firmware will use.

Topology (per spec section 1): leak clamps sit at tees upstream of the two
branches; Branch A (servo, no meter) and Branch B (Q_branch meter) rejoin
before the Q_out meter. So a leak shows up as Q_in - Q_out diverging, and
Q_branch is modeled as a (noisy) fraction of whatever flow makes it past the
leak point, not a separate quantity to subtract from the mass balance here —
which "topology mode" the backend uses for its residual calc is a config
flag on the backend side (spec section 7), not something this tool decides.

Usage:
  python tools/mock_publisher.py --leak-lpm 0.5 --leak-start-s 60 --leak-duration-s 120
  python tools/mock_publisher.py --demand-mode variable --noise-std 0.05
"""
import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="rig/telemetry")
    p.add_argument("--device", default="mock-rig-01")
    p.add_argument("--rate-hz", type=float, default=1.0)
    p.add_argument("--duration-s", type=float, default=0.0, help="0 = run until Ctrl+C")

    p.add_argument("--k1", type=float, default=450.0, help="pulses/litre, Q_in sensor")
    p.add_argument("--k2", type=float, default=450.0, help="pulses/litre, Q_out sensor")
    p.add_argument("--k3", type=float, default=450.0, help="pulses/litre, Q_branch sensor")

    p.add_argument("--baseline-lpm", type=float, default=5.0, help="steady-state Q_in")
    p.add_argument("--bias-lpm", type=float, default=0.02, help="natural zero-leak Q_in - Q_out offset")
    p.add_argument("--branch-fraction", type=float, default=0.35, help="fraction of post-leak flow through Branch B")
    p.add_argument("--noise-std", type=float, default=0.03, help="gaussian noise std dev on flow readings, L/min")

    p.add_argument("--demand-mode", choices=["steady", "variable"], default="steady",
                    help="variable cycles P2 (demand) with a sine wave to fluctuate Q_out independent of leaks")
    p.add_argument("--demand-period-s", type=float, default=60.0)
    p.add_argument("--demand-amplitude-lpm", type=float, default=0.4)

    p.add_argument("--leak-lpm", type=float, default=0.0, help="0 = no leak this run")
    p.add_argument("--leak-start-s", type=float, default=0.0, help="seconds after start the leak begins")
    p.add_argument("--leak-duration-s", type=float, default=0.0, help="0 = leak runs until process stops, once started")

    p.add_argument("--baseline-current-ma", type=float, default=650.0)
    p.add_argument("--bus-v", type=float, default=11.95)

    return p.parse_args()


def flow_to_pulses(q_lpm: float, k_factor: float, window_seconds: float) -> int:
    # Inverse of spec 5.2: Q_lpm = (pulses / K) * (60 / window_seconds)
    pulses = q_lpm * k_factor * window_seconds / 60.0
    return max(0, round(pulses))


def main():
    args = parse_args()

    client = mqtt.Client(client_id=f"mock-publisher-{args.device}")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    print(f"[mock_publisher] Publishing to {args.host}:{args.port}/{args.topic} as device={args.device} "
          f"at {args.rate_hz} Hz (leak_lpm={args.leak_lpm}, demand_mode={args.demand_mode})")

    window_seconds = 1.0 / args.rate_hz
    seq = 0
    start_time = time.monotonic()
    total_pulses_in = total_pulses_out = total_pulses_branch = 0

    try:
        while True:
            now = time.monotonic()
            elapsed = now - start_time
            if args.duration_s > 0 and elapsed >= args.duration_s:
                break

            q_in = args.baseline_lpm
            if args.demand_mode == "variable":
                q_in += args.demand_amplitude_lpm * math.sin(2 * math.pi * elapsed / args.demand_period_s)
            q_in = max(0.0, q_in + random.gauss(0, args.noise_std))

            leak_active = (
                args.leak_lpm > 0
                and elapsed >= args.leak_start_s
                and (args.leak_duration_s <= 0 or elapsed < args.leak_start_s + args.leak_duration_s)
            )
            active_leak_lpm = args.leak_lpm if leak_active else 0.0

            q_out = max(0.0, q_in - args.bias_lpm - active_leak_lpm + random.gauss(0, args.noise_std))
            q_branch = max(0.0, q_out * args.branch_fraction + random.gauss(0, args.noise_std * 0.5))

            pulses_in = flow_to_pulses(q_in, args.k1, window_seconds)
            pulses_out = flow_to_pulses(q_out, args.k2, window_seconds)
            pulses_branch = flow_to_pulses(q_branch, args.k3, window_seconds)
            total_pulses_in += pulses_in
            total_pulses_out += pulses_out
            total_pulses_branch += pulses_branch

            current_ma = args.baseline_current_ma + random.gauss(0, 5.0)
            bus_v = args.bus_v + random.gauss(0, 0.02)
            power_mw = round(bus_v * current_ma, 1)

            payload = {
                "ts": round(time.time(), 3),
                "seq": seq,
                "device": args.device,
                "flow": {
                    "q_in_lpm": round(q_in, 3),
                    "q_out_lpm": round(q_out, 3),
                    "q_branch_lpm": round(q_branch, 3),
                    "pulses_in": pulses_in,
                    "pulses_out": pulses_out,
                    "pulses_branch": pulses_branch,
                },
                "power": {
                    "bus_v": round(bus_v, 2),
                    "current_ma": round(current_ma, 1),
                    "power_mw": power_mw,
                },
                "actuators": {
                    "pump1": True,
                    "pump2": args.demand_mode == "variable",
                    "servo_deg": 0,
                },
                "health": {
                    "uptime_s": int(elapsed),
                    "wifi_rssi": -58 + random.randint(-4, 4),
                    "free_heap": 184320 - random.randint(0, 2000),
                },
            }

            client.publish(args.topic, json.dumps(payload), qos=1)
            leak_marker = " [LEAK]" if leak_active else ""
            print(f"seq={seq:<6} q_in={q_in:.2f} q_out={q_out:.2f} q_branch={q_branch:.2f}{leak_marker}")

            seq += 1
            time.sleep(window_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        print("[mock_publisher] Stopped.")


if __name__ == "__main__":
    main()
