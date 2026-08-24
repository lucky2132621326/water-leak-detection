import "dotenv/config";
import express from "express";
import path from "path";
import fs from "fs";
import net from "net";
import { createServer as createViteServer } from "vite";

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8001";
const FASTAPI_API_KEY = process.env.API_KEY || "local-dev-key-change-me";
const DASHBOARD_AUDIENCE = process.env.DASHBOARD_AUDIENCE === "judge" ? "judge" : "operator";
const IS_JUDGE_VIEW = DASHBOARD_AUDIENCE === "judge";
const WORKSPACE_ROOT = path.resolve(process.cwd());
const SENSITIVE_FILENAMES = new Set([".env", "secrets.h"]);
const DEFAULT_FASTAPI_TIMEOUT_MS = 4_000;
const LONG_RUNNING_FASTAPI_TIMEOUT_MS = 300_000;
const LONG_RUNNING_API_PATHS = new Set(["/api/scenarios/run", "/api/benchmark/evaluate"]);

function resolveInsideWorkspace(relativePath: string) {
  const resolved = path.resolve(WORKSPACE_ROOT, relativePath);
  const relative = path.relative(WORKSPACE_ROOT, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  if (SENSITIVE_FILENAMES.has(path.basename(resolved)) || path.basename(resolved).startsWith(".env")) return null;
  return resolved;
}

async function startServer() {
  const app = express();
  const PORT = Number(process.env.PORT || 3000);
  const HOST = process.env.HOST || "0.0.0.0";

  app.disable("x-powered-by");
  app.use(express.json({ limit: "32kb" }));
  app.use((req, res, next) => {
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("X-Frame-Options", "DENY");
    if (req.path.startsWith("/api/")) res.setHeader("Cache-Control", "no-store");

    if (IS_JUDGE_VIEW) {
      res.setHeader("X-Robots-Tag", "noindex, nofollow, noarchive");
      if (process.env.NODE_ENV === "production") {
        res.setHeader(
          "Content-Security-Policy",
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        );
      }
      if (!["GET", "HEAD", "OPTIONS"].includes(req.method)) {
        res.status(403).json({
          status: "error",
          code: "PUBLIC_DEMO_READ_ONLY",
          message: "The judge-facing dashboard is read-only. Use the local operator dashboard for changes.",
        });
        return;
      }
      if (req.path.startsWith("/api/files") || req.path.startsWith("/api/docs")) {
        res.status(404).json({
          status: "error",
          code: "PUBLIC_DEMO_ROUTE_HIDDEN",
          message: "This route is not available in the judge view.",
        });
        return;
      }
    }
    next();
  });

  app.get("/api/runtime-capabilities", (_req, res) => {
    res.json({
      audience: DASHBOARD_AUDIENCE,
      read_only: IS_JUDGE_VIEW,
      mutations_allowed: !IS_JUDGE_VIEW,
    });
  });

  app.get("/robots.txt", (_req, res) => {
    res.type("text/plain").send("User-agent: *\nDisallow: /\n");
  });

  // Thin proxy to the Python FastAPI service (backend/api_server.py), which
  // owns real detection state for whichever operating mode is active (Mock Data
  // or Live Sensor — same pipeline either way). Node neither generates nor
  // evaluates telemetry itself.
  async function proxyToFastApi(req: express.Request, res: express.Response, fastApiPath: string) {
    try {
      const query = req.originalUrl.includes("?") ? req.originalUrl.slice(req.originalUrl.indexOf("?")) : "";
      const url = `${FASTAPI_BASE_URL}${fastApiPath}${query}`;
      const timeoutMs = LONG_RUNNING_API_PATHS.has(fastApiPath)
        ? LONG_RUNNING_FASTAPI_TIMEOUT_MS
        : DEFAULT_FASTAPI_TIMEOUT_MS;
      const init: RequestInit = {
        method: req.method,
        headers: { "Content-Type": "application/json", "X-API-Key": FASTAPI_API_KEY },
        signal: AbortSignal.timeout(timeoutMs),
      };
      if (req.method !== "GET" && req.method !== "HEAD") {
        init.body = JSON.stringify(req.body ?? {});
      }
      const upstream = await fetch(url, init);

      // The printable experiment report comes back as HTML, not JSON — pass it
      // through verbatim so it can be opened in a tab and saved as a PDF.
      const contentType = upstream.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) {
        const text = await upstream.text();
        res.status(upstream.status).type(contentType || "text/plain").send(text);
        return;
      }

      const data = await upstream.json();
      res.status(upstream.status).json(data);
    } catch (_e) {
      const isLongRunning = LONG_RUNNING_API_PATHS.has(fastApiPath);
      res.status(502).json({
        status: "error",
        code: "DETECTION_BACKEND_UNAVAILABLE",
        message: isLongRunning
          ? "The scoring operation did not complete within five minutes."
          : "The detection service did not respond within four seconds.",
      });
    }
  }

  // Static one-to-one proxies. Paths with :params are registered separately
  // below because the upstream path has to be rebuilt from req.params.
  const PROXIED_ROUTES: Array<{ method: "get" | "post"; path: string }> = [
    { method: "get", path: "/api/health" },
    { method: "get", path: "/api/mode" },
    { method: "post", path: "/api/mode" },
    { method: "get", path: "/api/telemetry" },
    { method: "get", path: "/api/telemetry/history" },
    { method: "post", path: "/api/leak/toggle" },
    { method: "get", path: "/api/benchmark/runs" },
    { method: "post", path: "/api/benchmark/evaluate" },
    { method: "get", path: "/api/localization/current" },
    { method: "get", path: "/api/work-orders" },
    { method: "post", path: "/api/work-orders/dispatch" },
    { method: "get", path: "/api/impact/config" },
    { method: "get", path: "/api/impact/current" },
    { method: "post", path: "/api/impact/simulate" },
    { method: "get", path: "/api/alerts" },
    { method: "get", path: "/api/alerts/summary" },
    { method: "get", path: "/api/savings" },
    { method: "get", path: "/api/status" },
    { method: "get", path: "/api/analytics/summary" },
    { method: "get", path: "/api/analytics/roc" },
    { method: "get", path: "/api/detectors/config" },
    { method: "get", path: "/api/scenarios" },
    { method: "post", path: "/api/scenarios/run" },
    { method: "get", path: "/api/mock/control" },
    { method: "post", path: "/api/mock/control/release" },
    { method: "get", path: "/api/calibration" },
    { method: "post", path: "/api/calibration" },
    { method: "get", path: "/api/config" },
    { method: "post", path: "/api/self-test" },
    { method: "get", path: "/api/experiments/status" },
    { method: "post", path: "/api/experiments/start" },
    { method: "post", path: "/api/experiments/stop" },
    { method: "post", path: "/api/experiments/ground-truth/start" },
    { method: "post", path: "/api/experiments/ground-truth/stop" },
  ];

  for (const route of PROXIED_ROUTES) {
    app[route.method](route.path, (req, res) => proxyToFastApi(req, res, route.path));
  }

  const PARAM_ROUTES: Array<{ method: "get" | "post"; path: string; upstream: (p: any) => string }> = [
    { method: "post", path: "/api/alerts/:alertId/resolve", upstream: (p) => `/api/alerts/${encodeURIComponent(p.alertId)}/resolve` },
    { method: "post", path: "/api/alerts/:alertId/false-positive", upstream: (p) => `/api/alerts/${encodeURIComponent(p.alertId)}/false-positive` },
    { method: "post", path: "/api/alerts/:alertId/reopen", upstream: (p) => `/api/alerts/${encodeURIComponent(p.alertId)}/reopen` },
    { method: "get", path: "/api/reports/experiment/:runId", upstream: (p) => `/api/reports/experiment/${encodeURIComponent(p.runId)}` },
    { method: "get", path: "/api/reports/experiment/:runId/html", upstream: (p) => `/api/reports/experiment/${encodeURIComponent(p.runId)}/html` },
  ];

  for (const route of PARAM_ROUTES) {
    app[route.method](route.path, (req, res) => proxyToFastApi(req, res, route.upstream(req.params)));
  }

  // Documentation APIs
  app.get("/api/docs", (req, res) => {
    const docsDir = path.join(process.cwd(), "docs");
    try {
      const files = fs.readdirSync(docsDir).filter(f => f.endsWith(".md"));
      res.json(files);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.get("/api/docs/:filename", (req, res) => {
    const filename = path.basename(req.params.filename);
    const filePath = filename.endsWith(".md") ? resolveInsideWorkspace(path.join("docs", filename)) : null;
    try {
      if (filePath && fs.existsSync(filePath)) {
        const content = fs.readFileSync(filePath, "utf-8");
        res.json({ filename, content });
      } else {
        res.status(404).json({ error: "File not found" });
      }
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.post("/api/docs/:filename", (req, res) => {
    const filename = path.basename(req.params.filename);
    const { content } = req.body;
    const filePath = filename.endsWith(".md") ? resolveInsideWorkspace(path.join("docs", filename)) : null;
    try {
      if (!filePath || typeof content !== "string") return res.status(400).json({ error: "Valid Markdown filename and content required" });
      fs.writeFileSync(filePath, content, "utf-8");
      res.json({ success: true, filename });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Codebase Tree API
  app.get("/api/files/tree", (req, res) => {
    function buildTree(dir: string, baseRelative = ""): any[] {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      const items: any[] = [];
      for (const entry of entries) {
        if (entry.name === "node_modules" || entry.name === ".git" || entry.name === "dist") continue;
        if (SENSITIVE_FILENAMES.has(entry.name) || entry.name.startsWith(".env")) continue;
        const relPath = path.join(baseRelative, entry.name);
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          items.push({
            name: entry.name,
            path: relPath,
            type: "directory",
            children: buildTree(fullPath, relPath)
          });
        } else {
          items.push({
            name: entry.name,
            path: relPath,
            type: "file"
          });
        }
      }
      return items;
    }

    try {
      const tree = buildTree(process.cwd());
      res.json(tree);
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  app.get("/api/files/content", (req, res) => {
    const relativePath = req.query.path as string;
    if (!relativePath) return res.status(400).json({ error: "Path required" });
    const fullPath = resolveInsideWorkspace(relativePath);
    try {
      if (fullPath && fs.existsSync(fullPath) && fs.statSync(fullPath).isFile()) {
        const content = fs.readFileSync(fullPath, "utf-8");
        res.json({ path: relativePath, content });
      } else {
        res.status(404).json({ error: "File not found" });
      }
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  // Vite development middleware vs production static server
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  const httpServer = app.listen(PORT, HOST, () => {
    console.log(`[Water Leak Detection Platform] ${DASHBOARD_AUDIENCE} server running at http://${HOST}:${PORT}`);
  });

  // Raw TCP passthrough for the FastAPI WebSocket — the handshake and every
  // frame after it are just bytes, so proxying at the socket level needs no
  // WebSocket-aware library. Only the one path is forwarded; anything else
  // requesting an upgrade is rejected rather than silently misrouted.
  const FASTAPI_HOST = new URL(FASTAPI_BASE_URL).hostname;
  const FASTAPI_PORT = Number(new URL(FASTAPI_BASE_URL).port || 80);
  httpServer.on("upgrade", (req, clientSocket, head) => {
    if (req.url !== "/ws/telemetry") {
      clientSocket.destroy();
      return;
    }
    const upstream = net.connect(FASTAPI_PORT, FASTAPI_HOST, () => {
      const headerLines = [`${req.method} ${req.url} HTTP/1.1`];
      for (let i = 0; i < req.rawHeaders.length; i += 2) {
        headerLines.push(`${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}`);
      }
      upstream.write(headerLines.join("\r\n") + "\r\n\r\n");
      if (head && head.length) upstream.write(head);
      clientSocket.pipe(upstream);
      upstream.pipe(clientSocket);
    });
    upstream.on("error", () => clientSocket.destroy());
    clientSocket.on("error", () => upstream.destroy());
  });
}

startServer();
