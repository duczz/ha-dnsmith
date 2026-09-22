"""Hetzner.

Not a request block because every write answers with an action rather than a
result: the API accepts the change, hands back {"action": {...}} and expects
the client to poll until it leaves the "running" state. Reporting success at
the moment the POST returned would be reporting that Hetzner accepted the
job, not that the record changed.

This module serves both the "hetzner" and "hetznercloud" manifests. Since
Hetzner shut down the separate DNS Console on 2026-05-27 and moved DNS into
the Cloud API, the two are the same service behind the same token and the
same endpoints. Keeping both entries is a courtesy to people who look for the
name they know; keeping two implementations would not be.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any

from ..base import AdapterError
from .support import Api, Context, succeeded

BASE = "https://api.hetzner.cloud/v1"

# DNS actions finish in well under a second in practice. The budget is an
# upper bound for a bad day, not an expected duration — and it is bounded
# because a scheduler pass must not hang on one record.
POLL_INTERVAL = 0.5
POLL_BUDGET = 20.0


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def update(api: Api, values: dict[str, Any], ctx: Context, *, sleep=time.sleep):
    api = api.with_headers(
        Authorization=f"Bearer {values['token']}",
        **{"Content-Type": "application/json", "Accept": "application/json"},
    )
    # The apex is "@" here, never an empty name.
    name = ctx.subdomain or "@"
    rrset = f"{BASE}/zones/{_quote(ctx.domain)}/rrsets/{_quote(name)}/{ctx.rrtype}"

    status, body = api.call(rrset)

    if status == 404:
        answer = api.json(
            f"{BASE}/zones/{_quote(ctx.domain)}/rrsets",
            method="POST",
            json_body={"name": name, "type": ctx.rrtype, "ttl": values.get("ttl"),
                       "records": [{"value": ctx.ip}]},
            expect=(200, 201, 202),
        )
        _await_action(api, answer, sleep)
        return succeeded("Der Eintrag wurde beim Anbieter angelegt.")

    if status in (401, 403):
        raise AdapterError("auth", "Hetzner hat den Token abgelehnt.", detail=body[:200])
    if status != 200:
        raise AdapterError("provider_response",
                           f"Hetzner hat mit HTTP {status} geantwortet.", detail=body[:200])

    answer = api.json(f"{rrset}/actions/set_records", method="POST",
                      json_body={"records": [{"value": ctx.ip}]}, expect=(200, 201, 202))
    _await_action(api, answer, sleep)
    return succeeded()


def _await_action(api: Api, answer: Any, sleep) -> None:
    """Wait for the action to finish, or say why it did not."""
    action = (answer or {}).get("action") or {}
    _raise_if_failed(action)

    if action.get("status") != "running":
        return

    deadline = time.monotonic() + POLL_BUDGET
    while time.monotonic() < deadline:
        sleep(POLL_INTERVAL)
        current = (api.json(f"{BASE}/actions/{action['id']}") or {}).get("action") or {}
        _raise_if_failed(current)
        if current.get("status") != "running":
            return

    raise AdapterError(
        "timeout",
        "Hetzner hat die Änderung angenommen, sie war aber nach 20 Sekunden "
        "noch nicht abgeschlossen. Der Eintrag kann trotzdem gesetzt worden sein.",
    )


def _raise_if_failed(action: dict) -> None:
    if action.get("status") == "error":
        error = action.get("error") or {}
        raise AdapterError(
            "provider_response",
            "Hetzner hat die Änderung abgelehnt.",
            detail=f"{error.get('code')}: {error.get('message')}"[:200],
        )
