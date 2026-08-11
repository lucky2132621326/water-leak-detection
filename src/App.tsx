import React, { lazy, Suspense, useState, useEffect } from "react";
import { Sidebar, NavTab } from "./components/Sidebar";
import { Header } from "./components/Header";
import { ViewErrorBoundary } from "./components/ViewErrorBoundary";
import type { SystemHealth, TelemetryEnvelope, TelemetrySample, AlertsSummary, SavingsSummary, RuntimeCapabilities } from "./types";

const DashboardView = lazy(() => import("./components/DashboardView").then((module) => ({ default: module.DashboardView })));
const LiveMonitorView = lazy(() => import("./components/LiveMonitorView").then((module) => ({ default: module.LiveMonitorView })));
const ExperimentsView = lazy(() => import("./components/ExperimentsView").then((module) => ({ default: module.ExperimentsView })));
const DetectionEngineView = lazy(() => import("./components/DetectionEngineView").then((module) => ({ default: module.DetectionEngineView })));
const LocalizationView = lazy(() => import("./components/LocalizationView").then((module) => ({ default: module.LocalizationView })));
const AnalyticsView = lazy(() => import("./components/AnalyticsView").then((module) => ({ default: module.AnalyticsView })));
const CalibrationView = lazy(() => import("./components/CalibrationView").then((module) => ({ default: module.CalibrationView })));
const WorkOrderSchedulerView = lazy(() => import("./components/WorkOrderSchedulerView").then((module) => ({ default: module.WorkOrderSchedulerView })));
const ReplaySystemView = lazy(() => import("./components/ReplaySystemView").then((module) => ({ default: module.ReplaySystemView })));
const ReportsView = lazy(() => import("./components/ReportsView").then((module) => ({ default: module.ReportsView })));
const AlertsView = lazy(() => import("./components/AlertsView").then((module) => ({ default: module.AlertsView })));
const SettingsView = lazy(() => import("./components/SettingsView").then((module) => ({ default: module.SettingsView })));
const ImpactSimulatorView = lazy(() => import("./components/ImpactSimulatorView").then((module) => ({ default: module.ImpactSimulatorView })));
const LeakHistoryView = lazy(() => import("./components/LeakHistoryView").then((module) => ({ default: module.LeakHistoryView })));

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<TelemetryEnvelope | null>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<TelemetrySample[]>([]);
  const [mode, setMode] = useState<"live" | "replay">("replay");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [alertsSummary, setAlertsSummary] = useState<AlertsSummary | null>(null);
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);

  const fetchJson = async <T,>(url: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(url, init);
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json() as Promise<T>;
  };

  // Health/latest stay at 1Hz; history is refreshed separately at 5s so a
  // group of judges does not multiply expensive history reads every second.
  const fetchLiveState = async () => {
    try {
      const [healthData, telemetryData] = await Promise.all([
        fetchJson<SystemHealth>("/api/health"),
        fetchJson<TelemetryEnvelope>("/api/telemetry"),
      ]);
      setHealth(healthData);
      setLatestTelemetry(telemetryData);
      if (healthData.mode === "live" || healthData.mode === "replay") setMode(healthData.mode);
      setConnectionError(null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : "Detection backend unavailable");
      setHealth((current) => current ? { ...current, status: "error" } : null);
    }
  };

  const fetchHistory = () => {
    fetchJson<TelemetrySample[]>("/api/telemetry/history")
      .then((data) => setTelemetryHistory(Array.isArray(data) ? data : []))
      .catch(() => undefined);
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
    fetchJson<RuntimeCapabilities>("/api/runtime-capabilities")
      .then(setCapabilities)
      .catch(() => setCapabilities({ audience: "operator", read_only: false, mutations_allowed: true }));
    void fetchLiveState();
    fetchHistory();
    const interval = setInterval(() => void fetchLiveState(), 1000);
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

  // Leak injection is intentionally not wired here — the hardware spec
  // (docs/HARDWARE_INTEGRATION_SPEC.md §8) replaced software leak injection
  // with physical ground-truth logging; there is no /api/leak/toggle route
  // to call anymore.
  const activeAlertCount = alertsSummary?.counts.active ?? 0;
  const readOnly = capabilities?.read_only ?? true;

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
          systemLabel={
            mode === "live"
              ? (health?.device?.online ? "Rig online" : "Waiting for rig")
              : (health?.data_source_ready ? "Replay ready" : "Replay unavailable")
          }
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
          {(mode === "replay" || health?.simulation_mode) && (
            <div className="mb-5 rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-xs font-bold tracking-wide text-indigo-800">
              SIMULATION MODE — synthetic telemetry for validation; physical ESP32 integration is not the active data source.
            </div>
          )}
          {connectionError && (
            <div className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">
              Detection service connection lost. Showing the last verified sample. ({connectionError})
            </div>
          )}
          {/* Keyed on the active tab so navigating away from a failed view clears
              the error rather than stranding the operator on it. */}
          <ViewErrorBoundary resetKey={activeTab}>
          <Suspense fallback={(
            <div className="h-64 rounded-2xl border border-slate-200 bg-white flex items-center justify-center text-sm font-semibold text-slate-500">
              Loading intelligence module…
            </div>
          )}>
          {activeTab === "dashboard" && (
            <DashboardView
              health={health}
              mode={mode}
              latestTelemetry={latestTelemetry}
              telemetryHistory={telemetryHistory}
              onNavigateTab={setActiveTab}
              impact={latestTelemetry?.impact}
              savings={savings}
              onAnalyzeImpact={readOnly ? undefined : () => setActiveTab("impact-simulator")}
              readOnly={readOnly}
            />
          )}

          {activeTab === "live-monitoring" && (
            <LiveMonitorView
              telemetryHistory={telemetryHistory}
              latestTelemetry={latestTelemetry}
              mode={mode}
              health={health}
            />
          )}

          {activeTab === "experiment-control" && <ExperimentsView mode={mode} health={health} />}

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

          {activeTab === "alerts" && <AlertsView readOnly={readOnly} />}

          {activeTab === "leak-history" && <LeakHistoryView />}

          {activeTab === "settings" && <SettingsView />}
          </Suspense>
          </ViewErrorBoundary>
        </main>
      </div>
    </div>
  );
}
