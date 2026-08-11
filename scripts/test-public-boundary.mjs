import "dotenv/config";
import { spawn } from "node:child_process";

const root = process.cwd();
const apiKey = process.env.API_KEY || "local-dev-key-change-me";
const baseEnv = {
  ...process.env,
  NODE_ENV: "production",
  HOST: "127.0.0.1",
  FASTAPI_BASE_URL: process.env.FASTAPI_BASE_URL || "http://127.0.0.1:8001",
  API_KEY: apiKey,
};
const children = [];

function start(port, audience) {
  const child = spawn(process.execPath, ["dist/server.cjs"], {
    cwd: root,
    env: { ...baseEnv, PORT: String(port), DASHBOARD_AUDIENCE: audience },
    stdio: "ignore",
  });
  children.push(child);
}

async function waitFor(url) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function expectStatus(label, url, expected, init) {
  const response = await fetch(url, init);
  if (response.status !== expected) {
    throw new Error(`${label}: expected ${expected}, received ${response.status}`);
  }
  console.log(`PASS ${label}: ${response.status}`);
  return response;
}

try {
  start(3100, "operator");
  start(3101, "judge");
  await waitFor("http://127.0.0.1:3100/api/runtime-capabilities");
  await waitFor("http://127.0.0.1:3101/api/runtime-capabilities");

  const operatorCapabilities = await (await fetch("http://127.0.0.1:3100/api/runtime-capabilities")).json();
  const judgeCapabilities = await (await fetch("http://127.0.0.1:3101/api/runtime-capabilities")).json();
  if (operatorCapabilities.audience !== "operator" || operatorCapabilities.read_only) throw new Error("Operator capabilities are incorrect");
  if (judgeCapabilities.audience !== "judge" || !judgeCapabilities.read_only) throw new Error("Judge capabilities are incorrect");
  console.log("PASS runtime capabilities");

  const writes = [
    ["/api/mode", { mode: "replay", run_id: "RUN_001" }],
    ["/api/calibration", {}],
    ["/api/ground-truth/start", {}],
    ["/api/ground-truth/stop", {}],
    ["/api/work-orders/dispatch", {}],
    ["/api/alerts/test/resolve", {}],
    ["/api/replay/evaluate", {}],
    ["/api/impact/simulate", {}],
    ["/api/docs/README.md", { content: "blocked" }],
  ];
  for (const [route, body] of writes) {
    const response = await expectStatus(
      `judge blocks ${route}`,
      `http://127.0.0.1:3101${route}`,
      403,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    );
    const payload = await response.json();
    if (payload.code !== "PUBLIC_DEMO_READ_ONLY") throw new Error(`${route} returned the wrong error code`);
  }

  await expectStatus("judge hides docs", "http://127.0.0.1:3101/api/docs", 404);
  await expectStatus("judge hides files", "http://127.0.0.1:3101/api/files/tree", 404);
  const judgePage = await expectStatus("judge serves dashboard", "http://127.0.0.1:3101/", 200);
  if (judgePage.headers.get("x-robots-tag") !== "noindex, nofollow, noarchive") throw new Error("Judge no-index header is missing");
  if (judgePage.headers.get("x-frame-options") !== "DENY") throw new Error("Judge anti-frame header is missing");

  await expectStatus(
    "operator mode mutation reaches FastAPI",
    "http://127.0.0.1:3100/api/mode",
    200,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "replay", run_id: "RUN_001" }),
    },
  );
} finally {
  for (const child of children) child.kill("SIGTERM");
}
