"""Storage for provider credentials.

Secrets live in their own file, apart from the configuration, for one reason:
everything that touches the configuration — the API, the export, a log line, a
diff in a bug report — then handles a structure that contains no credentials
at all. Redaction becomes something you cannot forget to do, rather than
something you must remember everywhere.

The file is written 0600 and replaced atomically, so a crash mid-write cannot
leave a half-file that loses every credential at once.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from pathlib import Path

SECRET_FILE_MODE = 0o600
SECRET_DIR_MODE = 0o700

# Shown instead of a value. Long enough to be obviously deliberate.
MASK = "••••••••"


class SecretStore:
    """Per-record credential storage, keyed by record ID and field ID."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._secrets: dict[str, dict[str, str]] = {}
        self._loaded = False
        # `probe()` reads this directly, bypassing ConfigStore's lock, while
        # create_record/update_record write through it from the event-loop
        # thread — needs its own lock, not just the store's.
        self._lock = threading.RLock()

    # -- reading -----------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            if not self._path.is_file():
                self._secrets = {}
                self._loaded = True
                return

            self._warn_on_loose_permissions()

            raw = json.loads(self._path.read_text(encoding="utf-8"))
            secrets = raw.get("secrets", {})
            if not isinstance(secrets, dict):
                raise ValueError("secrets file is malformed: 'secrets' is not an object")

            self._secrets = {
                record_id: {str(field): str(value) for field, value in fields.items()}
                for record_id, fields in secrets.items()
                if isinstance(fields, dict)
            }
            self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, record_id: str, field_id: str) -> str | None:
        with self._lock:
            self._ensure_loaded()
            return self._secrets.get(record_id, {}).get(field_id)

    def for_record(self, record_id: str) -> dict[str, str]:
        """All secrets of one record.

        The only caller that should use this is the adapter layer, which
        needs the real values to build an engine request.
        """
        with self._lock:
            self._ensure_loaded()
            return dict(self._secrets.get(record_id, {}))

    def field_names(self, record_id: str) -> list[str]:
        with self._lock:
            self._ensure_loaded()
            return sorted(self._secrets.get(record_id, {}))

    def has(self, record_id: str, field_id: str) -> bool:
        return self.get(record_id, field_id) is not None

    def all_values(self) -> set[str]:
        """Every stored secret, for the log redactor.

        This is the one place that hands out values in bulk, and it exists so
        that a value which does leak into a message can be caught on the way
        out. Nothing here is ever serialised.
        """
        with self._lock:
            self._ensure_loaded()
            return {
                value
                for fields in self._secrets.values()
                for value in fields.values()
                if value
            }

    # -- writing -----------------------------------------------------------

    def set_many(self, record_id: str, values: dict[str, str]) -> None:
        """Store or replace secrets.

        An empty string means "delete this one". A field simply absent from
        `values` is left alone — that is what lets the UI submit a form whose
        secret inputs were left blank without wiping the stored credentials.
        """
        with self._lock:
            self._ensure_loaded()
            current = dict(self._secrets.get(record_id, {}))

            for field_id, value in values.items():
                if value == "":
                    current.pop(field_id, None)
                else:
                    current[field_id] = value

            if current:
                self._secrets[record_id] = current
            else:
                self._secrets.pop(record_id, None)

            self.save()

    def forget(self, record_id: str) -> None:
        with self._lock:
            self._ensure_loaded()
            if self._secrets.pop(record_id, None) is not None:
                self.save()

    def forget_fields(self, record_id: str, field_ids: set[str]) -> None:
        """Drop specific fields, independent of what a caller submitted.

        `set_many` deliberately leaves an absent field alone — that is what
        lets a blank secret input mean "keep it". This is the other half:
        fields that belong to an auth variant the record no longer uses.
        Those are never present in a submitted form at all (the UI only ever
        renders the active variant's inputs), so `set_many` would leave them
        stranded forever without an explicit call like this one.
        """
        if not field_ids:
            return
        with self._lock:
            self._ensure_loaded()
            current = dict(self._secrets.get(record_id, {}))
            changed = False
            for field_id in field_ids:
                if current.pop(field_id, None) is not None:
                    changed = True

            if not changed:
                return
            if current:
                self._secrets[record_id] = current
            else:
                self._secrets.pop(record_id, None)
            self.save()

    def retain_only(self, record_ids: set[str]) -> list[str]:
        """Drop secrets whose record no longer exists.

        Called after a record is deleted. Orphaned credentials in a file the
        user may later export are exactly the kind of thing that outlives its
        purpose unnoticed.
        """
        with self._lock:
            self._ensure_loaded()
            orphans = [record_id for record_id in self._secrets if record_id not in record_ids]
            for record_id in orphans:
                del self._secrets[record_id]
            if orphans:
                self.save()
            return orphans

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self._path.parent, SECRET_DIR_MODE)

            payload = json.dumps(
                {"version": 1, "secrets": self._secrets}, indent=2, sort_keys=True
            )

            # Written to a temporary file in the same directory and renamed,
            # so the file is never observed partially written — and created
            # 0600 from the start, never briefly world-readable.
            handle, temporary = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".secrets-", suffix=".tmp"
            )
            try:
                os.fchmod(handle, SECRET_FILE_MODE)
                with os.fdopen(handle, "w", encoding="utf-8") as file:
                    file.write(payload)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self._path)
            except BaseException:
                try:
                    os.unlink(temporary)
                except OSError:  # pragma: no cover
                    pass
                raise

            os.chmod(self._path, SECRET_FILE_MODE)

    # -- diagnostics -------------------------------------------------------

    def _warn_on_loose_permissions(self) -> None:
        mode = stat.S_IMODE(self._path.stat().st_mode)
        if mode & 0o077:
            # Repaired rather than only reported: a credential file readable
            # by other users is worth fixing immediately, and the add-on is
            # the only legitimate writer.
            os.chmod(self._path, SECRET_FILE_MODE)
