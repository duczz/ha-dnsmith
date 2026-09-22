"""Aliyun DNS.

Signed like Route 53 is signed, but by a different scheme: every parameter of
the call, sorted and percent-encoded, becomes the string that is signed with
HMAC-SHA1, and the signature is appended as one more parameter.

Two steps, because Aliyun addresses a record by an ID that only the listing
knows — so this would be a lookup block if the signature did not have to be
computed over each call's own parameters.

One deviation from the code this was read off: the percent-encoding here
follows Aliyun's published rule (space as %20, "*" as %2A, "~" left alone)
rather than plain form-encoding. For the values that actually occur — host
names, IP addresses, record IDs — the two agree; for anything else the
published rule is the one Aliyun verifies against.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import secrets
import urllib.parse
from typing import Any

from ..base import AdapterError
from .support import Api, Context, succeeded

# Reading and writing live on different host names. That is Aliyun's doing,
# not a mistake here.
READ_HOST = "dns.aliyuncs.com"
WRITE_HOST = "alidns.aliyuncs.com"

API_VERSION = "2015-01-09"


def update(api: Api, values: dict[str, Any], ctx: Context, *, nonce=None, now=None):
    listing = _call(api, READ_HOST, values, {
        "Action": "DescribeDomainRecords",
        "DomainName": ctx.domain,
        "RRKeyWord": ctx.owner,
        "Type": ctx.rrtype,
    }, nonce=nonce, now=now)

    record = _match(listing, ctx)

    if record is None:
        _call(api, WRITE_HOST, values, {
            "Action": "AddDomainRecord",
            "DomainName": ctx.domain,
            "RR": ctx.owner,
            "Type": ctx.rrtype,
            "Value": ctx.ip,
        }, nonce=nonce, now=now)
        return succeeded("Der Eintrag wurde beim Anbieter angelegt.")

    if record.get("Value") == ctx.ip:
        return succeeded("Der Eintrag war bereits aktuell.")

    _call(api, WRITE_HOST, values, {
        "Action": "UpdateDomainRecord",
        "RecordId": record["RecordId"],
        "RR": ctx.owner,
        "Type": ctx.rrtype,
        "Value": ctx.ip,
    }, nonce=nonce, now=now)
    return succeeded()


def _match(listing: dict, ctx: Context) -> dict | None:
    """The record for this exact name and type.

    RRKeyWord is a keyword search, not an equality filter: asking for "home"
    also returns "home-office". Picking the first answer would update the
    wrong record.
    """
    records = ((listing.get("DomainRecords") or {}).get("Record")) or []
    for record in records:
        if record.get("RR") == ctx.owner and record.get("Type") == ctx.rrtype:
            return record
    return None


def _call(api: Api, host: str, values: dict[str, Any], action: dict[str, str],
          *, nonce=None, now=None) -> dict:
    params = {
        "AccessKeyId": values["access_key_id"],
        "Format": "JSON",
        "Version": API_VERSION,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": nonce or secrets.token_hex(16),
        "Timestamp": (now or datetime.datetime.now(datetime.timezone.utc))
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        **action,
    }
    params["Signature"] = sign("GET", params, values["access_secret"])

    status, body = api.call(f"https://{host}/", params=params,
                            headers={"Accept": "application/json"})

    import json as jsonlib

    try:
        answer = jsonlib.loads(body) if body.strip() else {}
    except ValueError:
        answer = {}

    if 200 <= status < 300:
        return answer

    raise _explain(status, answer, body)


def sign(method: str, params: dict[str, str], secret: str) -> str:
    """Aliyun's signature over the whole parameter set.

    https://www.alibabacloud.com/help/en/sdk/product-overview/rpc-mechanism
    """
    canonical = "&".join(
        f"{_quote(key)}={_quote(str(value))}" for key, value in sorted(params.items())
    )
    to_sign = f"{method.upper()}&{_quote('/')}&{_quote(canonical)}"
    digest = hmac.new(f"{secret}&".encode(), to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _quote(value: str) -> str:
    # Aliyun's percentEncode: form-encoding, then three corrections.
    quoted = urllib.parse.quote_plus(value, safe="")
    return quoted.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _explain(status: int, answer: dict, body: str) -> AdapterError:
    code = str(answer.get("Code") or "")
    message = str(answer.get("Message") or body[:200])
    detail = f"{code}: {message}".strip(": ")

    if code.startswith(("InvalidAccessKeyId", "SignatureDoesNotMatch", "Forbidden")):
        return AdapterError("auth", "Aliyun hat die Zugangsdaten abgelehnt.", detail=detail)
    if code.startswith("InvalidDomainName") or code.endswith("DomainNotExists"):
        return AdapterError("not_found", "Aliyun kennt diese Domain nicht.", detail=detail)
    if code.startswith("Throttling") or status == 429:
        return AdapterError("rate_limit", "Aliyun drosselt gerade.", detail=detail)
    return AdapterError(
        "provider_response", f"Aliyun hat mit HTTP {status} geantwortet.", detail=detail or None
    )
