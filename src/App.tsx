import React, { useState, useEffect, useRef } from "react";
import { Sidebar, NavTab } from "./components/Sidebar";
import { Header } from "./components/Header";
import { DashboardView } from "./components/DashboardView";
import { LiveMonitorView } from "./components/LiveMonitorView";
import { ExperimentsView } from "./components/ExperimentsView";
import { DetectionEngineView } from "./components/DetectionEngineView";
import { LocalizationView } from "./components/LocalizationView";
import { AnalyticsView } from "./components/AnalyticsView";
import { CalibrationView } from "./components/CalibrationView";
import { WorkOrderSchedulerView } from "./components/WorkOrderSchedulerView";
import { ScenarioLabView } from "./components/ScenarioLabView";
import { ReportsView } from "./components/ReportsView";
import { AlertsView } from "./components/AlertsView";
import { SettingsView } from "./components/SettingsView";
import { ImpactSimulatorView } from "./components/ImpactSimulatorView";
import { LeakHistoryView } from "./components/LeakHistoryView";
import { ViewErrorBoundary } from "./components/ViewErrorBoundary";
import { LeakAlertToast } from "./components/LeakAlertToast";
import type { AlertsSummary, SavingsSummary, LeakAlert, OperatingMode, RuntimeCapabilities } from "./types";
import type { SystemStatus } from "./components/SystemStatusRow";

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [darkMode, setDarkMode] = useState(() => document.documentElement.classList.contains("dark"));
  const [health, setHealth] = useState<any>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<any[]>([]);
  const [mode, setMode] = useState<OperatingMode>("mock");
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [alertsSummary, setAlertsSummary] = useState<AlertsSummary | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<LeakAlert[]>([]);
  const [alertToast, setAlertToast] = useState<LeakAlert | null>(null);
  const alertFeedInitialized = useRef(false);
  const seenAlertKeys = useRef<Set<string>>(new Set());
  const telemetryPollInFlight = useRef(false);
  const [scenarioName, setScenarioName] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    window.localStorage.setItem("water-leak-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  // Health is cheap and changes rarely; still polled. Telemetry itself comes
  // over the WebSocket below instead — see fetchState's docstring-equivalent
  // comment on the effect that opens it.
  const fetchState = () => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => {
        setHealth(data);
        if (data?.mode === "live" || data?.mode === "mock") setMode(data.mode);
      })
      .catch((err) => console.error(err));
  };

  const fetchHistory = () => {
    fetch("/api/telemetry/history")
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setTelemetryHistory(data);
        }
      })
      .catch((err) => console.error(err));
  };

  const fetchTelemetry = () => {
    // Never stack requests if the backend is momentarily slow. The next
    // one-second tick retries while the last good sample remains visible.
    if (telemetryPollInFlight.current) return;
    telemetryPollInFlight.current = true;
    fetch("/api/telemetry", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`telemetry request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setLatestTelemetry(data);
        if (data?.mode === "live" || data?.mode === "mock") setMode(data.mode);
      })
      .catch((err) => console.error(err))
      .finally(() => { telemetryPollInFlight.current = false; });
  };

  // Savings and the alert badge change on operator action, not per sample, so
  // they poll far slower than telemetry.
  const fetchImpactState = () => {
    fetch("/api/savings")
      .then((res) => res.json())
      .then(setSavings)
      .catch(() => undefined);

    fetch("/api/alerts/summary")
      .then((res) => res.json())
      .then(setAlertsSummary)
      .catch(() => undefined);

    fetch("/api/status")
      .then((res) => res.json())
      .then(setSystemStatus)
      // Leave the previous status rather than clearing it — the status row
      // renders "unknown" only when it has genuinely never had data.
      .catch(() => undefined);

    fetch("/api/alerts?limit=5")
      .then((res) => res.json())
      .then((data) => {
        const alerts = Array.isArray(data) ? data as LeakAlert[] : [];
        setRecentAlerts(alerts);

        const keyOf = (alert: LeakAlert) =>
          `${alert.source}:${alert.alert_id}:${alert.start_ts}`;
        if (alertFeedInitialized.current) {
          const recentCutoff = Date.now() / 1000 - 15;
          const newlyCreated = alerts.find((alert) =>
            !seenAlertKeys.current.has(keyOf(alert)) &&
            Number(alert.created_at ?? 0) >= recentCutoff
          );
          if (newlyCreated) setAlertToast(newlyCreated);
        } else {
          alertFeedInitialized.current = true;
        }
        alerts.forEach((alert) => seenAlertKeys.current.add(keyOf(alert)));
      })
      .catch(() => undefined);

    fetch("/api/mode")
      .then((res) => res.json())
      .then((data) => setScenarioName(data?.source?.scenario?.name ?? null))
      .catch(() => undefined);
  };

  useEffect(() => {
    fetch("/api/runtime-capabilities")
      .then((res) => res.json())
      .then(setCapabilities)
      .catch(() => setCapabilities({ audience: "operator", read_only: false, mutations_allowed: true }));
    fetchState();
    fetchHistory();
    // Health/connection-status widgets change far less often than telemetry
    // itself (which now arrives over the WebSocket below), so this poll can
    // stay slow without the dashboard feeling stale.
    const interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, [mode]);

  useEffect(() => {
    const interval = setInterval(fetchHistory, 5000);
    return () => clearInterval(interval);
  }, []);

  // Guaranteed one-second polling path. WebSocket push remains as a low-latency
  // enhancement, while this job makes updates reliable through proxies or
  // browsers where the socket is unavailable.
  useEffect(() => {
    fetchTelemetry();
    const interval = window.setInterval(fetchTelemetry, 1000);
    return () => window.clearInterval(interval);
  }, []);

  // WebSocket push complements the required polling job: the backend pushes a
  // new payload the instant a sample actually changes (see /ws/telemetry),
  // so values update the moment water starts moving through the pipe rather
  // than waiting for the next fixed-interval fetch. Reconnects on drop with a
  // short fixed backoff — this is a dashboard, not a control channel, so a
  // simple retry is enough rather than exponential backoff/jitter.
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry`);
      socket.onmessage = (event) => {
        try {
          setLatestTelemetry(JSON.parse(event.data));
        } catch {
          // Malformed frame — drop it rather than crash the socket handler.
        }
      };
      socket.onclose = () => {
        if (!stopped) reconnectTimer = setTimeout(connect, 2000);
      };
      socket.onerror = () => socket?.close();
    };
    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    fetchImpactState();
    const interval = setInterval(fetchImpactState, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!alertToast) return;
    const timeout = window.setTimeout(() => setAlertToast(null), 15000);
    return () => window.clearTimeout(timeout);
  }, [alertToast]);

    // Which mock scenario is streaming — shown on the Dashboard instead of a
    // stale stored run id.
  const activeAlertCount = alertsSummary?.counts.active ?? 0;
  const readOnly = capabilities?.read_only ?? true;

  const handleToggleLeak = (action: "OPEN" | "CLOSE", size?: number) => {
    fetch("/api/leak/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, size })
    })
      .then((res) => res.json())
      .then(() => fetchState())
      .catch((err) => console.error(err));
  };

  const handleTogglePump = (state: boolean) => {
    fetch("/api/leak/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pump_state: state })
    })
      .then((res) => res.json())
      .then(() => fetchState())
      .catch((err) => console.error(err));
  };

  const handleToggleMode = () => {
    // Two modes only. Switching resets all detector state on the backend, so
    // a scenario never inherits the rig's learned baseline (or the reverse).
    const nextMode: OperatingMode = mode === "live" ? "mock" : "live";
    fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: nextMode, scenario_id: nextMode === "mock" ? "sudden_leak" : undefined })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data?.success) setMode(nextMode);
      })
      .catch((err) => console.error(err));
  };

  const handleToggleAirBubbles = (state: boolean) => {
    fetch("/api/leak/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ air_bubbles: state })
    })
      .then((res) => res.json())
      .then(() => fetchState())
      .catch((err) => console.error(err));
  };

  return (
    <div className="flex min-h-screen bg-[#F8FAFC] text-slate-800 font-sans selection:bg-blue-500/20 selection:text-blue-700">
      {/* 1. Left Sidebar Navigation (Fixed dark navy sidebar matching screenshot) */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        unreadAlertsCount={activeAlertCount}
        readOnly={readOnly}
      />

      {/* 2. Main Right Container */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <Header
          systemOnline={health?.status === "ok"}
          unreadCount={activeAlertCount}
          onOpenAlerts={() => setActiveTab("alerts")}
          onOpenSettings={() => setActiveTab("settings")}
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((enabled) => !enabled)}
          mode={mode}
          onToggleMode={handleToggleMode}
          readOnly={readOnly}
        />

        {alertToast && (
          <LeakAlertToast
            alert={alertToast}
            onDismiss={() => setAlertToast(null)}
            onOpen={() => {
              setAlertToast(null);
              setActiveTab("alerts");
            }}
          />
        )}

        {/* View Content Body */}
        <main className="flex-1 p-8 max-w-[1600px] w-full mx-auto">
          {readOnly && capabilities?.audience === "judge" && (
            <div className="mb-5 rounded-2xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-xs font-bold tracking-wide text-cyan-900">
              LIVE JUDGE VIEW · READ-ONLY — telemetry and evidence are live; operator controls remain on the rig laptop.
            </div>
          )}
          {/* Keyed on the active tab so navigating away from a failed view clears
              the error rather than stranding the operator on it. */}
          <ViewErrorBoundary resetKey={activeTab}>
          {activeTab === "dashboard" && (
            <DashboardView
              latestTelemetry={latestTelemetry}
              telemetryHistory={telemetryHistory}
              onNavigateTab={setActiveTab}
              onToggleLeak={handleToggleLeak}
              onTogglePump={handleTogglePump}
              impact={latestTelemetry?.impact}
              savings={savings}
              onAnalyzeImpact={readOnly ? undefined : () => setActiveTab("impact-simulator")}
              systemStatus={systemStatus}
              evaluation={latestTelemetry?.evaluation}
              alerts={recentAlerts}
              scenarioName={scenarioName}
              readOnly={readOnly}
            />
          )}

          {activeTab === "live-monitoring" && (
            <LiveMonitorView
              telemetryHistory={telemetryHistory}
              latestTelemetry={latestTelemetry}
              onToggleLeak={handleToggleLeak}
              onTogglePump={handleTogglePump}
              onToggleAirBubbles={handleToggleAirBubbles}
              mode={mode}
              readOnly={readOnly}
            />
          )}

          {activeTab === "experiment-control" && <ExperimentsView />}

          {activeTab === "leak-detection" && (
            <DetectionEngineView evaluation={latestTelemetry?.evaluation} />
          )}

          {activeTab === "localization" && <LocalizationView />}

          {activeTab === "impact-simulator" && <ImpactSimulatorView />}

          {activeTab === "scenarios" && <ScenarioLabView onModeChange={fetchState} />}

          {activeTab === "analytics" && <AnalyticsView />}

          {activeTab === "calibration" && <CalibrationView />}

          {activeTab === "work-orders" && <WorkOrderSchedulerView />}

          {activeTab === "reports" && <ReportsView />}

          {activeTab === "alerts" && <AlertsView readOnly={readOnly} />}

          {activeTab === "leak-history" && <LeakHistoryView />}

          {activeTab === "settings" && <SettingsView />}
          </ViewErrorBoundary>
        </main>
      </div>
    </div>
  );
}
