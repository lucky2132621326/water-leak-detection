"""Physical Plausibility Guard

Answers a question no single detector can: *is the flow reading itself
believable?*

Why this exists
---------------
Four of the five detectors are not independent. `mass_balance`, `cusum` and
`mnf` are three statistics of the SAME random variable — the flow residual
Q_in - (Q_out + Q_branch). When the outlet meter drops out, the residual jumps
to the full inlet flow and all three fire at once. Fusion then sees "multiple
methods agree" and confirms a leak, when in truth it has one broken measurement
counted three times.

This was found by the `sensor_fault` mock scenario: an outlet dropout with no
leak present produced 8 confirmed false positives at residual +5.20 L/min —
which is 100% of the inlet flow.

The insight
-----------
A dead flow meter is genuinely indistinguishable from a total leak *using flow
alone*. It is not indistinguishable using the whole instrument set. A leak is a
physical event: water escaping lowers the circuit's hydraulic resistance, so the
pump moves along its head-flow curve and its current shifts — and the escaping
jet excites the pipe wall audibly. Both effects come from different physics than
the flow imbalance, measured by different hardware.

The asymmetry that makes this work: **a dead flow meter makes no sound and draws
no extra current. A real leak does both.** Silence from a meter that claims a
catastrophic leak is not weak evidence — it is a contradiction.

So we do not merely ask the other channels to agree. We ask what they *should*
be reading if the flow claim were true, and check whether they read it:

    expected current drop = residual_lpm * current_ma_per_leak_lpm
    expected band_mid     = clean baseline * vib_ratio_threshold  (a real leak is audible)

If a claimed leak is big enough that a channel could not possibly miss it, and
that channel is sitting at baseline, the channel **contradicts** the flow
reading. That is positive evidence of an instrument fault, not an absence of
evidence for a leak.

Why the "should have seen it" gate is the whole design
------------------------------------------------------
A naive rule — "require the current sensor to agree before alarming" — would
destroy small-leak sensitivity. A 0.30 L/min weep predicts a ~10 mA current
drop, well under the current detector's 25 mA threshold, so that detector is
*correct* to stay quiet. Vetoing on its silence would suppress exactly the
leaks this system exists to catch.

A channel therefore gets a vote only when the predicted effect clears its own
threshold by `margin`. Below that it abstains, and abstention never vetoes.

Failure direction
-----------------
Fails OPEN. An unconfigured, uncalibrated or unavailable channel cannot veto,
and a veto requires zero corroborating channels. Suppressing a real burst is
far worse than the false positive this guard removes, so every ambiguous case
resolves toward letting the alarm through.

Suppression is never silent. The guard returns the contradiction so the
pipeline can report an INSTRUMENT FAULT — an operator must learn that a meter
died, and a quietly swallowed alarm would be its own kind of dishonesty.
"""
from backend.config.config_loader import thresholds_loader

#: Detectors that consume the flow residual. They are one measurement viewed
#: three ways, so their agreement carries no more weight than any one of them.
FLOW_CHANNEL_METHODS = ("mass_balance", "Mass_Balance", "cusum", "mnf")


class PlausibilityGuard:
    def __init__(self, current_ma_per_leak_lpm=None, acoustic_min_residual_lpm=None,
                 margin=None, min_residual_lpm=None, enabled=None):
        def cfg(explicit, key, default):
            return float(explicit if explicit is not None
                         else thresholds_loader.get(f"plausibility.{key}", default))

        #: Rig calibration: mA of pump current lost per L/min escaping. Measured
        #: on the bench by opening a known leak and recording the current delta.
        #: Zero disables the current channel's ability to contradict.
        self.current_ma_per_leak_lpm = cfg(current_ma_per_leak_lpm, "current_ma_per_leak_lpm", 35.0)
        #: Leak size above which the acoustic channel is expected to hear
        #: something. Below it a leak may genuinely be too quiet to resolve over
        #: pump noise, so acoustic silence proves nothing and must not veto.
        self.acoustic_min_residual_lpm = cfg(
            acoustic_min_residual_lpm, "acoustic_min_residual_lpm", 1.0)
        #: How far the predicted effect must clear a channel's own threshold
        #: before that channel is considered capable of contradicting. Above 1.0
        #: so ordinary calibration error and sensor noise cannot manufacture a
        #: veto near the boundary.
        self.margin = cfg(margin, "margin", 2.0)
        #: Never veto a claim smaller than this, whatever the arithmetic says.
        #: A backstop against a mis-set calibration constant silencing the small
        #: leaks the system is most valuable for catching.
        self.min_residual_lpm = cfg(min_residual_lpm, "min_residual_lpm", 0.75)

        configured = thresholds_loader.get("plausibility.enabled", True)
        self.enabled = configured if enabled is None else enabled

        self.current_threshold_ma = float(
            thresholds_loader.get("current_signature.drop_threshold_ma", 25.0))

    # --- channel tests ----------------------------------------------------
    def _current_verdict(self, residual, result):
        """Does the pump current corroborate, contradict, or abstain?"""
        if result is None or self.current_ma_per_leak_lpm <= 0:
            return None
        if result.get("is_alarm"):
            return {"channel": "current_signature", "verdict": "corroborates"}

        expected_drop_ma = residual * self.current_ma_per_leak_lpm
        required = self.current_threshold_ma * self.margin
        if expected_drop_ma < required:
            return {"channel": "current_signature", "verdict": "abstains",
                    "reason": f"a {residual:.2f} L/min leak predicts only "
                              f"{expected_drop_ma:.0f} mA of drop; this channel "
                              f"cannot resolve less than {required:.0f} mA"}

        # `residual_ma` is expected-minus-actual: how much current went missing.
        observed_drop_ma = float(result.get("residual_ma", 0.0))
        return {
            "channel": "current_signature",
            "verdict": "contradicts",
            "expected_drop": round(expected_drop_ma, 1),
            "observed_drop": round(observed_drop_ma, 1),
            "unit": "mA",
            "reason": f"flow claims {residual:.2f} L/min escaping, which requires a "
                      f"{expected_drop_ma:.0f} mA current drop; only {observed_drop_ma:.0f} mA observed",
        }

    def _acoustic_verdict(self, residual, result):
        """Does the pipe sound like it is leaking?

        This is the channel that most directly refutes a dead meter: a flow
        sensor reading zero produces no noise whatsoever, while water escaping at
        several L/min is loudly audible in the pipe wall. Silence against a large
        claimed leak is a contradiction, not merely an absence of evidence.
        """
        if result is None or not result.get("active"):
            return None
        if result.get("is_alarm"):
            return {"channel": "acoustic", "verdict": "corroborates"}
        if result.get("ratio") is None:
            return None  # still establishing baseline — nothing to compare against

        if residual < self.acoustic_min_residual_lpm:
            return {"channel": "acoustic", "verdict": "abstains",
                    "reason": f"a {residual:.2f} L/min leak may be too quiet to resolve "
                              f"over pump noise; this channel only speaks above "
                              f"{self.acoustic_min_residual_lpm:.2f} L/min"}

        ratio = float(result.get("ratio", 0.0))
        threshold = float(result.get("ratio_threshold", 1.8))
        return {
            "channel": "acoustic",
            "verdict": "contradicts",
            "expected_drop": threshold,
            "observed_drop": round(ratio, 3),
            "unit": "x baseline band_mid",
            "reason": f"flow claims {residual:.2f} L/min escaping, which would be clearly "
                      f"audible ({threshold:.2f}x baseline in 50-150 Hz); the pipe is at "
                      f"{ratio:.2f}x — essentially silent",
        }

    # --- public API -------------------------------------------------------
    def evaluate(self, residual, detector_results, pump_on=True, q_in=None):
        """Judge whether the flow residual is physically believable.

        Returns a verdict dict; `implausible` True means the leak alarm should
        be suppressed and an instrument fault raised in its place.
        """
        verdict = {
            "implausible": False,
            "channels": [],
            "contradicting": [],
            "corroborating": [],
            "reason": None,
        }

        by_method = {r.get("method"): r for r in detector_results}
        flow_alarms = [m for m in FLOW_CHANNEL_METHODS
                       if by_method.get(m, {}).get("is_alarm")]

        if not self.enabled:
            verdict["reason"] = "guard disabled"
            return verdict
        if not pump_on:
            # With the pump off there is no hydraulic signature and no jet noise
            # to predict, so neither channel can speak to the flow claim.
            verdict["reason"] = "pump off — no hydraulic prediction available"
            return verdict
        if not flow_alarms:
            verdict["reason"] = "no flow-channel alarm to adjudicate"
            return verdict
        if residual <= self.min_residual_lpm:
            verdict["reason"] = (f"residual {residual:.2f} L/min is at or below the "
                                 f"{self.min_residual_lpm:.2f} L/min floor; too small to "
                                 f"contradict on hydraulic grounds")
            return verdict

        for v in (self._current_verdict(residual, by_method.get("current_signature")),
                  self._acoustic_verdict(residual, by_method.get("acoustic"))):
            if v is None:
                continue
            verdict["channels"].append(v)
            if v["verdict"] == "contradicts":
                verdict["contradicting"].append(v["channel"])
            elif v["verdict"] == "corroborates":
                verdict["corroborating"].append(v["channel"])

        if verdict["corroborating"]:
            verdict["reason"] = (f"independent corroboration from "
                                 f"{', '.join(verdict['corroborating'])}")
            return verdict

        if not verdict["contradicting"]:
            verdict["reason"] = ("no independent channel is capable of resolving a leak "
                                 "this size; flow evidence stands unchallenged")
            return verdict

        verdict["implausible"] = True
        verdict["reason"] = "; ".join(
            v["reason"] for v in verdict["channels"] if v["verdict"] == "contradicts")
        verdict["fault_hypothesis"] = self._fault_hypothesis(residual, q_in)
        return verdict

    @staticmethod
    def _fault_hypothesis(residual, q_in):
        """Name the most likely instrument at fault, for the operator's benefit.

        A residual equal to essentially the whole inlet flow points at the
        outlet meter having stopped reporting rather than at a partial
        miscalibration.
        """
        if q_in and residual >= 0.9 * float(q_in):
            return "outlet flow meter reporting zero or near-zero — suspect dropout"
        return "flow meter reading inconsistent with pump current and pipe noise"
