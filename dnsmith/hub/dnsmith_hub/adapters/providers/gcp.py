"""Google Cloud DNS.

The one provider that needed a new dependency. Google does not accept a
credential directly: the service-account key signs a short-lived JWT, that
JWT is exchanged for an access token, and the token authorises the call.
The signature is RS256 — RSA — which the standard library cannot do, so
`cryptography` is in requirements.txt for this module and nothing else.

Writing RSA by hand was the alternative and it was declined deliberately.
HMAC chains, as Route 53 and Aliyun need, are arithmetic anyone can check;
parsing a private key and padding a signature is not the place to save four
megabytes.

The token is kept until shortly before it expires. A scheduler pass that
updates six Google records should not fetch six tokens.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
from typing import Any

from ..base import AdapterError
from .support import Api, Context, succeeded

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://dns.googleapis.com/dns/v1"

# The narrowest scope that can still write a record. The wider
# cloud-platform scopes would also work and would let this add-on do a great
# deal more than change a DNS record.
SCOPE = "https://www.googleapis.com/auth/ndev.clouddns.readwrite"

TOKEN_LIFETIME = 3600
# Renew a minute early rather than discover expiry through a 401.
TOKEN_MARGIN = 60

DEFAULT_TTL = 300

# Tokens by service-account e-mail, shared across records and passes.
_tokens: dict[str, tuple[str, float]] = {}


def update(api: Api, values: dict[str, Any], ctx: Context, *, now=None):
    credentials = _credentials(values)
    token = _access_token(api, credentials, now=now)

    api = api.with_headers(
        Authorization=f"Bearer {token}",
        **{"Content-Type": "application/json", "Accept": "application/json"},
    )

    # Google names records absolutely, with the trailing dot.
    fqdn = f"{ctx.hostname}."
    base = (f"{API}/projects/{urllib.parse.quote(values['project'], safe='')}"
            f"/managedZones/{urllib.parse.quote(values['zone'], safe='')}/rrsets")
    single = f"{base}/{urllib.parse.quote(fqdn, safe='')}/{ctx.rrtype}"
    query = {"alt": "json", "prettyPrint": "false"}

    status, body = api.call(single, params=query)

    if status == 404:
        _check(api.call(base, method="POST", params=query, json_body={
            "name": fqdn, "type": ctx.rrtype, "ttl": DEFAULT_TTL, "rrdatas": [ctx.ip],
        }))
        return succeeded("Der Eintrag wurde beim Anbieter angelegt.")

    _check((status, body))

    existing = json.loads(body) if body.strip() else {}
    if existing.get("rrdatas") == [ctx.ip]:
        return succeeded("Der Eintrag war bereits aktuell.")

    _check(api.call(single, method="PATCH", params=query, json_body={
        "name": fqdn, "type": ctx.rrtype,
        "ttl": existing.get("ttl") or DEFAULT_TTL,
        "rrdatas": [ctx.ip],
    }))
    return succeeded()


def _credentials(values: dict[str, Any]) -> dict[str, str]:
    """The service-account JSON, as the user pasted it."""
    raw = values.get("credentials") or ""
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise AdapterError(
            "config",
            "Die Zugangsdaten sind keine gültige JSON-Datei. Erwartet wird der "
            "Inhalt der Schlüsseldatei eines Dienstkontos, so wie Google sie "
            "herunterlädt.",
        ) from error

    missing = [key for key in ("client_email", "private_key") if not parsed.get(key)]
    if missing:
        raise AdapterError(
            "config",
            f"In den Zugangsdaten fehlt {', '.join(missing)}. Das sieht nicht nach "
            f"dem Schlüssel eines Dienstkontos aus.",
        )
    return parsed


def _access_token(api: Api, credentials: dict[str, str], *, now=None) -> str:
    account = credentials["client_email"]
    moment = now if now is not None else time.time()

    cached = _tokens.get(account)
    if cached and cached[1] - TOKEN_MARGIN > moment:
        return cached[0]

    assertion = _signed_assertion(credentials, moment)
    status, body = api.call(
        TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        form_body={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
    )

    if status != 200:
        detail = body[:200]
        if status in (400, 401):
            raise AdapterError(
                "auth",
                "Google hat den Schlüssel des Dienstkontos abgelehnt. Stimmt die "
                "Uhrzeit des Geräts, und ist der Schlüssel noch gültig?",
                detail=detail,
            )
        raise AdapterError("provider_response",
                           f"Google hat die Tokenanfrage mit HTTP {status} beantwortet.",
                           detail=detail)

    answer = json.loads(body)
    token = answer.get("access_token")
    if not token:
        raise AdapterError("provider_response", "Google hat kein Zugangstoken geliefert.",
                           detail=body[:200])

    _tokens[account] = (token, moment + int(answer.get("expires_in") or TOKEN_LIFETIME))
    return token


def _signed_assertion(credentials: dict[str, str], moment: float) -> str:
    """The JWT Google exchanges for a token.

    RS256 over base64url(header) + "." + base64url(claims), which is the one
    place this project needs asymmetric crypto.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    issued = int(moment)
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": credentials["client_email"],
        "scope": SCOPE,
        "aud": credentials.get("token_uri") or TOKEN_URL,
        "iat": issued,
        "exp": issued + TOKEN_LIFETIME,
    }
    signing_input = b".".join(_segment(part) for part in (header, claims))

    try:
        key = serialization.load_pem_private_key(
            credentials["private_key"].encode(), password=None
        )
    except Exception as error:  # noqa: BLE001 - any malformed key means the same thing
        raise AdapterError(
            "config",
            "Der private Schlüssel in den Zugangsdaten konnte nicht gelesen werden.",
            detail=str(error)[:200],
        ) from error

    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode()}.{_b64(signature)}"


def _segment(payload: dict) -> bytes:
    return _b64(json.dumps(payload, separators=(",", ":")).encode()).encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _check(answer: tuple[int, str]) -> None:
    status, body = answer
    if 200 <= status < 300:
        return

    message = body[:200]
    try:
        message = (json.loads(body).get("error") or {}).get("message") or message
    except ValueError:
        pass

    if status in (401, 403):
        raise AdapterError(
            "auth",
            "Google hat den Zugriff verweigert. Hat das Dienstkonto die Rolle "
            "„DNS-Administrator“ für dieses Projekt?",
            detail=message,
        )
    if status == 404:
        raise AdapterError("not_found",
                           "Google kennt dieses Projekt oder diese Zone nicht.",
                           detail=message)
    if status == 429:
        raise AdapterError("rate_limit", "Google drosselt gerade.", detail=message)
    raise AdapterError("provider_response",
                       f"Google hat mit HTTP {status} geantwortet.", detail=message)
