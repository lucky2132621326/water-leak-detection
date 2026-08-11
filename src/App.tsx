import React, { useState, useEffect } from "react";
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
import type { AlertsSummary, SavingsSummary, LeakAlert, OperatingMode, RuntimeCapabilities } from "./types";
import type { SystemStatus } from "./components/SystemStatusRow";

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [health, setHealth] = useState<any>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<any[]>([]);
  const [mode, setMode] = useState<OperatingMode>("mock");
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [alertsSummary, setAlertsSummary] = useState<AlertsSummary | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<LeakAlert[]>([]);
  const [scenarioName, setScenarioName] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);

  // Fetch Health & Live Telemetry State
  const fetchState = () => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => {
        setHealth(data);
        if (data?.mode === "live" || data?.mode === "mock") setMode(data.mode);
      })
      .catch((err) => console.error(err));

    fetch("/api/telemetry")
      .then((res) => res.json())
      .then((data) => setLatestTelemetry(data))
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
      .then((data) => setRecentAlerts(Array.isArray(data) ? data : []))
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
    const interval = setInterval(fetchState, 1000); // 1Hz live telemetry polling
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const interval = setInterval(fetchHistory, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    fetchImpactState();
    const interval = setInterval(fetchImpactState, 5000);
    return () => clearInterval(interval);
  }, []);

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
          mode={mode}
          onToggleMode={handleToggleMode}
          readOnly={readOnly}
        />

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
