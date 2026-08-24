"""USB-serial-to-MQTT bridge for the ESP32 rig.

The ESP32 is USB-only right now (no WiFi/MQTT on the device itself). This
script reads its human-readable [TELEMETRY] line over the COM port, rebuilds
the same nested JSON document the firmware would otherwise publish over MQTT,
and publishes it to the LOCAL broker on the rig's behalf — so the existing
backend/dashboard pipeline (which only knows how to read MQTT) needs no
changes at all.

Run: python scripts/usb_serial_bridge.py
"""
import json
import os
import re
import sys
import time

import paho.mqtt.client as mqtt
import serial

COM_PORT = os.environ.get("RIG_COM_PORT", "COM3")
BAUD = 115200
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_DEVICE_USERNAME", "rig_device")
MQTT_PASSWORD = os.environ.get("MQTT_DEVICE_PASSWORD", "")
DEVICE_ID = "esp32-rig-01"
TOPIC_TELEMETRY = "rig/telemetry"
# Must match firmware/src/config.h — bump both together on a wire-schema change.
FW_VERSION = "1.1.0"
SCHEMA_VERSION = 1

LINE_RE = re.compile(
    r"\[TELEMETRY\] seq=(\d+) Qin=([\d.]+) Qout=([\d.]+) Qbr=([\d.]+) L/min \| "
    r"pulses\(in/out/br\)=(\d+)/(\d+)/(\d+) \| "
    r"V=([\w.\-]+)V I=([\w.\-]+)mA P=([\w.\-]+)mW \| "
    r"water=([\w.\-]+)C \| "
    r"vib=(present|NOT-FOUND) rms=([\d.]+) \| "
    r"piezo=(present|NOT-FOUND) rms=([\d.]+) centroid=([\d.]+)Hz \| "
    r"pump1=(\d) pump2=(\d) servo=(-?\d+)"
)


def _num(s):
    try:
        v = float(s)
        return None if v != v else v  # NaN -> None
    except ValueError:
        return None  # "nan", "inf", etc.


def parse_line(line: str):
    m = LINE_RE.search(line)
    if not m:
        return None
    (seq, qin, qout, qbr, pin, pout, pbr, v, i, p, water,
     vib_present, vib_rms, piezo_present, piezo_rms, piezo_centroid,
     pump1, pump2, servo) = m.groups()

    vib_on = vib_present == "present"
    piezo_on = piezo_present == "present"

    return {
        "ts": time.time(),
        # The firmware's own counter, not one the bridge invents — a gap here
        # means a line was lost between the ESP32 and this process, not just
        # "nothing arrived for a while."
        "seq": int(seq),
        "device": DEVICE_ID,
        "fw_version": FW_VERSION,
        "schema_version": SCHEMA_VERSION,
        "transport": "usb_serial_bridge",
        "mode": "live",
        "clock_synced": False,
        "flow": {
            "q_in_lpm": float(qin),
            "q_out_lpm": float(qout),
            "q_branch_lpm": float(qbr),
            "pulses_in": int(pin),
            "pulses_out": int(pout),
            "pulses_branch": int(pbr),
        },
        "power": {
            "bus_v": _num(v),
            "current_ma": _num(i),
            "power_mw": _num(p),
        },
        "vibration": {
            "rms": float(vib_rms) if vib_on else None,
            "band_low": 0.0 if vib_on else None,
            "band_mid": 0.0 if vib_on else None,
            "band_high": 0.0 if vib_on else None,
            "piezo_rms": float(piezo_rms) if piezo_on else None,
            "piezo_centroid_hz": float(piezo_centroid) if piezo_on else None,
        },
        "temp": {"water_c": _num(water)},
        "actuators": {
            "pump1": pump1 == "1",
            "pump2": pump2 == "1",
            "servo_deg": int(servo),
        },
        "health": {
            "uptime_s": 0,
            "wifi_rssi": -100,
            "free_heap": 0,
        },
    }


def main():
    client = mqtt.Client()
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    print(f"[bridge] MQTT connected to {MQTT_HOST}:{MQTT_PORT}, publishing to {TOPIC_TELEMETRY}")

    ser = serial.Serial(COM_PORT, BAUD, timeout=1)
    print(f"[bridge] reading {COM_PORT} @ {BAUD}")

    while True:
        raw = ser.readline()
        if not raw:
            continue
        try:
            line = raw.decode("utf-8", errors="replace").rstrip()
        except Exception:
            continue
        if not line:
            continue
        print(line)
        doc = parse_line(line)
        if doc is None:
            continue
        client.publish(TOPIC_TELEMETRY, json.dumps(doc), qos=0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
