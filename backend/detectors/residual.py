"""The residual — the single signal the whole detection stack rests on.

    R = Q_in - Q_out - bias                        (this rig)
    R = Q_in - (Q_out + Q_branch) - bias           (branch metered as a separate exit)

Why the topology matters
------------------------
On this rig (spec Part A.1) Flow 3 sits on Branch B, and Branch B flows *through*
Flow 2 on its way back to the bucket. Q_branch is therefore an in-loop
sub-measurement: **Q_out already contains it.** Subtracting it as well
double-counts the branch and drags the residual permanently negative by roughly
the branch flow. With the spec's own example sample:

    q_in 4.812, q_out 4.655, q_branch 2.104
      correct   4.812 - 4.655           = +0.157   plausible
      wrong     4.812 - 4.655 - 2.104   = -1.947   every sample, forever

The other topology is real too — a branch that leaves the loop and is metered on
its way out *is* a separate exit and must be subtracted. So this is a
configuration property of the plumbing, not a constant, and it is resolved in one
place rather than repeated at each call site. It was previously hardcoded
identically in four files, which is how a topology assumption becomes invisible.

`bias` is the mean residual over a 30-minute zero-leak run: the permanent
systematic offset between two physically different meters. It is a calibration
input, never a detection threshold.
"""
from backend.config.config_loader import thresholds_loader


def subtract_branch() -> bool:
    """True when the branch meter measures flow *leaving* the monitored loop."""
    return bool(thresholds_loader.get("topology.subtract_branch", False))


def flow_bias_lpm() -> float:
    return float(thresholds_loader.get("calibration.bias_lpm", 0.0))


def compute_residual(q_in: float, q_out: float, q_branch: float = 0.0,
                     apply_bias: bool = True) -> float:
    """Unaccounted flow, in L/min. Positive means water is going missing."""
    residual = q_in - q_out
    if subtract_branch():
        residual -= q_branch
    if apply_bias:
        residual -= flow_bias_lpm()
    return residual


def describe_topology() -> dict:
    """The formula actually in force, so the UI can publish it rather than a
    hand-copied version that may no longer be true."""
    branch = subtract_branch()
    return {
        "subtract_branch": branch,
        "bias_lpm": flow_bias_lpm(),
        "formula": ("R = Q_in - (Q_out + Q_branch) - bias" if branch
                    else "R = Q_in - Q_out - bias"),
        "rationale": (
            "Branch meter measures flow leaving the monitored loop, so it is a separate exit."
            if branch else
            "Branch B flows through the outlet meter, so Q_out already includes it — "
            "subtracting Q_branch as well would double-count the branch."
        ),
    }
