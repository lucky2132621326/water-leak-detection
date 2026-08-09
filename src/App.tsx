import React, { lazy, Suspense, useState, useEffect } from "react";
import { Sidebar, NavTab } from "./components/Sidebar";
import { Header } from "./components/Header";
import type { SystemHealth, TelemetryEnvelope, TelemetrySample } from "./types";

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

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latestTelemetry, setLatestTelemetry] = useState<TelemetryEnvelope | null>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<TelemetrySample[]>([]);
  const [mode, setMode] = useState<"live" | "replay">("replay");
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const fetchJson = async <T,>(url: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(url, init);
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json() as Promise<T>;
  };

  // Fetch the three dashboard contracts together so every card represents the
  // same observation window. A failed backend is surfaced in the UI.
  const fetchState = async () => {
    try {
      const [healthData, telemetryData, historyData] = await Promise.all([
        fetchJson<SystemHealth>("/api/health"),
        fetchJson<TelemetryEnvelope>("/api/telemetry"),
        fetchJson<TelemetrySample[]>("/api/telemetry/history"),
      ]);
      setHealth(healthData);
      setLatestTelemetry(telemetryData);
      setTelemetryHistory(Array.isArray(historyData) ? historyData : []);
      if (healthData.mode === "live" || healthData.mode === "replay") setMode(healthData.mode);
      setConnectionError(null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : "Detection backend unavailable");
      setHealth((current) => current ? { ...current, status: "error" } : null);
    }
  };

  useEffect(() => {
    void fetchState();
    const interval = setInterval(() => void fetchState(), 1000); // 1Hz live telemetry polling
    return () => clearInterval(interval);
  }, []);

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
        unreadAlertsCount={latestTelemetry?.evaluation?.is_alarm ? 1 : 0}
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
          unreadCount={latestTelemetry?.evaluation?.is_alarm ? 1 : 0}
          onOpenAlerts={() => setActiveTab("alerts")}
          mode={mode}
          onToggleMode={handleToggleMode}
        />

        {/* View Content Body */}
        <main className="flex-1 p-8 max-w-[1600px] w-full mx-auto">
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

          {activeTab === "replay" && <ReplaySystemView />}

          {activeTab === "analytics" && <AnalyticsView />}

          {activeTab === "calibration" && <CalibrationView />}

          {activeTab === "work-orders" && <WorkOrderSchedulerView />}

          {activeTab === "reports" && <ReportsView />}

          {activeTab === "alerts" && <AlertsView evaluation={latestTelemetry?.evaluation || null} />}

          {activeTab === "settings" && <SettingsView />}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
