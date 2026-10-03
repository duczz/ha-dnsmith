"""netcup.

Not a request block because netcup's CCP is JSON-RPC over a single endpoint
with a session: log in, read the zone, write the zone, log out. The session ID
from the first call is required by every later one, and the credential that
obtains it is not the credential that authorises the write — that is a
sequence, not a request.

The write posts a record set rather than a record, which is why the listing
is read first: what is sent back is the existing entry with a new
destination, so that netcup does not lose the fields DNSmith never knew about.
"""

from __future__ import annotations

from typing import Any

from ..base import AdapterError
from .support import Api, Context, find, succeeded

ENDPOINT = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"


def _rpc(api: Api, action: str, param: dict[str, Any]) -> dict:
    answer = api.json(ENDPOINT, method="POST", json_body={"action": action, "param": param})
    answer = answer or {}

    if answer.get("status") == "success":
        return answer.get("responsedata") or {}

    message = str(answer.get("longmessage") or answer.get("shortmessage") or "")
    code = "auth" if str(answer.get("statuscode")) in ("4013", "4001") else "provider_response"
    raise AdapterError(code, f"netcup hat \"{action}\" abgelehnt.", detail=message[:200])


def update(api: Api, values: dict[str, Any], ctx: Context):
    api = api.with_headers(**{"Content-Type": "application/json", "Accept": "application/json"})
    account = {"apikey": values["api_key"], "customernumber": values["customer_number"]}

    session = _rpc(api, "login", {**account, "apipassword": values["password"]})["apisessionid"]
    authenticated = {**account, "apisessionid": session}

    try:
        listing = _rpc(api, "infoDnsRecords", {**authenticated, "domainname": ctx.domain})
        record = find(listing.get("dnsrecords"), hostname=ctx.owner, type=ctx.rrtype)

        if record is None:
            raise AdapterError(
                "not_found",
                "Den Eintrag gibt es bei netcup nicht. Lege ihn dort einmal an; "
                "danach hält DNSmith ihn aktuell.",
            )
        if record.get("destination") == ctx.ip:
            return succeeded("Der Eintrag war bereits aktuell.")

        # Send the record back as it came, with only the destination changed:
        # priority, state and anything netcup adds later survive that way.
        _rpc(api, "updateDnsRecords", {
            **authenticated,
            "domainname": ctx.domain,
            "dnsrecordset": {"dnsrecords": [{**record, "destination": ctx.ip}]},
        })
        return succeeded()
    finally:
        # A session left open counts against netcup's limit, so it is closed
        # even when the update failed.
        try:
            _rpc(api, "logout", authenticated)
        except AdapterError:
            pass
