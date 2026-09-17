"""Amazon Route 53.

A module for the reason the whole tier exists: every call is signed, and the
signature covers the method, the path, the headers and a hash of the body.
Nothing in a manifest can express that.

No boto3. The library is excellent and weighs more than this entire add-on;
what is needed here is one signature for one fixed request, and that is forty
lines of hmac and hashlib from the standard library. An image that runs on a
Raspberry Pi should not carry an AWS SDK so that three people can use Route 53.

Route 53 is a single UPSERT: the API has no separate create, and sending the
record set replaces whatever was there. So there is no lookup either.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import xml.etree.ElementTree as ElementTree
from typing import Any
from xml.sax.saxutils import escape

from ..base import AdapterError
from .support import Api, Context, succeeded

HOST = "route53.amazonaws.com"
NAMESPACE = "https://route53.amazonaws.com/doc/2013-04-01/"

# Route 53 is a global service, and a global service is signed against
# us-east-1 no matter where the caller sits.
REGION = "us-east-1"
SERVICE = "route53"
CONTENT_TYPE = "application/xml"

DEFAULT_TTL = 300


def update(api: Api, values: dict[str, Any], ctx: Context, *, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    path = f"/2013-04-01/hostedzone/{values['zone_id']}/rrset"
    body = _change_batch(ctx, int(values.get("ttl") or DEFAULT_TTL)).encode()

    headers = {
        "Content-Type": CONTENT_TYPE,
        "Accept": CONTENT_TYPE,
        "Host": HOST,
        "Date": now.strftime("%Y%m%dT%H%M%SZ"),
        "Authorization": sign(
            method="POST",
            path=path,
            payload=body,
            moment=now,
            access_key=values["access_key"],
            secret_key=values["secret_key"],
        ),
    }

    status, answer = api.call(
        f"https://{HOST}{path}", method="POST", headers=headers, content=body
    )

    if 200 <= status < 300:
        return succeeded()
    raise _explain(status, answer)


def _change_batch(ctx: Context, ttl: int) -> str:
    """The UPSERT document.

    Built as text rather than through a serialiser because the signature is
    over these exact bytes: a library that reorders attributes or changes the
    declaration would produce the same document and a different signature.
    """
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<ChangeResourceRecordSetsRequest xmlns="{NAMESPACE}">'
        f"<ChangeBatch><Changes><Change>"
        f"<Action>UPSERT</Action>"
        f"<ResourceRecordSet>"
        f"<Name>{escape(ctx.hostname)}</Name>"
        f"<Type>{ctx.rrtype}</Type>"
        f"<TTL>{ttl}</TTL>"
        f"<ResourceRecords><ResourceRecord>"
        f"<Value>{escape(ctx.ip)}</Value>"
        f"</ResourceRecord></ResourceRecords>"
        f"</ResourceRecordSet>"
        f"</Change></Changes></ChangeBatch>"
        f"</ChangeResourceRecordSetsRequest>"
    )


# -- Signature Version 4 ----------------------------------------------------
#
# https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html
#
# Only the header-based variant for one fixed shape of request: two signed
# headers, no query string. Generalising it would mean writing an SDK.


def sign(*, method: str, path: str, payload: bytes, moment: datetime.datetime,
         access_key: str, secret_key: str) -> str:
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    day = moment.strftime("%Y%m%d")
    scope = f"{day}/{REGION}/{SERVICE}/aws4_request"
    signed_headers = "content-type;host"

    canonical_request = "\n".join([
        method.upper(),
        path,
        "",                                           # no query
        f"content-type:{CONTENT_TYPE}\nhost:{HOST}\n",
        signed_headers,
        hashlib.sha256(payload).hexdigest(),
    ])

    to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        stamp,
        scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    key = f"AWS4{secret_key}".encode()
    for part in (day, REGION, SERVICE, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()

    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope},"
        f"SignedHeaders={signed_headers},Signature={signature}"
    )


def _explain(status: int, answer: str) -> AdapterError:
    """Turn Route 53's XML error into one of ours."""
    code = message = ""
    try:
        root = ElementTree.fromstring(answer)
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "Code":
                code = (element.text or "").strip()
            elif tag == "Message":
                message = (element.text or "").strip()
    except ElementTree.ParseError:
        message = answer[:200]

    detail = f"{code}: {message}".strip(": ")

    if code in ("InvalidClientTokenId", "SignatureDoesNotMatch", "AccessDenied"):
        return AdapterError("auth", "AWS hat die Zugangsdaten abgelehnt.", detail=detail)
    if code == "NoSuchHostedZone":
        return AdapterError(
            "not_found",
            "Diese Hosted-Zone-ID gibt es nicht. Sie steht in der Route-53-Konsole "
            "und sieht aus wie Z1D633PJN98FT9.",
            detail=detail,
        )
    if code == "Throttling" or status == 429:
        return AdapterError("rate_limit", "AWS drosselt gerade.", detail=detail)
    return AdapterError(
        "provider_response", f"AWS hat mit HTTP {status} geantwortet.", detail=detail or None
    )
