"""DNSPod.

Not a request block because the write needs the record's line ("record_line"),
which only the listing knows — it is not a value DNSmith can supply or guess,
and it differs per record.

The API is form-encoded rather than JSON, and it answers HTTP 200 for
everything; the outcome lives in status.code, where "1" means success.
"""

from __future__ import annotations

from typing import Any

from ..base import AdapterError
from .support import Api, Context, find, succeeded

BASE = "https://dnsapi.cn"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _post(api: Api, path: str, body: dict[str, str]) -> dict:
    answer = api.json(f"{BASE}/{path}", method="POST", headers=FORM, form_body=body)
    status = (answer or {}).get("status") or {}

    if str(status.get("code")) == "1":
        return answer
    if str(status.get("code")) in ("-1", "-2", "6", "8"):
        raise AdapterError("auth", "DNSPod hat den Token abgelehnt.",
                           detail=str(status.get("message"))[:200])
    raise AdapterError("provider_response", "DNSPod hat die Anfrage abgelehnt.",
                       detail=str(status.get("message"))[:200])


def update(api: Api, values: dict[str, Any], ctx: Context):
    common = {"login_token": values["token"], "format": "json", "domain": ctx.domain}

    listing = _post(api, "Record.List", {
        **common, "length": "200", "sub_domain": ctx.owner, "record_type": ctx.rrtype})
    record = find(listing.get("records"), name=ctx.owner, type=ctx.rrtype)

    if record is None:
        raise AdapterError(
            "not_found",
            "Den Eintrag gibt es bei DNSPod nicht. Lege ihn dort einmal an; "
            "danach hält DNSmith ihn aktuell.",
        )
    if record.get("value") == ctx.ip:
        return succeeded("Der Eintrag war bereits aktuell.")

    _post(api, "Record.Ddns", {
        **common,
        "record_id": record["id"],
        "sub_domain": ctx.owner,
        "value": ctx.ip,
        # The line is the record's own; DNSPod rejects a write that changes it.
        "record_line": record.get("line") or "默认",
    })
    return succeeded()
