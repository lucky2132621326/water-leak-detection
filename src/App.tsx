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
import { ReplaySystemView } from "./components/ReplaySystemView";
import { ReportsView } from "./components/ReportsView";
import { AlertsView } from "./components/AlertsView";
import { SettingsView } from "./components/SettingsView";
import { ImpactSimulatorView } from "./components/ImpactSimulatorView";
import { LeakHistoryView } from "./components/LeakHistoryView";
import { ViewErrorBoundary } from "./components/ViewErrorBoundary";
import type { AlertsSummary, SavingsSummary } from "./types";

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [health, setHealth] = useState<any>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<any[]>([]);
  const [mode, setMode] = useState<"live" | "replay">("replay");
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [alertsSummary, setAlertsSummary] = useState<AlertsSummary | null>(null);

  // Fetch Health & Live Telemetry State
  const fetchState = () => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => {
        setHealth(data);
        if (data?.mode === "live" || data?.mode === "replay") setMode(data.mode);
      })
      .catch((err) => console.error(err));

    fetch("/api/telemetry")
      .then((res) => res.json())
      .then((data) => setLatestTelemetry(data))
      .catch((err) => console.error(err));

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
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 1000); // 1Hz live telemetry polling
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    fetchImpactState();
    const interval = setInterval(fetchImpactState, 5000);
    return () => clearInterval(interval);
  }, []);

  const activeAlertCount = alertsSummary?.counts.active ?? 0;

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
    const nextMode = mode === "live" ? "replay" : "live";
    fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: nextMode, run_id: nextMode === "replay" ? "RUN_001" : undefined })
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
      />

      {/* 2. Main Right Container */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <Header
          systemOnline={health?.status === "ok" || true}
          unreadCount={activeAlertCount}
          onOpenAlerts={() => setActiveTab("alerts")}
          mode={mode}
          onToggleMode={handleToggleMode}
        />

        {/* View Content Body */}
        <main className="flex-1 p-8 max-w-[1600px] w-full mx-auto">
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
              onAnalyzeImpact={() => setActiveTab("impact-simulator")}
            />
          )}

          {activeTab === "live-monitoring" && (
            <LiveMonitorView
              telemetryHistory={telemetryHistory}
              latestTelemetry={latestTelemetry}
              onToggleLeak={handleToggleLeak}
              onTogglePump={handleTogglePump}
              onToggleAirBubbles={handleToggleAirBubbles}
            />
          )}

          {activeTab === "experiment-control" && <ExperimentsView />}

          {activeTab === "leak-detection" && (
            <DetectionEngineView evaluation={latestTelemetry?.evaluation} />
          )}

          {activeTab === "localization" && <LocalizationView />}

          {activeTab === "impact-simulator" && <ImpactSimulatorView />}

          {activeTab === "replay" && <ReplaySystemView />}

          {activeTab === "analytics" && <AnalyticsView />}

          {activeTab === "calibration" && <CalibrationView />}

          {activeTab === "work-orders" && <WorkOrderSchedulerView />}

          {activeTab === "reports" && <ReportsView />}

          {activeTab === "alerts" && <AlertsView />}

          {activeTab === "leak-history" && <LeakHistoryView />}

          {activeTab === "settings" && <SettingsView />}
          </ViewErrorBoundary>
        </main>
      </div>
    </div>
  );
}
