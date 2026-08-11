"""Shared repository base.

Every repository used to bind `self.db = get_db()` in its constructor. With one
database that was harmless. With a database per mode it is a bug waiting to
happen: a repository built during startup in mock mode would hold the mock
handle forever and keep writing there after the operator switched to live —
silently filing physical rig data into the synthetic store.

Resolving the handle per access fixes it. A repository either follows the active
mode (the default) or is pinned to one mode explicitly, which is what scoring
and migration need when they read one store while another is active.
"""
from backend.mode import get_active_mode, require_mode
from backend.repositories.db import get_db


class ModeScopedRepository:
    def __init__(self, db=None, mode: str = None):
        #: An explicit handle (tests, migrations) always wins.
        self._db = db
        #: None means "whatever mode is active right now", resolved per access.
        self._mode = require_mode(mode) if mode else None

    @property
    def mode(self) -> str:
        return self._mode or get_active_mode()

    @property
    def db(self):
        if self._db is not None:
            return self._db
        return get_db(self.mode)

    def stamp(self, doc: dict) -> dict:
        """Tag a document with its mode before writing.

        Redundant with the database it is about to land in, deliberately. A
        record that gets exported, copied between environments, or read straight
        out of the shell still says what it is instead of depending on which file
        it happens to sit in.
        """
        doc["mode"] = self.mode
        return doc
