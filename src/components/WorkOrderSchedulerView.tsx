import React, { useState, useEffect } from "react";
import { Calendar, UserCheck, Clock, Plus, Send } from "lucide-react";

export const WorkOrderSchedulerView: React.FC = () => {
  const [workOrders, setWorkOrders] = useState<any[]>([]);
  const [newLocation, setNewLocation] = useState<string>("Branch_A (Side Loop)");
  const [newSeverity, setNewSeverity] = useState<string>("1.5");
  const [newPriority, setNewPriority] = useState<string>("HIGH");

  useEffect(() => {
    fetch("/api/work-orders")
      .then((res) => res.json())
      .then((data) => setWorkOrders(data))
      .catch((err) => console.error(err));
  }, []);

  const handleDispatchNew = (e: React.FormEvent) => {
    e.preventDefault();
    fetch("/api/work-orders/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: newLocation,
        severity: newSeverity,
        priority: newPriority,
        crew: "CREW_ALPHA"
      })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          setWorkOrders((prev) => [data.work_order, ...prev]);
        }
      })
      .catch((err) => console.error(err));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
          <Calendar className="w-6 h-6 text-emerald-600" />
          <span>Field Verification Work Orders</span>
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Converts indicative leak evidence into an auditable inspection brief; no operational control action is issued.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Dispatch New Work Order Form */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Plus className="w-4 h-4 text-emerald-600" />
            <span>Generate Work Order</span>
          </h3>

          <form onSubmit={handleDispatchNew} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-600 mb-1.5 font-bold">Pipe Node Location:</label>
              <input
                type="text"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-slate-900 focus:outline-none focus:border-emerald-600 focus:bg-white transition"
              />
            </div>

            <div>
              <label className="block text-slate-600 mb-1.5 font-bold">Leak Severity (L/min):</label>
              <input
                type="number"
                step="0.1"
                value={newSeverity}
                onChange={(e) => setNewSeverity(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-slate-900 focus:outline-none focus:border-emerald-600 focus:bg-white transition"
              />
            </div>

            <div>
              <label className="block text-slate-600 mb-1.5 font-bold">Priority Level:</label>
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-slate-900 focus:outline-none focus:border-emerald-600 focus:bg-white transition"
              >
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>

            <button
              type="submit"
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl text-xs transition flex items-center justify-center space-x-2 shadow-md shadow-emerald-600/20"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Optimize & Save Work Order</span>
            </button>
          </form>
        </div>

        {/* Right: Active Work Orders List */}
        <div className="lg:col-span-2 bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center justify-between">
            <span>Saved Work Orders</span>
            <span className="text-xs text-slate-500 font-semibold bg-slate-100 px-2.5 py-0.5 rounded-full">{workOrders.length} Active</span>
          </h3>

          <div className="space-y-3">
            {workOrders.map((wo) => (
              <div
                key={wo.id}
                className="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-4 text-xs flex flex-wrap items-center justify-between gap-3 shadow-2xs hover:bg-slate-50 transition"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-extrabold text-sm text-slate-900 font-mono">{wo.id}</span>
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                      wo.priority === "CRITICAL"
                        ? "bg-rose-100 text-rose-700 border border-rose-200"
                        : "bg-amber-100 text-amber-800 border border-amber-200"
                    }`}>
                      {wo.priority}
                    </span>
                  </div>
                  <div className="text-slate-600 font-medium">Node: <span className="text-slate-900 font-bold">{wo.location_node}</span></div>
                  <div className="text-slate-600 font-medium">Severity: <span className="text-rose-600 font-black">{wo.severity_lpm} L/min</span></div>
                </div>

                <div className="text-right space-y-1.5">
                  <div className="text-slate-900 font-bold flex items-center justify-end space-x-1.5">
                    <UserCheck className="w-4 h-4 text-emerald-600" />
                    <span>{wo.assigned_crew}</span>
                  </div>
                  <div className="text-slate-500 flex items-center justify-end space-x-1 text-[11px] font-medium">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    <span>Est: {wo.estimated_hrs} hrs</span>
                  </div>
                  <span className="inline-block bg-blue-100 text-blue-800 border border-blue-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                    {wo.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

