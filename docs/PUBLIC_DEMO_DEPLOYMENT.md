# Public Hackathon Demo

The deployed demo is hybrid: MongoDB, FastAPI, MQTT, and the ESP32 remain on
the rig laptop. Only a separate read-only Node dashboard is exposed through a
temporary Cloudflare Quick Tunnel.

## One-command launch

Make sure MongoDB is running. The Windows demo laptop keeps Mosquitto under
`.tools/mosquitto`; when port 1883 is free, the launcher starts it with a
generated password file and least-privilege ACL. Configure separate
`rig_backend` and `rig_device` passwords in the Git-ignored `.env`, and copy
the device password to `firmware/src/secrets.h`.

`MQTT_BIND_ADDRESS` defaults to `127.0.0.1`. Set it only to the laptop address
on the dedicated private rig network when the ESP32 is ready. The launcher
refuses wildcard values such as `0.0.0.0`.

The official Windows installer registers an automatic Mosquitto service. The
launcher writes the same private config to the service install directory, but
an administrator must restart that service once before hardware commissioning
so the generated password file, ACL and rig-interface binding take effect.

Run: npm run demo:public

The launcher builds the production application, starts:

- FastAPI on 127.0.0.1:8001
- the operator dashboard on 127.0.0.1:3000
- the judge dashboard on 127.0.0.1:3001
- the authenticated Mosquitto broker on loopback and, when configured, the
  dedicated rig-interface address
- a tunnel exposing only the judge dashboard

It prints a random https://*.trycloudflare.com judge URL and records it in the
ignored `.tools/public-demo-url.txt`. Press Ctrl+C once to stop all supervised
child processes. The URL changes each time and works only
while the laptop and launcher remain running.

## Security boundary

The judge process rejects every non-GET API request with
403 PUBLIC_DEMO_READ_ONLY. It also hides repository and documentation APIs,
sets no-index and anti-framing headers, and never exposes the FastAPI API key.
The operator process remains local and retains the existing supervised
actions.

Ports 8001, 1883, and 27017 are never tunneled. Restrict the broker's Windows
Firewall rule to the rig's private network. The example Mosquitto ACL allows
the ESP32 to publish telemetry/status and receive commands; the backend can
consume telemetry/status and publish supervised commands.

## Demo readiness

If MQTT is missing, the public dashboard starts in clearly labelled Replay
mode rather than pretending the rig is connected. A live claim requires a
fresh, non-mock esp32-rig-01 frame and a successful PlatformIO build/flash.

Before sharing the link, run the Python tests, backend self-test, frontend
lint, and production build.
