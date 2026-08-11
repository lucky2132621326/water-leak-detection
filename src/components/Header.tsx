import React, { useState, useEffect } from "react";
import { Clock, Bell, ChevronDown } from "lucide-react";

interface HeaderProps {
  systemOnline?: boolean;
  unreadCount?: number;
  onOpenAlerts?: () => void;
  mode?: "live" | "mock";
  onToggleMode?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  systemOnline = true,
  unreadCount = 3,
  onOpenAlerts,
  mode = "mock",
  onToggleMode
}) => {
  const [timeStr, setTimeStr] = useState("");
  const [dateStr, setDateStr] = useState("");

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

  return (
    <header className="bg-white border-b border-slate-200/80 px-8 py-4 flex items-center justify-between sticky top-0 z-20 shadow-2xs">
      {/* Title & Online Status Badge */}
      <div className="flex items-center space-x-4">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
          Smart Water Leak Detection
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
        {onToggleMode && (
          <button
            onClick={onToggleMode}
            title="Switch telemetry source: generated mock data or the live ESP32 rig"
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold border transition flex items-center space-x-2 ${
              mode === "live"
                ? "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100"
                : "bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${mode === "live" ? "bg-rose-500 animate-pulse" : "bg-indigo-500"}`} />
            <span>{mode === "live" ? "LIVE SENSORS" : "MOCK DATA"}</span>
          </button>
        )}

        {/* Real-time Clock Display matching screenshot: "10:24:38 AM | May 24, 2025" */}
        <div className="flex items-center space-x-2 text-slate-600 bg-slate-50 border border-slate-200/60 rounded-xl px-3.5 py-1.5 text-xs font-medium">
          <Clock className="w-4 h-4 text-slate-500" />
          <span>
            {timeStr || "10:24:38 AM"} <span className="text-slate-400 mx-1">|</span> {dateStr || "May 24, 2025"}
          </span>
        </div>

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

        {/* User Profile Avatar */}
        <div className="flex items-center space-x-2.5 cursor-pointer pl-2 border-l border-slate-200">
          <div className="w-9 h-9 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-xs">
            AD
          </div>
          <span className="text-sm font-semibold text-slate-800">Admin</span>
          <ChevronDown className="w-4 h-4 text-slate-400" />
        </div>
      </div>
    </header>
  );
};
