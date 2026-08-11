import React, { useEffect, useState } from "react";
import { Settings, Save, CheckCircle2, Server, Database, ShieldAlert, Terminal } from "lucide-react";

export const SettingsView: React.FC = () => {
  const [mqttHost, setMqttHost] = useState("localhost");
  const [mqttPort, setMqttPort] = useState(1883);
  const [mongoUri, setMongoUri] = useState("mongodb://localhost:27017");
  const [sigmaMultiplier, setSigmaMultiplier] = useState(3.0);
  const [persistenceSec, setPersistenceSec] = useState(5);
  const [configNote, setConfigNote] = useState<string | null>(null);
  const [dbSource, setDbSource] = useState<string | null>(null);
  const [testOutput, setTestOutput] = useState<string | null>(null);
  const [testPassed, setTestPassed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  // Reports the configuration actually in force — including which source won,
  // since settings.yaml and thresholds.yaml previously disagreed and only one
  // of them is read by the detectors.
  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => {
        if (d?.mqtt) { setMqttHost(d.mqtt.host); setMqttPort(d.mqtt.port); }
        if (d?.database) { setMongoUri(d.database.uri); setDbSource(d.database.source); }
        if (d?.detector) {
          setSigmaMultiplier(d.detector.sigma_multiplier);
          setPersistenceSec(d.detector.persistence_samples);
        }
        if (d?.note) setConfigNote(d.note);
      })
      .catch(() => setConfigNote("Could not read runtime configuration."));
  }, []);

  // Runs the real backend self-test rather than printing a fixed string.
  const handleSelfTest = () => {
    setBusy(true);
    setTestOutput(null);
    setTestPassed(null);
    fetch("/api/self-test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then((r) => r.json())
      .then((d) => { setTestOutput(d.output || "(no output)"); setTestPassed(Boolean(d.passed)); })
      .catch(() => { setTestOutput("Self-test could not run — backend unreachable."); setTestPassed(false); })
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <Settings className="w-6 h-6 text-blue-600" />
              <span>System Settings & Config Manager</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              The MQTT, database and detector settings actually in force at runtime, plus a full
              backend self-diagnostic.
            </p>
          </div>

          <button
            onClick={handleSelfTest}
            disabled={busy}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold rounded-xl shadow-md shadow-blue-600/20 flex items-center space-x-2 transition"
          >
            <Terminal className="w-4 h-4" />
            <span>{busy ? "Running…" : "Run Self-Test"}</span>
          </button>
        </div>

        {testOutput && (
          <div className="mb-6">
            <div className="flex items-center space-x-2 mb-2">
              {testPassed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-rose-600" />
              )}
              <span className={`text-xs font-bold ${testPassed ? "text-emerald-700" : "text-rose-700"}`}>
                {testPassed ? "All self-test modules passed" : "Self-test reported a problem"}
              </span>
            </div>
            <div className="bg-slate-900 text-slate-200 font-mono text-[11px] rounded-xl p-4 border border-slate-800 whitespace-pre-wrap shadow-inner max-h-72 overflow-y-auto">
              {testOutput}
            </div>
          </div>
        )}

        {configNote && (
          <p className="mb-5 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 leading-relaxed">
            <strong>Read-only:</strong> {configNote}
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* MQTT Configuration */}
          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2">
              <Server className="w-4 h-4 text-blue-600" />
              <span>MQTT Broker Connection</span>
            </h3>

            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Broker Host</label>
              <input
                type="text"
                value={mqttHost}
                onChange={(e) => setMqttHost(e.target.value)}
                className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Port</label>
              <input
                type="number"
                value={mqttPort}
                onChange={(e) => setMqttPort(parseInt(e.target.value))}
                className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Database & Detector Parameters */}
          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-slate-800 flex items-center space-x-2">
              <Database className="w-4 h-4 text-emerald-600" />
              <span>MongoDB & Detection Parameters</span>
            </h3>

            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">MongoDB Connection URI</label>
              <input
                type="text"
                value={mongoUri}
                onChange={(e) => setMongoUri(e.target.value)}
                className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Sigma Multiplier</label>
                <input
                  type="number"
                  step="0.5"
                  value={sigmaMultiplier}
                  onChange={(e) => setSigmaMultiplier(parseFloat(e.target.value))}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Persistence (Seconds)</label>
                <input
                  type="number"
                  value={persistenceSec}
                  onChange={(e) => setPersistenceSec(parseInt(e.target.value))}
                  className="w-full bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-sm font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
