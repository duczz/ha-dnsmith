"""DreamHost.

Not a request block because DreamHost has no update: a record is removed and
a new one added. Two writes, and the order matters — the removal has to
succeed before the addition, or the name ends up with nothing on it.

Its API is a single endpoint with a cmd parameter, and every call wants a
unique_id that the caller invents. That is a replay guard, so it has to be a
fresh value per call rather than something derived from the record.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..base import AdapterError
from .support import Api, Context, find, succeeded

BASE = "https://api.dreamhost.com/"


def _command(api: Api, values: dict[str, Any], command: str, **extra: str) -> dict:
    answer = api.json(BASE, params={
        "key": values["key"],
        # A fresh one per call: DreamHost uses it to recognise a repeat.
        "unique_id": str(uuid.uuid4()),
        "format": "json",
        "cmd": command,
        **extra,
    })
    if not isinstance(answer, dict) or answer.get("result") != "success":
        detail = str((answer or {}).get("data") or (answer or {}).get("result"))
        if "no_such_record" in detail or "no_record" in detail:
            raise AdapterError("not_found", "Den Eintrag gibt es bei DreamHost nicht.", detail=detail)
        raise AdapterError("provider_response", "DreamHost hat die Änderung abgelehnt.",
                           detail=detail[:200])
    return answer


def update(api: Api, values: dict[str, Any], ctx: Context):
    listing = _command(api, values, "dns-list_records")
    existing = find(listing.get("data"), record=ctx.hostname, type=ctx.rrtype)

    if existing and existing.get("value") == ctx.ip:
        return succeeded("Der Eintrag war bereits aktuell.")

    if existing:
        if existing.get("editable") == "0":
            raise AdapterError(
                "config",
                "Dieser Eintrag ist bei DreamHost nicht änderbar. "
                "Solche Einträge verwaltet DreamHost selbst.",
            )
        # Remove first: DreamHost refuses a second record of the same type on
        # the same name, so adding before removing would simply fail.
        _command(api, values, "dns-remove_record",
                 record=ctx.hostname, type=ctx.rrtype, value=existing["value"])

    _command(api, values, "dns-add_record",
             record=ctx.hostname, type=ctx.rrtype, value=ctx.ip)
    return succeeded()
