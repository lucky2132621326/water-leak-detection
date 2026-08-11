# TROUBLESHOOTING GUIDE

| Issue | Root Cause | Verification | Solution / Fix |
| :--- | :--- | :--- | :--- |
| **No MQTT messages** | ESP32 WiFi disconnect or wrong broker IP | Check Serial monitor @ 115200 baud | Re-flash `config.h` with correct WiFi/MQTT IP |
| **Random false leak alarms** | Trapped air bubbles in flow meter chamber | Inspect clear PVC tube for bubbles | Bleed air from system at high pump speed for 2 mins |
| **Flow sensor pulse drift** | High pressure pulse skipping | Run K-factor test script | Add 100nF filtering capacitor across signal line |
| **ESP32 reboots when Servo moves** | Voltage drop on 5V rail due to servo current spike | Probe 5V pin on oscilloscope | Isolate servo power to separate 5V 2A regulator |
| **MongoDB connection timeout** | Database container not running | `docker compose ps` — status should be `Up (healthy)` | `docker compose up -d --wait` |
| **`Bootstrap failed: 5: Input/output error`** | Homebrew's `mongodb-community` launchd service failing to load. This is exactly why the project moved to Docker | `brew services list` shows `error` or `none` | Stop chasing it — run `brew services stop mongodb-community`, then `docker compose up -d`. The container publishes the same `localhost:27017`, so no config changes are needed |
| **`port is already allocated` on `docker compose up`** | A previous MongoDB (usually Homebrew) still holds 27017 | `lsof -i :27017` | `brew services stop mongodb-community`, then retry. Prefer freeing the port over remapping it — remapping forces every developer to set `MONGO_URI` |
| **Container is healthy but appears empty, while the app clearly has data** | A local `mongod` is bound to `127.0.0.1:27017` *and* Docker to `[::]:27017`. Docker does **not** report a port conflict here, because the two bind different stacks. `localhost` resolves to IPv4 first, so the app silently talks to the local mongod while `docker compose exec … mongosh` inspects the empty container | `lsof -i :27017 -sTCP:LISTEN -P -n` — more than one listener means you have this | Kill the local `mongod` (`brew services stop mongodb-community`, and `kill` any manually started one), leaving Docker as the only listener. This failure is silent: nothing errors, the data just goes somewhere unexpected |
| **Backend connects but all collections are empty** | Fresh Docker volume; nothing recorded yet | `docker compose exec mongo mongosh water_leak_detection --eval "db.telemetry.countDocuments()"` | Not a fault — Mock Data Mode generates its own telemetry. Open **Mock Scenarios** and run one, or `curl -X POST localhost:8000/api/scenarios/run -d '{"scenario_id":"large_leak"}' -H 'Content-Type: application/json'` |
| **Live Sensor Mode shows no data** | MQTT broker not started (it is opt-in) | `docker compose ps` lists no `wld-mosquitto` | `docker compose --profile live up -d`. Mock Data Mode needs no broker |

