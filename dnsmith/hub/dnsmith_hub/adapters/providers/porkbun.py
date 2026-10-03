"""Porkbun.

Not a request block for one reason: before a record can be created, Porkbun's
parked-domain placeholder has to go. A new domain arrives with an ALIAS on the
apex pointing at pixie.porkbun.com, and creating an A record next to it fails.
So the first update on a fresh domain is delete-then-create — two writes,
which the declarative path deliberately does not do.

The deletion is careful on purpose: only a single record, only the parked
placeholder, only at the apex or the wildcard. Anything else is somebody's own
record, and DNSmith does not delete those to make room for itself.
"""

from __future__ import annotations

from typing import Any

from ..base import AdapterError
from .support import Api, Context, find, succeeded

BASE = "https://api.porkbun.com/api/json/v3/dns"
PARKED = "pixie.porkbun.com"


def _credentials(values: dict[str, Any]) -> dict[str, str]:
    # Porkbun authenticates in the body, not in a header, and every call
    # repeats it.
    return {"apikey": values["api_key"], "secretapikey": values["secret_api_key"]}


def _records(api: Api, values: dict[str, Any], domain: str, rrtype: str, owner: str) -> list:
    answer = api.json(
        f"{BASE}/retrieveByNameType/{domain}/{rrtype}/{owner}",
        method="POST", json_body=_credentials(values),
    )
    return (answer or {}).get("records") or []


def _delete_parked_placeholder(api: Api, values: dict[str, Any], ctx: Context) -> None:
    """Remove the placeholder Porkbun puts on a new domain — and only that."""
    if ctx.owner == "@":
        candidates = [("ALIAS", "@")]
    elif ctx.owner == "*":
        candidates = [("CNAME", "*"), ("ALIAS", "@")]
    else:
        return

    for rrtype, owner in candidates:
        records = _records(api, values, ctx.domain, rrtype, "" if owner == "@" else owner)
        if len(records) != 1 or records[0].get("content") != PARKED:
            # Either nothing is in the way, or what is in the way belongs to
            # the user. Leaving it is the safe outcome; the create below will
            # fail and say so.
            continue
        api.json(f"{BASE}/deleteByNameType/{ctx.domain}/{rrtype}/{owner if owner != '@' else ''}",
                 method="POST", json_body=_credentials(values))


def update(api: Api, values: dict[str, Any], ctx: Context):
    api = api.with_headers(**{"Content-Type": "application/json"})
    records = _records(api, values, ctx.domain, ctx.rrtype, ctx.subdomain)

    if not records:
        _delete_parked_placeholder(api, values, ctx)
        answer = api.json(
            f"{BASE}/create/{ctx.domain}",
            method="POST",
            json_body={**_credentials(values), "name": ctx.subdomain, "type": ctx.rrtype,
                       "content": ctx.ip, "ttl": str(values.get("ttl") or 600)},
        )
        _check(answer)
        return succeeded("Der Eintrag wurde beim Anbieter angelegt.")

    for record in records:
        answer = api.json(
            f"{BASE}/edit/{ctx.domain}/{record['id']}",
            method="POST",
            json_body={**_credentials(values), "name": ctx.subdomain, "type": ctx.rrtype,
                       "content": ctx.ip, "ttl": str(values.get("ttl") or 600)},
        )
        _check(answer)

    return succeeded()


def _check(answer: Any) -> None:
    if isinstance(answer, dict) and answer.get("status") not in (None, "SUCCESS"):
        raise AdapterError(
            "provider_response",
            "Porkbun hat die Änderung abgelehnt.",
            detail=str(answer.get("message") or answer.get("status"))[:200],
        )
