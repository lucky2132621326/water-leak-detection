"""Move the pre-split database into the mock store.

The old single `water_leak_detection` database holds scenario runs and seed data.
None of it came from physical hardware — there was no rig when it was written —
so it all belongs in the mock store. Labelling any of it live would be exactly
the dishonesty the split exists to prevent: a reviewer looking at a "live" run
must be able to trust that a physical valve was actually opened.

The data is kept rather than dropped: it is still a perfectly good corpus for
exercising the mock path.

Idempotent. Run from the repo root:

    python scripts/migrate_to_split_dbs.py            # dry run, shows the plan
    python scripts/migrate_to_split_dbs.py --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mode import MODE_MOCK
from backend.repositories.db import DB_NAMES, get_client

LEGACY_DB_NAME = os.getenv("MONGO_DB_NAME", "water_leak_detection")

#: Every collection the app writes. Listed explicitly rather than discovered so
#: an unexpected collection is reported instead of silently migrated.
COLLECTIONS = (
    "telemetry", "detections", "leak_events",
    "experiment_runs", "work_orders", "alerts", "events",
)


def migrate(apply: bool) -> int:
    client = get_client()
    names = client.list_database_names()

    if LEGACY_DB_NAME not in names:
        print(f"No legacy database '{LEGACY_DB_NAME}' — nothing to migrate.")
        return 0

    legacy = client[LEGACY_DB_NAME]
    target = client[DB_NAMES[MODE_MOCK]]

    unexpected = set(legacy.list_collection_names()) - set(COLLECTIONS)
    if unexpected:
        print(f"WARNING: unlisted collections will NOT be migrated: {sorted(unexpected)}")

    total = 0
    for name in COLLECTIONS:
        docs = list(legacy[name].find({}))
        if not docs:
            continue

        # Stamp the mode onto every record. Redundant with which database it now
        # sits in, and kept anyway so an exported document is self-describing.
        for d in docs:
            d["mode"] = MODE_MOCK
            d.setdefault("source", MODE_MOCK)

        print(f"  {name:18s} {len(docs):6d} docs -> {DB_NAMES[MODE_MOCK]}.{name}")
        total += len(docs)

        if apply:
            existing = {d["_id"] for d in target[name].find({}, {"_id": 1})}
            fresh = [d for d in docs if d["_id"] not in existing]
            if fresh:
                target[name].insert_many(fresh)
            print(f"  {'':18s} {len(fresh):6d} inserted, {len(docs) - len(fresh)} already present")

    if not apply:
        print(f"\nDRY RUN — {total} documents would move. Re-run with --apply.")
        print(f"The legacy database '{LEGACY_DB_NAME}' is left untouched either way;")
        print("drop it by hand once you have confirmed the migration.")
    else:
        print(f"\nMigrated {total} documents into '{DB_NAMES[MODE_MOCK]}'.")
        print(f"'{LEGACY_DB_NAME}' is left in place as a backup — drop it when satisfied.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    sys.exit(migrate(parser.parse_args().apply))
