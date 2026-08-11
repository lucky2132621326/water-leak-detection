import React, { useState, useEffect } from "react";
import { GitBranch, MapPin, ShieldAlert, Crosshair, Wrench } from "lucide-react";

export const LocalizationView: React.FC = () => {
  const [locData, setLocData] = useState<any>(null);

  useEffect(() => {
    fetch("/api/localization/current")
      .then((res) => res.json())
      .then((data) => setLocData(data))
      .catch((err) => console.error(err));

    const interval = setInterval(() => {
      fetch("/api/localization/current")
        .then((res) => res.json())
        .then((data) => setLocData(data))
        .catch((err) => console.error(err));
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const isLocalized = locData?.localized ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
          <GitBranch className="w-6 h-6 text-purple-600" />
          <span>Phase 3: Hydraulic Pipe Branch Localization & Isolation Engine</span>
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Differential flow topology analysis and Branch A step-test isolation to narrow the leak to a pipe section and suggest which valve to close.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Pipe Network Diagram */}
        <div className="lg:col-span-2 bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs relative overflow-hidden">
          <h3 className="text-sm font-bold text-slate-900 mb-6 flex items-center space-x-2">
            <Crosshair className="w-4 h-4 text-purple-600" />
            <span>Rig Pipe Topology Diagram & Active Pinpoint</span>
          </h3>

          <div className="relative border border-slate-200 rounded-2xl p-8 bg-slate-50 min-h-[280px] flex items-center justify-center">
            {/* Pipe Lines */}
            <div className="w-full max-w-lg space-y-12 relative">
              {/* Main Trunk Line */}
              <div className="h-3.5 bg-blue-500/30 rounded-full w-full relative flex items-center border border-blue-200">
                {/* Flow Indicator */}
                <div className="absolute left-2 text-[10px] text-blue-700 font-bold bg-blue-100 px-2.5 py-0.5 rounded-md border border-blue-200">Inlet (Q_in)</div>
                <div className="absolute right-2 text-[10px] text-cyan-700 font-bold bg-cyan-100 px-2.5 py-0.5 rounded-md border border-cyan-200">Outlet (Q_out)</div>

                {/* Branch Junction */}
                <div className="absolute left-1/3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-slate-200 border-2 border-slate-400 flex items-center justify-center shadow-xs">
                  <div className="w-2.5 h-2.5 rounded-full bg-blue-600"></div>
                </div>

                {/* Branch A Line (Vertical Up) */}
                <div className="absolute left-1/3 bottom-1/2 w-2.5 h-20 bg-blue-400/40 border-l-2 border-blue-500">
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] bg-white text-slate-700 font-bold px-2 py-0.5 rounded-md border border-slate-200 shadow-2xs whitespace-nowrap">
                    Branch A (Side Loop)
                  </div>

                  {/* Active Leak Pinpoint Marker */}
                  {isLocalized && locData?.branch === "Branch_A" && (
                    <div className="absolute top-8 left-1/2 -translate-x-1/2 flex items-center space-x-2 animate-bounce">
                      <div className="bg-rose-600 text-white p-1.5 rounded-full shadow-lg shadow-rose-500/40">
                        <MapPin className="w-4 h-4" />
                      </div>
                      <div className="bg-rose-600 text-white text-[11px] font-bold px-2.5 py-1 rounded-lg shadow-md whitespace-nowrap">
                        LEAK DETECTED (confidence {((locData.confidence ?? 0) * 100).toFixed(0)}%)
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Localization Info */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900">Isolation & Localizer Summary</h3>

          {isLocalized ? (
            <div className="space-y-4">
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center space-x-2 text-rose-700 font-bold text-sm">
                  <ShieldAlert className="w-4.5 h-4.5" />
                  <span>Leak Pinpointed</span>
                </div>
                <div className="text-xs text-slate-700">
                  Location Node: <span className="font-bold text-slate-900">{locData.node}</span>
                </div>
                <div className="text-xs text-slate-700">
                  Localization Confidence: <span className="font-bold text-emerald-700">{((locData.confidence ?? 0) * 100).toFixed(0)}%</span>
                </div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 text-xs">
                <div className="font-bold text-slate-900 flex items-center space-x-2">
                  <Wrench className="w-4 h-4 text-blue-600" />
                  <span>Isolation Point (Diagnostic)</span>
                </div>
                <p className="text-slate-600 text-[11px] leading-relaxed">
                  Branch A can be isolated at <span className="text-slate-900 font-mono font-extrabold bg-slate-200/80 px-1.5 py-0.5 rounded">{locData.isolation_valve_suggested}</span> if a crew confirms the leak in the field. This is diagnostic guidance only — the system does not issue valve or pump control instructions.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-6 text-center text-slate-500 text-xs">
              <MapPin className="w-8 h-8 mx-auto mb-2 text-slate-400" />
              <span>No leak localized in hydraulic network. System operating nominal.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
