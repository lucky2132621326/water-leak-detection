import express from "express";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || "http://localhost:8000";

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // Thin proxy to the Python FastAPI service (backend/api_server.py), which
  // owns real detection state for whichever operating mode is active (Mock Data
  // or Live Sensor — same pipeline either way). Node neither generates nor
  // evaluates telemetry itself.
  async function proxyToFastApi(req: express.Request, res: express.Response, fastApiPath: string) {
    try {
      const query = req.originalUrl.includes("?") ? req.originalUrl.slice(req.originalUrl.indexOf("?")) : "";
      const url = `${FASTAPI_BASE_URL}${fastApiPath}${query}`;
      const init: RequestInit = { method: req.method, headers: { "Content-Type": "application/json" } };
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
    } catch (e) {
      res.status(502).json({ status: "error", result: `Detection backend unreachable: ${String(e)}` });
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
    const filename = req.params.filename;
    const filePath = path.join(process.cwd(), "docs", filename);
    try {
      if (fs.existsSync(filePath)) {
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
    const filename = req.params.filename;
    const { content } = req.body;
    const filePath = path.join(process.cwd(), "docs", filename);
    try {
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
    const fullPath = path.join(process.cwd(), relativePath);
    try {
      if (fs.existsSync(fullPath)) {
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

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[Water Leak Detection Platform] Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer();
