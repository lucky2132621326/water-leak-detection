import React from "react";
import {
  LayoutDashboard,
  Radio,
  FlaskConical,
  Droplets,
  MapPin,
  RotateCcw,
  BarChart3,
  Sliders,
  ClipboardList,
  FileText,
  Bell,
  Droplet,
  Calculator,
  History
} from "lucide-react";

export type NavTab =
  | "dashboard"
  | "live-monitoring"
  | "experiment-control"
  | "leak-detection"
  | "localization"
  | "impact-simulator"
  | "scenarios"
  | "analytics"
  | "calibration"
  | "work-orders"
  | "reports"
  | "alerts"
  | "leak-history"
  | "settings";

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  unreadAlertsCount?: number;
  readOnly?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  unreadAlertsCount = 0,
  readOnly = false,
}) => {
  const allNavItems: { id: NavTab; label: string; icon: React.ReactNode; badge?: number; operatorOnly?: boolean }[] = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-5 h-5" /> },
    { id: "live-monitoring", label: "Live Monitoring", icon: <Radio className="w-5 h-5" /> },
    { id: "experiment-control", label: "Experiment Control", icon: <FlaskConical className="w-5 h-5" />, operatorOnly: true },
    { id: "leak-detection", label: "Leak Detection", icon: <Droplets className="w-5 h-5" /> },
    { id: "localization", label: "Localization", icon: <MapPin className="w-5 h-5" /> },
    { id: "impact-simulator", label: "Impact Simulator", icon: <Calculator className="w-5 h-5" />, operatorOnly: true },
    { id: "scenarios", label: "Mock Scenarios", icon: <RotateCcw className="w-5 h-5" />, operatorOnly: true },
    { id: "analytics", label: "Analytics", icon: <BarChart3 className="w-5 h-5" />, operatorOnly: true },
    { id: "calibration", label: "Calibration", icon: <Sliders className="w-5 h-5" />, operatorOnly: true },
    { id: "work-orders", label: "Work Orders", icon: <ClipboardList className="w-5 h-5" />, operatorOnly: true },
    { id: "reports", label: "Reports", icon: <FileText className="w-5 h-5" /> },
    { id: "alerts", label: "Alert Center", icon: <Bell className="w-5 h-5" />, badge: unreadAlertsCount },
    { id: "leak-history", label: "Leak History", icon: <History className="w-5 h-5" /> }
  ];
  const navItems = allNavItems.filter((item) => !readOnly || !item.operatorOnly);

  return (
    <aside className="w-64 bg-[#0B132B] text-slate-300 flex flex-col min-h-screen sticky top-0 z-30 border-r border-slate-800/80 shrink-0 select-none">
      {/* Brand Logo Header */}
      <div className="p-6 flex items-center space-x-3 border-b border-slate-800/60">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-blue-500/25 shrink-0">
          <Droplet className="w-6 h-6 fill-white text-white" />
        </div>
        <div className="overflow-hidden">
          <h1 className="brand-wordmark text-lg text-white leading-tight">
            Jal Netra
          </h1>
          <p className="text-[11px] text-blue-400 font-medium">Analytics & Hardware Rig</p>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 group ${
                isActive
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/30 font-semibold"
                  : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"
              }`}
            >
              <div className="flex items-center space-x-3">
                <span className={isActive ? "text-white" : "text-slate-400 group-hover:text-slate-200"}>
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </div>
              {item.badge ? (
                <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                  isActive ? "bg-white/20 text-white" : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                }`}>
                  {item.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>

      {/* Decorative Wave Footer */}
      <div className="mt-auto pt-4 pb-5 px-5 relative overflow-hidden">
        <div className="absolute inset-0 opacity-20 pointer-events-none">
          <svg className="w-full h-full text-blue-500" viewBox="0 0 100 100" preserveAspectRatio="none">
            <path d="M0,70 Q30,50 60,75 T100,60 L100,100 L0,100 Z" fill="currentColor" />
            <path d="M0,80 Q40,65 70,85 T100,75 L100,100 L0,100 Z" fill="currentColor" opacity="0.6" />
          </svg>
        </div>
        <div className="relative z-10 text-[11px] text-slate-500 leading-relaxed">
          <p>© 2026 Jal Netra</p>
          <p className="text-slate-600">All rights reserved.</p>
        </div>
      </div>
    </aside>
  );
};
