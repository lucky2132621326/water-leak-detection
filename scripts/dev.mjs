import "dotenv/config";
import fs from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";

function resolvePythonCommand() {
  const venvCandidates = process.platform === "win32"
    ? [
        path.resolve(".venv", "Scripts", "python.exe"),
        path.resolve(".venv", "Scripts", "python"),
      ]
    : [
        path.resolve(".venv", "bin", "python"),
      ];

  for (const candidate of venvCandidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return "python";
}

const pythonCommand = process.env.PYTHON_COMMAND || resolvePythonCommand();
const apiPort = process.env.API_PORT || "8001";
const webPort = process.env.PORT || "3000";
const childEnvironment = {
  ...process.env,
  PORT: webPort,
  FASTAPI_BASE_URL: process.env.FASTAPI_BASE_URL || `http://localhost:${apiPort}`,
};

const api = spawn(
  pythonCommand,
  ["-m", "uvicorn", "backend.api_server:app", "--host", "0.0.0.0", "--port", apiPort],
  { stdio: "inherit", env: childEnvironment },
);

const tsxCli = path.resolve("node_modules", "tsx", "dist", "cli.mjs");
const web = spawn(process.execPath, [tsxCli, "server.ts"], {
  stdio: "inherit",
  env: childEnvironment,
});

const children = [api, web];
let shuttingDown = false;

function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(exitCode), 500);
}

for (const [name, child] of [["Detection API", api], ["Web dashboard", web]]) {
  child.on("error", (error) => {
    console.error(`[${name}] failed to start:`, error.message);
    shutdown(1);
  });
  child.on("exit", (code) => {
    if (!shuttingDown && code !== 0) {
      console.error(`[${name}] exited with code ${code}`);
      shutdown(code || 1);
    }
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
