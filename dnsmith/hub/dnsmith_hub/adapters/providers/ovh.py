"""OVHcloud.

Not a request block for two reasons at once, and either would be enough.

OVH has two ways in, and they are different products: the DynHost endpoint,
which is plain DynDNS2 with a user and a password, and the OVH API, which
signs every call. The user picks one on the form, and a manifest cannot pick
a shape at runtime.

The API side signs with SHA1 over the secret, the consumer key, the method,
the full URL, the body and a timestamp — and the timestamp has to be OVH's,
not this machine's. An add-on on a device whose clock drifted would otherwise
fail with an authentication error that points at the credentials, which is
the wrong thing to go looking at. So each update asks OVH what time it is.

A zone change also needs a refresh afterwards, or it sits in the zone file
unpublished.
"""

from __future__ import annotations

import hashlib
import json as jsonlib
from typing import Any

from ..base import AdapterError
from ..native import interpret_dyndns2
from .support import Api, Context, succeeded

DYNHOST = "https://www.ovh.com/nic/update"

# OVH names its regions rather than its hosts. The names are what the user
# sees in their account, so the form takes those and the mapping lives here.
ENDPOINTS = {
    "": "https://eu.api.ovh.com/1.0",
    "ovh-eu": "https://eu.api.ovh.com/1.0",
    "ovh-ca": "https://ca.api.ovh.com/1.0",
    "ovh-us": "https://api.us.ovhcloud.com/1.0",
    "kimsufi-eu": "https://eu.api.kimsufi.com/1.0",
    "kimsufi-ca": "https://ca.api.kimsufi.com/1.0",
    "soyoustart-eu": "https://eu.api.soyoustart.com/1.0",
    "soyoustart-ca": "https://ca.api.soyoustart.com/1.0",
}


def update(api: Api, values: dict[str, Any], ctx: Context):
    if (values.get("mode") or "dynamic") == "dynamic":
        return _update_dynhost(api, values, ctx)
    return _update_zone(api, values, ctx)


# -- DynHost: plain DynDNS2 ------------------------------------------------

def _update_dynhost(api: Api, values: dict[str, Any], ctx: Context):
    status, body = api.call(
        DYNHOST,
        params={"system": "dyndns", "hostname": ctx.hostname, "myip": ctx.ip},
        headers={"Authorization": _basic(values["username"], values["password"])},
    )
    outcome = interpret_dyndns2(status, body)
    if not outcome.ok:
        raise AdapterError(outcome.code, outcome.message, detail=outcome.raw)
    return succeeded(outcome.message)


def _basic(username: str, password: str) -> str:
    import base64

    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


# -- The API: signed calls -------------------------------------------------

def _base(values: dict[str, Any]) -> str:
    endpoint = (values.get("api_endpoint") or "").strip()
    try:
        return ENDPOINTS[endpoint]
    except KeyError:
        raise AdapterError(
            "config",
            f"Unbekannter OVH-Endpunkt {endpoint!r}. "
            f"Möglich sind: {', '.join(name for name in ENDPOINTS if name)}.",
        ) from None


def _signed(api: Api, values: dict[str, Any], method: str, url: str,
            body: Any = None, timestamp: str = "") -> tuple[int, str]:
    """One API call, with the signature OVH expects.

    The signed string includes the body exactly as it goes out, so it is
    serialised once here and sent as text rather than handed to the JSON
    encoder again — a re-encoding with different spacing would invalidate the
    signature while looking identical.
    """
    payload = "" if body is None else jsonlib.dumps(body, separators=(",", ":"))
    material = "+".join([
        values["app_secret"], values["consumer_key"], method, url, payload, timestamp,
    ])
    signature = "$1$" + hashlib.sha1(material.encode()).hexdigest()  # noqa: S324 - OVH's scheme

    headers = {
        "X-Ovh-Application": values["app_key"],
        "X-Ovh-Consumer": values["consumer_key"],
        "X-Ovh-Timestamp": timestamp,
        "X-Ovh-Signature": signature,
        "Accept": "application/json;charset=utf-8",
    }
    if payload:
        headers["Content-Type"] = "application/json"

    # The signed bytes are the bytes that go out. Handing the object to a
    # JSON encoder again would produce the same document with different
    # spacing — and a signature over the other spelling.
    return api.call(url, method=method, headers=headers,
                    content=payload.encode() if payload else None)


def _update_zone(api: Api, values: dict[str, Any], ctx: Context):
    base = _base(values)

    # OVH's clock, not ours: a drifted device would otherwise be told its
    # credentials are wrong.
    status, body = api.call(f"{base}/auth/time")
    if status != 200 or not body.strip().isdigit():
        raise AdapterError("provider_response",
                           "OVH hat keine verwertbare Serverzeit geliefert.", detail=body[:200])
    timestamp = body.strip()

    zone = f"{base}/domain/zone/{ctx.domain}"
    listing = _json(_signed(api, values, "GET",
                            f"{zone}/record?fieldType={ctx.rrtype}&subDomain={ctx.subdomain}",
                            timestamp=timestamp))

    if listing:
        for record_id in listing:
            _json(_signed(api, values, "PUT", f"{zone}/record/{record_id}",
                          body={"target": ctx.ip}, timestamp=timestamp))
        message = "Der Eintrag wurde aktualisiert."
    else:
        _json(_signed(api, values, "POST", f"{zone}/record",
                      body={"fieldType": ctx.rrtype, "subDomain": ctx.subdomain,
                            "target": ctx.ip},
                      timestamp=timestamp))
        message = "Der Eintrag wurde beim Anbieter angelegt."

    # Without this the change sits in the zone but is never published.
    _json(_signed(api, values, "POST", f"{zone}/refresh", timestamp=timestamp))
    return succeeded(message)


def _json(answer: tuple[int, str]) -> Any:
    status, body = answer
    if status in (401, 403):
        raise AdapterError("auth", "OVH hat die Zugangsdaten abgelehnt.", detail=body[:200])
    if status == 404:
        raise AdapterError("not_found", "OVH kennt diese Zone nicht.", detail=body[:200])
    if not 200 <= status < 300:
        raise AdapterError("provider_response",
                           f"OVH hat mit HTTP {status} geantwortet.", detail=body[:200])
    if not body.strip():
        return None
    try:
        return jsonlib.loads(body)
    except ValueError as error:
        raise AdapterError("provider_response",
                           "OVH hat keine gültige JSON-Antwort geschickt.",
                           detail=body[:200]) from error
