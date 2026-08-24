"""Declarative mock scenarios.

A scenario describes what the *rig physically does* — flows, leaks, demand
regime, sensor faults, time of day. It says nothing about detection. That
separation is the point: you can add or retune a scenario without touching a
detector, and mock data cannot take a different code path because the generator
emits the same wire format the ESP32 publishes.

Scenarios are seeded, so a given scenario produces identical telemetry on every
run. Regression tests depend on that.
"""
from dataclasses import dataclass, field
from typing import List, Optional

MAIN = "Main_Trunk"
BRANCH_A = "Branch_A"
BRANCH_B = "Branch_B"

#: Physical leak points — worm-drive clamps on tee stubs off the main trunk.
TEE_A, TEE_B, TEE_C = "A", "B", "C"

#: Onset is never instantaneous. Backing off a hose clamp takes a moment and the
#: residual has to propagate past the meters, so even a "sudden" leak ramps.
DEFAULT_ONSET_RAMP_SEC = 2.0


@dataclass
class LeakProfile:
    """One physical leak, opened at a tee by backing off its clamp.

    `ramp_sec` distinguishes the two failure shapes: the default ~2 s is a clamp
    being opened by hand, while a large value models a joint slowly weeping —
    the case no single-sample threshold catches, and the reason CUSUM exists.
    """
    start_sec: float
    end_sec: float
    rate_lpm: float
    ramp_sec: float = DEFAULT_ONSET_RAMP_SEC
    tee_id: str = TEE_A
    location: str = MAIN

    def rate_at(self, t: float) -> float:
        if not (self.start_sec <= t <= self.end_sec):
            return 0.0
        if self.ramp_sec <= 0:
            return self.rate_lpm
        return self.rate_lpm * min(1.0, (t - self.start_sec) / self.ramp_sec)

    def is_active_at(self, t: float) -> bool:
        return self.start_sec <= t <= self.end_sec


@dataclass
class FaultProfile:
    """A sensor misbehaviour that is NOT a leak.

    These prove the system does not raise alarms on instrument problems. A
    detector that cannot tell a dropped meter from a burst pipe is worse than no
    detector.
    """
    kind: str            # "dropout" | "spike" | "noise_burst" | "stuck"
    start_sec: float
    end_sec: float
    magnitude: float = 1.0

    def is_active_at(self, t: float) -> bool:
        return self.start_sec <= t <= self.end_sec


@dataclass
class ScenarioSpec:
    id: str
    name: str
    description: str
    duration_sec: int = 300

    baseline_flow_lpm: float = 5.20
    #: Branch B flow. In-loop: it returns through the outlet meter, so it does
    #: NOT enter the residual (see backend/detectors/residual.py).
    branch_flow_lpm: float = 2.10

    #: Per-sensor measurement noise. The meters are physically different units,
    #: so their noise is independent — which is exactly why a small residual
    #: appears with no leak, and why detection needs a noise floor rather than a
    #: fixed threshold.
    noise_sigma_lpm: float = 0.02
    #: Permanent K-factor mismatch between the inlet and outlet meters. This is
    #: what `calibration.bias_lpm` exists to cancel.
    sensor_bias_lpm: float = 0.02

    #: P2 cycling. Detecting a leak against VARYING demand is the hard, realistic
    #: version of the problem, and results must be reported separately for the two.
    demand_mode: str = "steady"          # "steady" | "variable"
    demand_period_sec: float = 60.0
    demand_swing_lpm: float = 0.8

    pump_baseline_ma: float = 420.0
    #: A leak lowers hydraulic resistance, so the motor draws less. Negative by
    #: convention: mA lost per L/min escaping.
    current_per_leak_lpm: float = -35.0
    current_noise_ma: float = 2.0
    bus_v_nominal: float = 11.95
    bus_v_noise: float = 0.02

    #: Acoustic. band_mid (50-150 Hz) carries the leak jet; the others are mostly
    #: pump noise and respond only weakly.
    vib_baseline_mid: float = 0.030
    vib_per_leak_lpm: float = 0.055      # band_mid rise per L/min escaping
    vib_noise: float = 0.0025
    #: Per-run mounting variance. A real accelerometer is zip-tied by hand, so
    #: its absolute coupling to the pipe differs every time it is refitted —
    #: which is exactly why the detector and the model both work on RATIOS. This
    #: scales all band energies for the whole run, so a model that accidentally
    #: learned absolute levels fails here instead of in front of a judge.
    vib_mount_gain_spread: float = 0.35
    #: Cavitation bursts: short, loud, broadband events with NO leak behind them.
    #: Air coming out of solution at the pump inlet does this. They are the
    #: acoustic channel's main false-positive source, so a mock corpus without
    #: them overstates precision.
    cavitation_burst_probability: float = 0.004
    cavitation_burst_gain: float = 2.6
    emit_vibration: bool = True
    #: The piezo disc is optional hardware — a rig without one must still detect.
    emit_piezo: bool = True

    #: Reservoir warms over a long run as the pump does work. This walks the
    #: meters' K-factor and produces slow residual drift that looks like a
    #: worsening leak if uncorrected.
    water_c_start: float = 24.0
    water_c_rise_per_hour: float = 2.5
    emit_temp: bool = True

    # --- SIMULATED pressure channel (MOCK ONLY) ------------------------------
    # The physical rig has NO pressure transducer. These drive a generated
    # channel that demonstrates how the system extends to pressure
    # instrumentation, and every value is labelled SIMULATED downstream.
    #
    # The model is a pump curve: head falls as flow rises. A leak lowers
    # hydraulic resistance, so flow rises AND pressure falls — the same physical
    # event that shifts pump current. All three move together by construction
    # (see generator._simulated_pressure), so they can never contradict.
    emit_pressure: bool = True
    #: Shut-off head, i.e. pressure at zero flow. A 12V diaphragm pump is well
    #: under 1 bar; this is deliberately a realistic figure and not the 2.5 bar
    #: the old fabricated channel claimed.
    pressure_shutoff_bar: float = 0.85
    #: Slope of the pump curve: bar lost per L/min of total throughput.
    pressure_curve_slope: float = 0.058
    #: Extra sag at the tee per L/min escaping, on top of the curve effect.
    pressure_per_leak_lpm: float = 0.045
    pressure_noise_bar: float = 0.004

    #: Wall-clock start, "HH:MM". Required to exercise MNF, which only evaluates
    #: between 01:00 and 05:00.
    start_time: Optional[str] = None

    leaks: List[LeakProfile] = field(default_factory=list)
    faults: List[FaultProfile] = field(default_factory=list)
    seed: int = 42

    #: What a correct system should conclude. Used by tests and the scenario
    #: results panel; never consulted by the detectors.
    expect_detection: bool = True
    expect_zone: Optional[str] = None

    def total_leak_at(self, t: float) -> float:
        return sum(l.rate_at(t) for l in self.leaks)

    def is_leaking_at(self, t: float) -> bool:
        return any(l.is_active_at(t) and l.rate_at(t) > 0 for l in self.leaks)

    def ground_truth_windows(self) -> List[dict]:
        return [
            {"open_sec": l.start_sec, "close_sec": l.end_sec, "leak_lpm": l.rate_lpm,
             "tee_id": l.tee_id, "location": l.location, "ramp_sec": l.ramp_sec}
            for l in self.leaks
        ]

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            # Manual Control is an indefinite operator sandbox, not a
            # reproducible benchmark with scripted ground truth.
            "scoreable": self.id != "manual_control",
            "duration_sec": self.duration_sec,
            "leak_count": len(self.leaks),
            "fault_count": len(self.faults),
            "max_leak_lpm": max((l.rate_lpm for l in self.leaks), default=0.0),
            "start_time": self.start_time,
            "demand_mode": self.demand_mode,
            "emits_vibration": self.emit_vibration,
            "emits_piezo": self.emit_piezo,
            "expect_detection": self.expect_detection,
            "expect_zone": self.expect_zone,
        }


# --- Built-in library --------------------------------------------------------

BUILTIN_SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        id="manual_control",
        name="Manual Control (free run)",
        description=(
            "Healthy baseline that runs indefinitely with no scripted leaks. "
            "The default for interactive testing: start from normal operation and "
            "open, resize, relocate or close a simulated leak yourself from the bench "
            "controls, then watch the same pipeline detect and recover."
        ),
        duration_sec=3600,
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="normal_operation",
        name="Normal Operation (steady demand)",
        description="Healthy pipe, no leak, P2 steady. The control case — any alarm here is a false positive.",
        duration_sec=300,
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="normal_variable_demand",
        name="Normal Operation (variable demand)",
        description=(
            "No leak, but P2 cycling to swing demand. The control case for the hard "
            "regime: fluctuating demand must not be mistaken for a leak."
        ),
        duration_sec=360,
        demand_mode="variable",
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="small_leak",
        name="Small Leak (0.34 L/min, tee A)",
        description="Clamp A at half a turn — a slow weep near the detection floor. Tests sensitivity without tripping on noise.",
        duration_sec=300,
        leaks=[LeakProfile(start_sec=120, end_sec=240, rate_lpm=0.34, tee_id=TEE_A, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="large_leak",
        name="Large Leak (2.5 L/min)",
        description="Major rupture — roughly half the inlet flow escaping. Should be caught almost immediately.",
        duration_sec=300,
        leaks=[LeakProfile(start_sec=120, end_sec=240, rate_lpm=2.50, tee_id=TEE_B, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="sudden_leak",
        name="Sudden Leak (clamp opened fast)",
        description="A 1.25 L/min leak opened in about two seconds, as fast as a hand can back off a clamp. Tests detection latency.",
        duration_sec=300,
        leaks=[LeakProfile(start_sec=150, end_sec=270, rate_lpm=1.25, ramp_sec=2.0, tee_id=TEE_C, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="gradual_leak",
        name="Gradual Leak (ramp)",
        description=(
            "Leak grows from zero to 1.2 L/min over two minutes. Deliberately hostile to "
            "threshold detectors — the mass balance baseline adapts as it grows, so this is "
            "primarily a CUSUM test."
        ),
        duration_sec=420,
        leaks=[LeakProfile(start_sec=120, end_sec=360, rate_lpm=1.20, ramp_sec=120.0, tee_id=TEE_A, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="leak_under_variable_demand",
        name="Leak Under Variable Demand",
        description=(
            "0.9 L/min at tee B while P2 cycles demand by ±0.8 L/min. The realistic hard "
            "case: the leak signal must be separated from legitimate demand swing."
        ),
        duration_sec=420,
        demand_mode="variable",
        leaks=[LeakProfile(start_sec=150, end_sec=330, rate_lpm=0.90, tee_id=TEE_B, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="night_flow",
        name="Minimum Night Flow",
        description=(
            "Runs at 02:00 with a small 0.25 L/min loss. The only scenario that can exercise "
            "the MNF detector, which evaluates solely inside the 01:00-05:00 quiet window."
        ),
        duration_sec=300,
        baseline_flow_lpm=1.10,
        branch_flow_lpm=0.30,
        start_time="02:00",
        leaks=[LeakProfile(start_sec=100, end_sec=260, rate_lpm=0.25, tee_id=TEE_A, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="sensor_noise",
        name="Sensor Noise / Fluctuation",
        description=(
            "No leak, but 5x normal measurement noise plus a burst of instability. "
            "A false-positive test: the correct outcome is silence."
        ),
        duration_sec=300,
        noise_sigma_lpm=0.10,
        faults=[FaultProfile(kind="noise_burst", start_sec=120, end_sec=180, magnitude=3.0)],
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="sensor_fault",
        name="Sensor Dropout & Spikes",
        description=(
            "Outlet meter drops out, then throws spikes, with no leak present. Proves the "
            "system distinguishes an instrument fault from a burst pipe — the flow meters "
            "claim a total loss while the pump current and the pipe itself stay silent."
        ),
        duration_sec=300,
        faults=[
            FaultProfile(kind="dropout", start_sec=90, end_sec=110),
            FaultProfile(kind="spike", start_sec=170, end_sec=175, magnitude=2.5),
            FaultProfile(kind="stuck", start_sec=220, end_sec=250),
        ],
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="no_acoustic_hardware",
        name="No Accelerometer Fitted",
        description=(
            "A real 1.1 L/min leak on a rig with no MPU6050 and no piezo. Proves detection "
            "degrades gracefully to the flow and current channels rather than breaking, and "
            "that fusion renormalises so the score stays on the same 0-1 scale."
        ),
        duration_sec=300,
        emit_vibration=False,
        emit_piezo=False,
        leaks=[LeakProfile(start_sec=120, end_sec=250, rate_lpm=1.10, tee_id=TEE_B, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="no_piezo",
        name="Accelerometer Only (no piezo disc)",
        description=(
            "The likely bring-up configuration: MPU6050 mounted, piezo not yet fitted. "
            "The acoustic channel must work on the accelerometer alone."
        ),
        duration_sec=300,
        emit_piezo=False,
        leaks=[LeakProfile(start_sec=120, end_sec=250, rate_lpm=1.10, tee_id=TEE_A, location=MAIN)],
        expect_zone=MAIN,
    ),
    ScenarioSpec(
        id="thermal_drift",
        name="Thermal Drift (long run, no leak)",
        description=(
            "A 40-minute clean run in which the pump warms the reservoir by several degrees. "
            "K-factor drifts with water viscosity, walking the residual baseline. Uncorrected "
            "this looks exactly like a slowly worsening leak — the correct outcome is silence."
        ),
        duration_sec=2400,
        water_c_rise_per_hour=4.0,
        leaks=[],
        expect_detection=False,
    ),
    ScenarioSpec(
        id="multiple_conditions",
        name="Multiple Abnormal Conditions",
        description=(
            "Two overlapping leaks at different tees, elevated noise, variable demand and a "
            "sensor spike. The hardest case: fusion must stay coherent when several things "
            "are wrong at once."
        ),
        duration_sec=480,
        demand_mode="variable",
        noise_sigma_lpm=0.05,
        leaks=[
            LeakProfile(start_sec=100, end_sec=300, rate_lpm=0.70, tee_id=TEE_A, location=MAIN),
            LeakProfile(start_sec=220, end_sec=420, rate_lpm=1.10, ramp_sec=60.0, tee_id=TEE_C, location=MAIN),
        ],
        faults=[FaultProfile(kind="spike", start_sec=350, end_sec=354, magnitude=2.0)],
        expect_zone=MAIN,
    ),
]

_BY_ID = {s.id: s for s in BUILTIN_SCENARIOS}


def get_scenario(scenario_id: str) -> Optional[ScenarioSpec]:
    return _BY_ID.get(scenario_id)


def list_scenarios() -> List[dict]:
    return [s.summary() for s in BUILTIN_SCENARIOS]


def scenario_from_dict(data: dict) -> ScenarioSpec:
    """Build a custom scenario from an API payload, so operators can define new
    cases without a code change."""
    leaks = [LeakProfile(**l) for l in data.get("leaks", [])]
    faults = [FaultProfile(**f) for f in data.get("faults", [])]
    known = {f for f in ScenarioSpec.__dataclass_fields__ if f not in ("leaks", "faults")}
    kwargs = {k: v for k, v in data.items() if k in known}
    kwargs.setdefault("id", "custom")
    kwargs.setdefault("name", "Custom Scenario")
    kwargs.setdefault("description", "Operator-defined scenario")
    return ScenarioSpec(leaks=leaks, faults=faults, **kwargs)
