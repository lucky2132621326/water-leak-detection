import "dotenv/config";
import { spawn, spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const toolsDir = path.join(root, ".tools");
const cloudflaredPath = path.join(toolsDir, "cloudflared.exe");
const publicUrlPath = process.env.PUBLIC_URL_PATH
  ? path.resolve(root, process.env.PUBLIC_URL_PATH)
  : path.join(toolsDir, "public-demo-url.txt");
const mosquittoHome = process.env.MOSQUITTO_HOME || path.join(toolsDir, "mosquitto");
const apiPort = Number(process.env.API_PORT || 8001);
const operatorPort = Number(process.env.PORT || 3000);
const judgePort = Number(process.env.PUBLIC_PORT || 3001);
const pythonCommand = process.env.PYTHON_COMMAND || "python";
const children = [];
let shuttingDown = false;

function tcpReady(host, port, timeoutMs = 800) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const finish = (ready) => {
      socket.destroy();
      resolve(ready);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
  });
}

async function waitForJson(url, predicate, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (response.ok) {
        const data = await response.json();
        if (predicate(data)) return data;
      }
    } catch {
      // Service is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function managedSpawn(name, command, args, env = process.env) {
  const child = spawn(command, args, { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  child.stdout.on("data", (chunk) => process.stdout.write(`[${name}] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[${name}] ${chunk}`));
  child.once("exit", (code) => {
    if (!shuttingDown) {
      console.error(`[public-demo] ${name} exited unexpectedly with code ${code}`);
      shutdown(code || 1);
    }
  });
  return child;
}

async function downloadCloudflared() {
  if (fs.existsSync(cloudflaredPath) && fs.statSync(cloudflaredPath).size > 1_000_000) return;
  if (process.platform !== "win32" || process.arch !== "x64") {
    throw new Error("Automatic cloudflared bootstrap currently supports Windows x64 only.");
  }

  fs.mkdirSync(toolsDir, { recursive: true });
  const tempPath = `${cloudflaredPath}.download`;
  console.log("[public-demo] Downloading the official Cloudflare Tunnel client...");
  const response = await fetch(
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    { redirect: "follow", signal: AbortSignal.timeout(120000) },
  );
  if (!response.ok || !response.body) throw new Error(`cloudflared download failed (${response.status})`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length < 1_000_000 || bytes[0] !== 0x4d || bytes[1] !== 0x5a) {
    throw new Error("Downloaded cloudflared file did not pass the Windows executable sanity check.");
  }
  fs.writeFileSync(tempPath, bytes);
  fs.renameSync(tempPath, cloudflaredPath);
}

async function ensureMqttBroker(host, port) {
  const brokerAlreadyRunning = await tcpReady(host, port);

  const brokerPath = path.join(mosquittoHome, "mosquitto.exe");
  const passwordTool = path.join(mosquittoHome, "mosquitto_passwd.exe");
  const backendUsername = process.env.MQTT_USERNAME;
  const backendPassword = process.env.MQTT_PASSWORD;
  const deviceUsername = process.env.MQTT_DEVICE_USERNAME;
  const devicePassword = process.env.MQTT_DEVICE_PASSWORD;
  if (!fs.existsSync(brokerPath) || !fs.existsSync(passwordTool)) return brokerAlreadyRunning;
  if (!backendUsername || !backendPassword || !deviceUsername || !devicePassword) {
    throw new Error("Mosquitto is installed, but separate backend/device credentials are missing from .env.");
  }

  const bindAddress = process.env.MQTT_BIND_ADDRESS || "127.0.0.1";
  if (["0.0.0.0", "::", "*"].includes(bindAddress)) {
    throw new Error("MQTT_BIND_ADDRESS must be loopback or the dedicated rig-interface IP, never a wildcard address.");
  }

  const runtimeDir = path.join(toolsDir, "mqtt-runtime");
  const passwordFile = path.join(runtimeDir, "passwords");
  const aclFile = path.join(runtimeDir, "acl");
  const configFile = path.join(runtimeDir, "mosquitto.conf");
  fs.mkdirSync(runtimeDir, { recursive: true });

  const createPassword = spawnSync(passwordTool, ["-b", "-c", passwordFile, backendUsername, backendPassword], { stdio: "ignore" });
  const addDevicePassword = spawnSync(passwordTool, ["-b", passwordFile, deviceUsername, devicePassword], { stdio: "ignore" });
  if (createPassword.status !== 0 || addDevicePassword.status !== 0) {
    throw new Error("Could not create the private Mosquitto password file.");
  }

  fs.writeFileSync(aclFile, [
    `user ${deviceUsername}`,
    "topic write rig/telemetry",
    "topic write rig/status",
    "topic read rig/cmd",
    "",
    `user ${backendUsername}`,
    "topic read rig/telemetry",
    "topic read rig/status",
    "topic write rig/cmd",
    "",
  ].join("\n"), "utf8");

  const listeners = ["listener 1883 127.0.0.1"];
  if (bindAddress !== "127.0.0.1") listeners.push(`listener 1883 ${bindAddress}`);
  const mosquittoPath = (value) => value.replaceAll("\\", "/");
  const configContents = [
    ...listeners,
    "socket_domain ipv4",
    "allow_anonymous false",
    `password_file ${mosquittoPath(passwordFile)}`,
    `acl_file ${mosquittoPath(aclFile)}`,
    "persistence false",
    "connection_messages true",
    "log_dest stdout",
    "log_type error",
    "log_type warning",
    "log_type notice",
    "",
  ].join("\n");
  fs.writeFileSync(configFile, configContents, "utf8");
  // The official Windows installer registers a service by default. Keeping
  // its install-directory config synchronized means its next administrator-
  // initiated restart applies the same password file, ACL and narrow binds.
  fs.writeFileSync(path.join(mosquittoHome, "mosquitto.conf"), configContents, "utf8");

  if (brokerAlreadyRunning) {
    console.warn("[public-demo] MQTT port is owned by an existing broker. Secure config is prepared; restart that broker before hardware commissioning to enforce it.");
    return true;
  }

  managedSpawn("mqtt", brokerPath, ["-c", configFile, "-v"]);
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (await tcpReady(host, port)) return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Mosquitto did not become ready on ${host}:${port}.`);
}

function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of [...children].reverse()) {
    if (!child.killed) child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(exitCode), 800);
}

async function main() {
  fs.rmSync(publicUrlPath, { force: true });
  for (const [name, port] of [["FastAPI", apiPort], ["operator dashboard", operatorPort], ["judge dashboard", judgePort]]) {
    if (await tcpReady("127.0.0.1", port)) {
      throw new Error(`${name} port ${port} is already in use. Stop the existing project process before starting the public demo.`);
    }
  }

  const mongoReady = await tcpReady("127.0.0.1", 27017);
  if (!mongoReady) throw new Error("MongoDB is not listening on 127.0.0.1:27017.");

  const mqttHost = process.env.MQTT_HOST || "127.0.0.1";
  const mqttPort = Number(process.env.MQTT_PORT || 1883);
  const mqttReady = await ensureMqttBroker(mqttHost, mqttPort);
  if (!mqttReady) {
    console.warn("[public-demo] MQTT is unavailable; install Mosquitto or set MOSQUITTO_HOME. The judge view will remain visibly in Replay mode.");
  } else {
    console.log(`[public-demo] MQTT ready on ${mqttHost}:${mqttPort}; waiting for a fresh ESP32 stream before live mode.`);
  }

  await downloadCloudflared();
  const apiKey = !process.env.API_KEY || process.env.API_KEY === "local-dev-key-change-me"
    ? crypto.randomBytes(32).toString("base64url")
    : process.env.API_KEY;
  const commonEnv = {
    ...process.env,
    NODE_ENV: "production",
    API_KEY: apiKey,
    FASTAPI_BASE_URL: `http://127.0.0.1:${apiPort}`,
    HOST: "127.0.0.1",
  };

  managedSpawn("api", pythonCommand, ["-m", "uvicorn", "backend.api_server:app", "--host", "127.0.0.1", "--port", String(apiPort)], commonEnv);
  await waitForJson(`http://127.0.0.1:${apiPort}/api/health`, (data) => typeof data?.status === "string");

  managedSpawn("operator", process.execPath, ["dist/server.cjs"], {
    ...commonEnv,
    PORT: String(operatorPort),
    DASHBOARD_AUDIENCE: "operator",
  });
  managedSpawn("judge", process.execPath, ["dist/server.cjs"], {
    ...commonEnv,
    PORT: String(judgePort),
    DASHBOARD_AUDIENCE: "judge",
  });

  await waitForJson(`http://127.0.0.1:${operatorPort}/api/runtime-capabilities`, (data) => data?.audience === "operator");
  await waitForJson(`http://127.0.0.1:${judgePort}/api/runtime-capabilities`, (data) => data?.audience === "judge" && data?.read_only === true);

  const cloudflared = managedSpawn(
    "tunnel",
    cloudflaredPath,
    ["tunnel", "--no-autoupdate", "--url", `http://127.0.0.1:${judgePort}`],
    commonEnv,
  );
  const urlPattern = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i;
  let announced = false;
  const inspectUrl = (chunk) => {
    if (announced) return;
    const match = chunk.toString().match(urlPattern);
    if (match) {
      announced = true;
      fs.writeFileSync(publicUrlPath, `${match[0]}\n`, "utf8");
      console.log(`\n[public-demo] JUDGE URL: ${match[0]}`);
      console.log(`[public-demo] Local operator dashboard: http://127.0.0.1:${operatorPort}`);
      console.log("[public-demo] Press Ctrl+C once to stop both dashboards, the API, and the tunnel.\n");
      const selfStopMs = Number(process.env.PUBLIC_DEMO_SELF_STOP_MS || 0);
      if (selfStopMs > 0) setTimeout(() => shutdown(0), selfStopMs);
    }
  };
  cloudflared.stdout.on("data", inspectUrl);
  cloudflared.stderr.on("data", inspectUrl);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("uncaughtException", (error) => {
  console.error(`[public-demo] ${error.message}`);
  shutdown(1);
});
process.on("unhandledRejection", (error) => {
  console.error(`[public-demo] ${error instanceof Error ? error.message : error}`);
  shutdown(1);
});

main().catch((error) => {
  console.error(`[public-demo] ${error.message}`);
  shutdown(1);
});
