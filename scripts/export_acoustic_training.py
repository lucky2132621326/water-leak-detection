"""Export a training CSV from the LIVE database — telemetry joined to leak_events.

This is the path from "physical runs on the bench" to "a bundle that is allowed
to run in live mode". Today's bundle is marked SYNTHETIC and the live-mode gate
refuses it; the only way to lift that is to train on rows produced by this
script.

    python scripts/export_acoustic_training.py --out training.csv
    python scripts/export_acoustic_training.py --mode mock --out mock_training.csv

Columns:
    run_id, ts, band_low, band_mid, band_high, rms,
    piezo_rms, piezo_centroid_hz, water_c, pump_duty, leak, lpm

Labelling
---------
A telemetry row is `leak=1` when its `ts` falls inside a logged leak window
[open_ts, close_ts], extended by the configured scoring grace. Those windows are
operator-logged physical events — someone opened a calibrated clamp and the
software recorded when. That is the only ground truth this project has, and it is
why `lpm` is the clamp's calibrated rate rather than any detector's estimate.

Reads the LIVE store by default. Pointing it at mock produces a corpus of
generated data, which is useful for exercising the pipeline but must be exported
with `note='SYNTHETIC — not valid results'` when bundled — see --mode's warning.

Swapping in a retrained bundle needs no code change: drop the file somewhere and
point `acoustic_ml.bundle_path` in backend/config/thresholds.yaml at it.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.benchmark.ground_truth import matching_window, normalise_windows
from backend.ml.acoustic_features import resolve_pump_duty
from backend.mode import MODE_LIVE, MODE_MOCK
from backend.repositories.db import get_db, get_db_name

COLUMNS = [
    "run_id", "ts",
    "band_low", "band_mid", "band_high", "rms",
    "piezo_rms", "piezo_centroid_hz", "water_c",
    "pump_duty", "leak", "lpm",
]

#: Duty buckets the baseline is keyed by. Must match the runtime and the bundle,
#: or the ratios computed at inference divide by a different number than the
#: ones the model trained on.
DUTY_LEVELS = (0.6, 0.8, 1.0)


def export(mode: str, out_path: str, nominal_flow_lpm: float, run_ids=None) -> int:
    db = get_db(mode)
    query = {"run_id": {"$in": run_ids}} if run_ids else {}

    events = list(db.leak_events.find(query))
    windows = normalise_windows(events)
    if not windows:
        print(f"WARNING: no leak_events in '{get_db_name(mode)}'. Every row will be "
              f"labelled leak=0, which trains a model that has never seen a leak.")

    docs = list(db.telemetry.find(query).sort("ts", 1))
    if not docs:
        print(f"No telemetry in '{get_db_name(mode)}'"
              + (f" for runs {run_ids}" if run_ids else "") + ". Nothing to export.")
        return 1

    written = skipped = positives = 0
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()

        for doc in docs:
            vib = doc.get("vibration") or {}
            temp = doc.get("temp") or {}
            flow = doc.get("flow") or {}
            actuators = doc.get("actuators") or {}

            row = {
                "band_low": vib.get("band_low"),
                "band_mid": vib.get("band_mid"),
                "band_high": vib.get("band_high"),
                "rms": vib.get("rms"),
                "piezo_rms": vib.get("piezo_rms"),
                "piezo_centroid_hz": vib.get("piezo_centroid_hz"),
                "water_c": temp.get("water_c"),
            }
            # A row missing any model input is DROPPED, never imputed. Filling a
            # gap with a mean would teach the model that the mean is what a
            # missing sensor looks like, and it would then predict confidently
            # on exactly the samples it should refuse.
            if any(v is None for v in row.values()):
                skipped += 1
                continue

            ts = doc.get("ts")
            window = matching_window(ts, windows)
            duty = resolve_pump_duty(
                DUTY_LEVELS,
                pump1=actuators.get("pump1", True),
                pump2=actuators.get("pump2", False),
                q_in_lpm=flow.get("q_in_lpm"),
                nominal_flow_lpm=nominal_flow_lpm,
            )

            row.update({
                "run_id": doc.get("run_id"),
                "ts": ts,
                "pump_duty": duty,
                "leak": 1 if window else 0,
                # The clamp's calibrated rate — what the rig was SET to leak.
                # Never a detector's estimate: labelling with the model's own
                # opinion is how a classifier learns to agree with itself.
                "lpm": (window or {}).get("leak_lpm") or 0.0,
            })
            writer.writerow(row)
            written += 1
            positives += row["leak"]

    print(f"Wrote {written} rows to {out_path} from '{get_db_name(mode)}'")
    print(f"  leak=1 : {positives}  ({positives / written:.1%})" if written else "")
    print(f"  leak=0 : {written - positives}")
    print(f"  skipped: {skipped} rows missing a required sensor value (not imputed)")
    print(f"  windows: {len(windows)} logged leak events")

    if written and positives == 0:
        print("\nWARNING: no positive samples. A model trained on this cannot detect a leak.")
    elif written and positives / written < 0.05:
        print(f"\nNOTE: positives are {positives / written:.1%} of the corpus. Consider "
              f"class weighting when training, or a classifier will score well by "
              f"always predicting 'no leak'.")

    if mode == MODE_MOCK:
        print("\n" + "=" * 70)
        print("THIS IS GENERATED DATA. A bundle trained on it MUST carry")
        print("    note = 'SYNTHETIC — not valid results'")
        print("and will be refused in live mode. Only a bundle trained on physical")
        print("runs may be exported with note = 'trained on physical ground truth'.")
        print("=" * 70)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=[MODE_LIVE, MODE_MOCK], default=MODE_LIVE,
                        help="which store to read (default: live)")
    parser.add_argument("--out", default="acoustic_training.csv")
    parser.add_argument("--runs", nargs="*", default=None,
                        help="limit to these run_ids (default: all)")
    parser.add_argument("--nominal-flow-lpm", type=float, default=5.2,
                        help="full-flow reference for duty bucketing; MUST match "
                             "acoustic_ml.nominal_flow_lpm in thresholds.yaml")
    args = parser.parse_args()
    sys.exit(export(args.mode, args.out, args.nominal_flow_lpm, args.runs))
