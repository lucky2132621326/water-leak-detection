"""MongoDB Connection

Single shared client for all repositories (docs/DECISIONS.md #001). Connection
is lazy and cached — repositories import get_db() rather than each opening
their own client.

Mode separation
---------------
Live and mock data live in **physically separate databases**, and this function
is the only place that decision is made. Every repository already funnels
through `get_db()`, so routing here means no query anywhere else can accidentally
read across the boundary — there is no filter to forget on a WHERE clause,
because there is no shared collection to filter.

This is the MongoDB form of "separate files": stronger than a `data_source`
column, which is only as good as the discipline of every query that ever touches
the table.
"""
import os

from pymongo import MongoClient

from backend.mode import MODE_LIVE, MODE_MOCK, get_active_mode, require_mode
from backend.utils.logger import logger

#: Physically separate databases. Renamed from the old single
#: `water_leak_detection` database, whose contents were a mix of mock scenario
#: runs and seed data — see scripts/migrate_to_split_dbs.py.
DB_NAMES = {
    MODE_LIVE: os.getenv("MONGO_DB_LIVE", "jal_netra_live"),
    MODE_MOCK: os.getenv("MONGO_DB_MOCK", "jal_netra_mock"),
}

_client = None
_databases = {}


def get_client():
    global _client
    if _client is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        logger.info(f"[MongoDB] Connected to {uri}")
    return _client


def get_db(mode: str = None):
    """Database for `mode`, or for the active mode when not specified.

    Callers that already know which store they mean — a migration, a scoring run
    over mock data while live is active — should pass `mode` explicitly rather
    than relying on process state.
    """
    resolved = require_mode(mode or get_active_mode())
    if resolved not in _databases:
        name = DB_NAMES[resolved]
        _databases[resolved] = get_client()[name]
        logger.info(f"[MongoDB] Bound {resolved} mode to database '{name}'")
    return _databases[resolved]


def get_db_name(mode: str = None) -> str:
    return DB_NAMES[require_mode(mode or get_active_mode())]
