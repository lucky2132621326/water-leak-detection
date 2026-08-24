import React, { useState, useEffect, useRef } from "react";
import { Clock, Bell, ChevronDown, Settings, Moon, Sun } from "lucide-react";

interface HeaderProps {
  systemOnline?: boolean;
  unreadCount?: number;
  onOpenAlerts?: () => void;
  onOpenSettings?: () => void;
  darkMode?: boolean;
  onToggleTheme?: () => void;
  mode?: "live" | "mock";
  onToggleMode?: () => void;
  readOnly?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  systemOnline = true,
  unreadCount = 3,
  onOpenAlerts,
  onOpenSettings,
  darkMode = false,
  onToggleTheme,
  mode = "mock",
  onToggleMode,
  readOnly = false,
}) => {
  const [timeStr, setTimeStr] = useState("");
  const [dateStr, setDateStr] = useState("");
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(
        now.toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: true
        })
      );
      setDateStr(
        now.toLocaleDateString("en-US", {
          month: "short",
          day: "2-digit",
          year: "numeric"
        })
      );
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!profileMenuOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProfileMenuOpen(false);
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [profileMenuOpen]);

  return (
    <header className="bg-white border-b border-slate-200/80 px-8 py-4 flex items-center justify-between sticky top-0 z-20 shadow-2xs">
      {/* Title & Online Status Badge */}
      <div className="flex items-center space-x-4">
        <h1 className="brand-wordmark brand-wordmark--header whitespace-nowrap text-3xl">
          Jal Netra
        </h1>
        <div className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center space-x-1.5 ${
          systemOnline 
            ? "bg-emerald-50 text-emerald-700 border border-emerald-200/80" 
            : "bg-rose-50 text-rose-700 border border-rose-200/80"
        }`}>
          <span className={`w-2 h-2 rounded-full ${systemOnline ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`} />
          <span>{systemOnline ? "System Online" : "System Offline"}</span>
        </div>
      </div>

      {/* Right Header Controls: Live Clock, Notifications, Profile */}
      <div className="flex items-center space-x-6">
        {/* Mock/Live data-source toggle — identical detection pipeline either way */}
        {onToggleMode && !readOnly && (
          <button
            onClick={onToggleMode}
            title="Switch telemetry source: test bench (generated) data or the live ESP32 rig"
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold border transition flex items-center space-x-2 ${
              mode === "live"
                ? "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
                : "bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${mode === "live" ? "bg-rose-500 animate-pulse" : "bg-indigo-500"}`} />
            <span>{mode === "live" ? "LIVE SENSORS" : "TEST BENCH"}</span>
          </button>
        )}

        {/* Real-time Clock Display matching screenshot: "10:24:38 AM | May 24, 2025" */}
        <div className="flex items-center space-x-2 text-slate-600 bg-slate-50 border border-slate-200/60 rounded-xl px-3.5 py-1.5 text-xs font-medium">
          <Clock className="w-4 h-4 text-slate-500" />
          <span>
            {timeStr || "10:24:38 AM"} <span className="text-slate-400 mx-1">|</span> {dateStr || "May 24, 2025"}
          </span>
        </div>

        {/* Local display preference; persisted in the browser only. */}
        {onToggleTheme && (
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            className="rounded-xl border border-slate-200 bg-slate-50 p-2 text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
          >
            {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
        )}

        {/* Notification Bell */}
        <button 
          onClick={onOpenAlerts}
          className="relative p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition"
          title="Notifications"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-4 h-4 bg-rose-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-white shadow-xs">
              {unreadCount}
            </span>
          )}
        </button>

        {/* Operator profile and account-level navigation */}
        <div ref={profileMenuRef} className="relative pl-2 border-l border-slate-200">
          <button
            type="button"
            disabled={readOnly}
            aria-haspopup={readOnly ? undefined : "menu"}
            aria-expanded={readOnly ? undefined : profileMenuOpen}
            onClick={() => !readOnly && setProfileMenuOpen((open) => !open)}
            className={`flex items-center space-x-2.5 rounded-xl px-2 py-1.5 transition ${
              readOnly ? "cursor-default" : "hover:bg-slate-100"
            }`}
          >
            <div className="w-9 h-9 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-xs">
              {readOnly ? "JV" : "AD"}
            </div>
            <span className="text-sm font-semibold text-slate-800">{readOnly ? "Judge View" : "Operator"}</span>
            {!readOnly && (
              <ChevronDown
                className={`w-4 h-4 text-slate-400 transition-transform ${profileMenuOpen ? "rotate-180" : ""}`}
              />
            )}
          </button>

          {!readOnly && profileMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-[calc(100%+0.65rem)] w-56 overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-xl shadow-slate-900/10"
            >
              <div className="border-b border-slate-100 px-3 py-2.5">
                <p className="text-xs font-bold text-slate-900">System Operator</p>
                <p className="mt-0.5 text-[11px] text-slate-500">Hardware rig administration</p>
              </div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setProfileMenuOpen(false);
                  onOpenSettings?.();
                }}
                className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-700 transition hover:bg-blue-50 hover:text-blue-700"
              >
                <Settings className="h-4 w-4" />
                <span>Settings</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
