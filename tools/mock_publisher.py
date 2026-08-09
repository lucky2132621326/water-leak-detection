"""Mock Telemetry Publisher

Emits the exact rig/telemetry schema from docs/HARDWARE_INTEGRATION_SPEC.md
section 5.4 at a configurable rate, so the backend/UI can be built and tested
before the physical rig is wired. This does NOT talk to real hardware — it's
a stand-in publisher for the same MQTT topic the firmware will use.

Topology (per spec section 1): leak clamps sit at tees upstream of the two
branches; Branch A (servo, no meter) and Branch B (Q_branch meter) rejoin
before the Q_out meter. So a leak shows up as Q_in - Q_out diverging, and
Q_branch is modeled as a (noisy) fraction of whatever flow makes it past the
leak point, not a separate quantity to subtract from the mass balance here —
which "topology mode" the backend uses for its residual calc is a config
flag on the backend side (spec section 7), not something this tool decides.

Acoustic channel (spec section 6, channel 5): band energies are meaningless
in absolute terms, only relative to a clean baseline. This tool models a
steady baseline spectrum and elevates band_mid specifically during a leak
(leak-jet energy concentrates 50-150 Hz), leaving band_low/band_high mostly
flat — the same signature the real detector's ratio-to-baseline logic should
key on.

Usage:
  python tools/mock_publisher.py --leak-lpm 0.5 --leak-start-s 60 --leak-duration-s 120
  python tools/mock_publisher.py --demand-mode variable --noise-std 0.05
  python tools/mock_publisher.py --leak-lpm 0.3 --leak-start-s 30 --vib-leak-elevation 3.0
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

    # Acoustic (MPU6050 + piezo) — spec section 5.3/5.4/6. Absolute band values
    # are meaningless; only band_mid's ratio to its own baseline matters.
    p.add_argument("--vib-baseline-low", type=float, default=0.010, help="clean-running band_low (10-50 Hz)")
    p.add_argument("--vib-baseline-mid", type=float, default=0.015, help="clean-running band_mid (50-150 Hz)")
    p.add_argument("--vib-baseline-high", type=float, default=0.020, help="clean-running band_high (150-250 Hz)")
    p.add_argument("--vib-leak-elevation", type=float, default=2.8,
                    help="multiplier applied to band_mid only while a leak is active")
    p.add_argument("--vib-noise-std", type=float, default=0.002)
    p.add_argument("--piezo-baseline-rms", type=float, default=0.012)
    p.add_argument("--piezo-leak-elevation", type=float, default=2.2)
    p.add_argument("--piezo-baseline-centroid-hz", type=float, default=95.0)
    p.add_argument("--piezo-leak-centroid-hz", type=float, default=140.0,
                    help="centroid shifts toward the leak-jet band while active")

    # Temperature (DS18B20) — spec section 6, K-factor compensation input.
    p.add_argument("--water-temp-c", type=float, default=24.0, help="starting reservoir temperature")
    p.add_argument("--water-temp-drift-c-per-hour", type=float, default=0.0,
                    help="simulates pump-warming drift over a long run; 0 = flat")

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

            current_ma = args.baseline_current_ma + random.gauss(0, 5.0)
            bus_v = args.bus_v + random.gauss(0, 0.02)
            power_mw = round(bus_v * current_ma, 1)

            band_low = max(0.0, args.vib_baseline_low + random.gauss(0, args.vib_noise_std))
            band_mid_baseline = args.vib_baseline_mid * (args.vib_leak_elevation if leak_active else 1.0)
            band_mid = max(0.0, band_mid_baseline + random.gauss(0, args.vib_noise_std))
            band_high = max(0.0, args.vib_baseline_high + random.gauss(0, args.vib_noise_std))
            vib_rms = round(math.sqrt(band_low ** 2 + band_mid ** 2 + band_high ** 2), 4)

            piezo_rms = max(0.0, (args.piezo_baseline_rms * (args.piezo_leak_elevation if leak_active else 1.0))
                             + random.gauss(0, args.vib_noise_std * 0.5))
            piezo_centroid_hz = (args.piezo_leak_centroid_hz if leak_active else args.piezo_baseline_centroid_hz) \
                + random.gauss(0, 3.0)

            water_c = args.water_temp_c + (args.water_temp_drift_c_per_hour * elapsed / 3600.0) + random.gauss(0, 0.05)

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
                "vibration": {
                    "rms": vib_rms,
                    "band_low": round(band_low, 4),
                    "band_mid": round(band_mid, 4),
                    "band_high": round(band_high, 4),
                    "piezo_rms": round(piezo_rms, 4),
                    "piezo_centroid_hz": round(piezo_centroid_hz, 1),
                },
                "temp": {
                    "water_c": round(water_c, 2),
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
            print(f"seq={seq:<6} q_in={q_in:.2f} q_out={q_out:.2f} q_branch={q_branch:.2f} "
                  f"band_mid={band_mid:.4f}{leak_marker}")

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
