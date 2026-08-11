"""Localization Service — which part of the loop is losing water.

The rig (spec Part A.1) offers two localization signals, and they are of very
different quality:

  * **`servo_state_deg`** — the MG996R pinch valve on **Branch A**. This is a
    step test, the miniature of what water utilities actually do: pinch the
    branch closed, watch whether the residual collapses. If it does, the leak was
    downstream of the pinch. That is direct causal evidence.
  * **`q_branch_lpm`** — Flow 3, which meters **Branch B**. This is *not*
    evidence of leak location. The meter reads what enters the branch; a leak
    downstream of it does not reduce that reading. Nonzero branch flow means the
    branch is in use, nothing more.

Two bugs lived here. The weak signal was tested first, so a Branch B diagnosis
was overwritten by branch flow — dispatching a crew to the wrong pipe. And branch
flow alone was reported as HIGH confidence, which it can never justify.

The three physical leak points are tee stubs A, B and C on the main trunk. Flow
instrumentation alone cannot separate them — that is what the step test and the
acoustic channel are for — so an un-isolated leak is reported at trunk level
rather than guessing a tee.
"""

#: Above this, Branch B is considered to be carrying flow at all.
_BRANCH_ACTIVE_LPM = 0.3
#: Below this residual there is nothing to localize.
_MIN_RESIDUAL_LPM = 0.1
#: Pinch valve fully closed. Anything at or above this is an isolation test.
_SERVO_CLOSED_DEG = 80

MAIN_TRUNK = "Main_Trunk"
BRANCH_A = "Branch_A"
BRANCH_B = "Branch_B"


class LocalizationService:
    def __init__(self):
        self.known_zones = [MAIN_TRUNK, BRANCH_A, BRANCH_B]

    def localize_leak(self, residual_lpm, q_branch_lpm, servo_state_deg=0):
        if residual_lpm < _MIN_RESIDUAL_LPM:
            return {"zone": "NONE", "confidence": "NONE"}

        # An isolation test is running: the Branch A pinch valve is closed and
        # the residual has NOT collapsed, so the loss is not on Branch A. This is
        # the strongest inference the rig can make, and it is a causal one.
        if servo_state_deg >= _SERVO_CLOSED_DEG:
            return {
                "zone": MAIN_TRUNK if q_branch_lpm <= _BRANCH_ACTIVE_LPM else BRANCH_B,
                "confidence": "HIGH",
                "basis": (f"step test: Branch A pinched at {servo_state_deg}° and the residual "
                          f"persists at {residual_lpm:.2f} L/min, so the loss is not on Branch A"),
            }

        # Valve open — no isolation evidence available. Branch flow is a hint
        # about which branches are live, never a finding about where the water is
        # going, so this is LOW and says why.
        if q_branch_lpm > _BRANCH_ACTIVE_LPM:
            return {
                "zone": MAIN_TRUNK,
                "confidence": "LOW",
                "basis": ("Branch B is carrying flow but no step test has been run. Flow 3 "
                          "meters the branch inlet and reads the same whether or not the leak "
                          "is downstream of it — pinch Branch A to isolate"),
            }

        return {
            "zone": MAIN_TRUNK,
            "confidence": "MEDIUM",
            "basis": "no branch flow and no step test — loss is on the main trunk",
        }
