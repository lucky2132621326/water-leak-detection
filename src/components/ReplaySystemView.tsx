import React, { useState, useEffect } from "react";
import { RotateCcw, BarChart3 } from "lucide-react";

export const ReplaySystemView: React.FC = () => {
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>("RUN_001");
  const [evalResult, setEvalResult] = useState<any>(null);

  useEffect(() => {
    fetch("/api/replay/runs")
      .then((res) => res.json())
      .then((data) => {
        setRuns(data);
        if (Array.isArray(data) && data.length > 0 && !data.some((r: any) => r.run_id === selectedRun)) {
          setSelectedRun(data[0].run_id);
        }
      })
      .catch((err) => console.error(err));
  }, []);

  useEffect(() => {
    if (!selectedRun) return;
    // The score is computed by the production DetectionPipeline against the
    // selected run's stored telemetry and ground-truth leak events.
    fetch("/api/replay/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: selectedRun })
    })
      .then((res) => res.json())
      .then((data) => setEvalResult(data))
      .catch((err) => console.error(err));
  }, [selectedRun]);

  const activeRun = runs.find((r) => r.run_id === selectedRun) || runs[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
          <RotateCcw className="w-6 h-6 text-indigo-600" />
          <span>Historical Replay & Benchmark</span>
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Re-run stored sensor frames through the production detection pipeline and score them against physical or synthetic ground truth.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Dataset Selector */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900">Select Historical Test Run</h3>
          <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
            {runs.map((r) => (
              <button
                key={r.run_id}
                onClick={() => setSelectedRun(r.run_id)}
                className={`w-full text-left p-3.5 rounded-xl border transition text-xs ${
                  selectedRun === r.run_id
                    ? "bg-indigo-50 border-indigo-300 text-indigo-900 font-bold shadow-2xs"
                    : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-extrabold text-sm text-slate-900">{r.run_id}</span>
                  <span className="text-[10px] bg-slate-200/80 font-bold px-2 py-0.5 rounded text-slate-800 font-mono">{r.leak_size_lpm ?? "?"} L/min</span>
                </div>
                <div className="flex justify-between text-slate-500 mt-1.5 text-[11px] font-medium">
                  <span>Location: {r.location ?? "unknown"}</span>
                  <span>{r.date ?? ""}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Active Run Details */}
          {activeRun && (
            <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4 text-xs space-y-2 text-slate-700">
              <div className="text-slate-500 font-bold border-b border-slate-200 pb-1.5 mb-1.5">Run Metadata</div>
              <div className="flex justify-between"><span>Operator:</span> <span className="font-mono font-bold text-slate-900">{activeRun.operator ?? "-"}</span></div>
              <div className="flex justify-between"><span>Leak Size:</span> <span className="font-mono text-rose-600 font-extrabold">{activeRun.leak_size_lpm ?? "?"} L/min</span></div>
              <div className="flex justify-between"><span>Samples Evaluated:</span> <span className="font-mono text-emerald-600 font-bold">{evalResult?.samples ?? "-"}</span></div>
            </div>
          )}
        </div>

        {/* Right: Parameter Tweak & Evaluation Metrics */}
        <div className="lg:col-span-2 space-y-6">
          {/* Benchmark Evaluation Metrics */}
          {evalResult?.metrics && (
            <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-5">
              <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
                <BarChart3 className="w-4 h-4 text-emerald-600" />
                <span>Benchmark Evaluation Metrics (Replay Results)</span>
              </h3>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
                  <div className="text-[11px] font-bold text-slate-500">Precision</div>
                  <div className="text-2xl font-black text-emerald-600 mt-1">{((evalResult.metrics.precision) * 100).toFixed(1)}%</div>
                  <div className="text-[10px] font-medium text-slate-400 mt-0.5">TP / (TP + FP)</div>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
                  <div className="text-[11px] font-bold text-slate-500">Recall (Sensitivity)</div>
                  <div className="text-2xl font-black text-blue-600 mt-1">{((evalResult.metrics.recall) * 100).toFixed(1)}%</div>
                  <div className="text-[10px] font-medium text-slate-400 mt-0.5">TP / (TP + FN)</div>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
                  <div className="text-[11px] font-bold text-slate-500">F1-Score</div>
                  <div className="text-2xl font-black text-indigo-600 mt-1">{((evalResult.metrics.f1_score) * 100).toFixed(1)}%</div>
                  <div className="text-[10px] font-medium text-slate-400 mt-0.5">Harmonic Mean</div>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
                  <div className="text-[11px] font-bold text-slate-500">Detection Latency</div>
                  <div className="text-2xl font-black text-amber-600 mt-1">{evalResult.metrics.avg_latency_sec != null ? `${evalResult.metrics.avg_latency_sec}s` : "N/A"}</div>
                  <div className="text-[10px] font-medium text-slate-400 mt-0.5">Time to Alarm</div>
                </div>
              </div>

              {/* Confusion Matrix Breakdown */}
              <div className="bg-slate-50 border border-slate-200 p-3.5 rounded-xl text-xs flex justify-around text-slate-700 font-medium">
                <div><span className="text-slate-500">True Positives (TP):</span> <span className="font-extrabold text-emerald-600 ml-1">{evalResult.metrics.true_positives}</span></div>
                <div><span className="text-slate-500">False Positives (FP):</span> <span className="font-extrabold text-rose-600 ml-1">{evalResult.metrics.false_positives}</span></div>
                <div><span className="text-slate-500">False Negatives (FN):</span> <span className="font-extrabold text-amber-600 ml-1">{evalResult.metrics.false_negatives}</span></div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
