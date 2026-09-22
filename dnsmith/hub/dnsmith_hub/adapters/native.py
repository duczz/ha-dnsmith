"""DNSmith's own updater.

Two things live here. The first is the pair of providers the user configures
themselves: generic DynDNS2, where they supply the update URL and the
parameter names, and the configurable HTTP provider. The second is the
declarative executor, which performs the update for every provider whose
manifest carries a ``request`` block — that is, for most of the catalogue.

The executor is the point of the rewrite. A provider that fits it is a piece
of YAML and nothing else: no module, no registration, no Python at all. Only
providers that need more than one call, or a signature, get their own adapter
under ``adapters/providers/``.

Every request made here goes through the SSRF guard. The URL template comes
from a manifest and is trusted; the values filled into it come from the user
and are not, so path segments are quoted, header values are refused if they
try to carry a newline, and the guard resolves and pins the address before a
connection is made.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .. import ssrf
from .base import AdapterError, ProbeResult

# DynDNS2's response vocabulary. The protocol answers in plain words on a
# 200, so the status code alone says nothing.
DYNDNS2_RESPONSES: dict[str, tuple[bool, str, str]] = {
    "good": (True, "success", "Der Eintrag wurde aktualisiert."),
    "nochg": (True, "up_to_date", "Der Eintrag war bereits aktuell."),
    "badauth": (False, "auth", "Benutzername oder Passwort wurden abgelehnt."),
    "badagent": (False, "banned", "Der Anbieter hat diesen Client blockiert."),
    "!donator": (False, "account", "Diese Funktion ist im gewählten Tarif nicht enthalten."),
    "notfqdn": (False, "config", "Der Hostname ist nicht vollständig qualifiziert."),
    "nohost": (False, "not_found", "Diesen Hostnamen gibt es beim Anbieter nicht."),
    "numhost": (False, "config", "Es wurden zu viele Hostnamen auf einmal übermittelt."),
    "abuse": (False, "banned", "Der Anbieter hat den Zugang wegen Missbrauchs gesperrt."),
    "dnserr": (False, "provider_response", "Beim Anbieter ist ein DNS-Fehler aufgetreten."),
    "911": (False, "provider_response", "Der Anbieter meldet eine Störung. Später erneut versuchen."),
}

MAX_RESPONSE_BYTES = 64 * 1024
REQUEST_TIMEOUT = 20.0


@dataclass(frozen=True)
class UpdateOutcome:
    ok: bool
    code: str
    message: str
    raw: str = ""


class HTTPCaller:
    """Makes the outbound request, pinned to an address the guard approved.

    Resolving once and connecting to that address is what closes the DNS
    rebinding hole: without it, a hostname could answer with a public address
    during validation and a private one a moment later, when the connection is
    actually made.
    """

    def __init__(self, *, transport=None, allow_http: bool = False) -> None:
        self._transport = transport
        self._allow_http = allow_http

    def call(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        json_body: Any = None,
        form_body: dict[str, str] | None = None,
        content: bytes | None = None,
        allow_http: bool | None = None,
    ) -> tuple[int, str]:
        import httpx

        guarded = ssrf.check_url(
            url, allow_http=self._allow_http if allow_http is None else allow_http
        )

        request_headers = dict(headers or {})
        request_headers.setdefault("User-Agent", "DNSmith")

        target = url
        extensions: dict[str, Any] = {}

        if guarded.pinned_addresses and self._transport is None:
            target = _url_with_address(url, guarded)
            request_headers["Host"] = _host_header(guarded)
            # Keep TLS validating against the real name, not the literal.
            extensions["sni_hostname"] = guarded.host

        try:
            with httpx.Client(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=5.0),
                transport=self._transport,
                # A redirect can point anywhere, including back inside the
                # network the guard just refused. The caller decides what to
                # do with a 3xx; it is never followed automatically.
                follow_redirects=False,
                verify=True,
            ) as client:
                response = client.request(
                    method.upper(),
                    target,
                    params=params,
                    headers=request_headers,
                    auth=auth,
                    json=json_body,
                    data=form_body,
                    # Raw bytes, for the one case where the body must go out
                    # byte for byte as it was: OVH signs the serialised body,
                    # and a re-encoding with different spacing would break the
                    # signature while looking identical.
                    content=content,
                    extensions=extensions or None,
                )
        except httpx.TimeoutException as error:
            raise AdapterError(
                "timeout", "Der Anbieter hat nicht rechtzeitig geantwortet.", detail=str(error)
            ) from error
        except httpx.TransportError as error:
            raise AdapterError(
                "network", "Der Anbieter war nicht erreichbar.", detail=str(error)
            ) from error

        if response.status_code in (301, 302, 303, 307, 308):
            raise AdapterError(
                "redirect_refused",
                "Der Anbieter hat auf eine andere Adresse weitergeleitet. "
                "DNSmith folgt Weiterleitungen nicht, weil das Ziel ungeprüft wäre. "
                "Trage die endgültige Update-URL direkt ein.",
            )

        body = response.content[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
        return response.status_code, body


def _url_with_address(url: str, guarded: ssrf.GuardedURL) -> str:
    address = guarded.pinned_address
    literal = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    # Swap only the host part; path, query and fragment are untouched.
    return re.sub(
        r"^(?P<scheme>https?://)(?P<authority>[^/?#]+)",
        lambda match: f"{match.group('scheme')}{literal}:{guarded.port}",
        url,
        count=1,
    )


def _host_header(guarded: ssrf.GuardedURL) -> str:
    default = 443 if guarded.scheme == "https" else 80
    if guarded.port == default:
        return guarded.host
    return f"{guarded.host}:{guarded.port}"


class NativeAdapter:
    """Updates records DNSmith handles itself."""

    name = "native"

    def __init__(self, caller: HTTPCaller | None = None) -> None:
        self._caller = caller or HTTPCaller()

    @property
    def caller(self) -> HTTPCaller:
        """The guarded HTTP client, for provider modules to borrow.

        They get this rather than making their own, so that the SSRF guard and
        the pinned address apply to them too.
        """
        return self._caller

    # -- DynDNS2 -----------------------------------------------------------

    def update_dyndns2(
        self,
        *,
        server: str,
        username: str,
        password: str,
        hostname: str,
        ipv4: str | None = None,
        ipv6: str | None = None,
        ipv4_parameter: str = "myip",
        ipv6_parameter: str = "myipv6",
        hostname_parameter: str = "hostname",
    ) -> UpdateOutcome:
        params = {hostname_parameter: hostname}

        if ipv4 and ipv4_parameter:
            params[ipv4_parameter] = ipv4
        if ipv6 and ipv6_parameter:
            params[ipv6_parameter] = ipv6

        if not ipv4 and not ipv6:
            raise AdapterError(
                "ip", "Es ist keine öffentliche IP-Adresse bekannt, die gesetzt werden könnte."
            )

        status, body = self._caller.call(server, params=params, auth=(username, password))
        return interpret_dyndns2(status, body)

    # -- Configurable HTTP -------------------------------------------------

    def update_custom_http(
        self,
        *,
        url: str,
        method: str = "GET",
        auth_mode: str = "none",
        auth_username: str = "",
        auth_password: str = "",
        auth_token: str = "",
        auth_query_name: str = "",
        auth_query_value: str = "",
        hostname: str = "",
        hostname_parameter: str = "hostname",
        ipv4: str | None = None,
        ipv6: str | None = None,
        ipv4_parameter: str = "myip",
        ipv6_parameter: str = "myipv6",
        success_mode: str = "status",
        success_regex: str = "",
    ) -> UpdateOutcome:
        params: dict[str, str] = {}
        headers: dict[str, str] = {}
        auth = None

        if hostname and hostname_parameter:
            params[hostname_parameter] = hostname
        if ipv4 and ipv4_parameter:
            params[ipv4_parameter] = ipv4
        if ipv6 and ipv6_parameter:
            params[ipv6_parameter] = ipv6

        if auth_mode == "basic":
            auth = (auth_username, auth_password)
        elif auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {auth_token}"
        elif auth_mode == "query":
            if not auth_query_name:
                raise AdapterError("config", "Für die Query-Authentifizierung fehlt der Parametername.")
            params[auth_query_name] = auth_query_value

        status, body = self._caller.call(
            url, method=method, params=params, headers=headers, auth=auth
        )

        return interpret_custom(status, body, success_mode, success_regex)

    # -- Manifest-driven providers ----------------------------------------

    def update_declarative(
        self,
        request: dict[str, Any],
        values: dict[str, Any],
        *,
        lookup: list[dict[str, Any]] | None = None,
        create: dict[str, Any] | None = None,
        bindings: dict[str, dict[str, Any]] | None = None,
        ipv4: str | None = None,
        ipv6: str | None = None,
        hostname: str = "",
        domain: str = "",
        owner: str = "",
    ) -> UpdateOutcome:
        """Perform the update a provider's manifest describes.

        `values` holds the form's field values, secrets resolved. The runtime
        values are added on top and win, so a provider cannot accidentally
        shadow {ipv4} with a field of its own.

        `bindings` derives extra values from the ones above — bunny.net names
        its record types 0 and 1 rather than A and AAAA, and a manifest should
        be able to say that without the executor learning about bunny.net.

        `lookup` runs first, for the many APIs that will not take a record by
        name: each step asks a question, binds the answer, and the next step
        or the update itself uses it. A step that finds nothing either fails
        or — for the step that looks for the record — hands over to `create`,
        which is how a record that does not exist yet comes into being.
        """
        if not ipv4 and not ipv6:
            raise AdapterError(
                "ip", "Es ist keine öffentliche IP-Adresse bekannt, die gesetzt werden könnte."
            )

        context: dict[str, Any] = dict(values)
        context.update({
            "ipv4": ipv4 or "",
            "ipv6": ipv6 or "",
            # Providers that take one address per call get the one this run is
            # about; IPv6 wins because a run that has it is an IPv6 run.
            "ip": ipv6 or ipv4 or "",
            # Variomedia puts the family in the host name — dyndns4. or
            # dyndns6. — and it will not be the last provider to do so.
            "ipversion": "6" if ipv6 else "4",
            # FreeDNS puts the family in a host prefix that is either "v6." or
            # nothing at all, which no number can express.
            "v6prefix": "v6." if ipv6 else "",
            # The DNS record type, for the many APIs that put it in the path
            # or the body.
            "rrtype": "AAAA" if ipv6 else "A",
            "hostname": hostname,
            "domain": domain,
            "zone": domain,
            "owner": owner,
            # The apex is "@" on the form and in most APIs, but a few want it
            # as an empty name instead.
            "subdomain": "" if owner in ("@", "") else owner,
        })

        for name, rule in (bindings or {}).items():
            source = str(context.get(rule["from"], ""))
            context[name] = rule["map"].get(source, rule.get("default", ""))

        spec = RequestSpec.from_manifest(request)

        for step in lookup or []:
            found = self._lookup(step, spec, context)
            # A 404 counts as "nothing bound" here just like an empty list
            # does: creating the record is still the right next move, and the
            # create call will say so itself if the zone is the problem.
            if found is None or found is NOT_FOUND_404:
                if step.get("on_missing") == "create":
                    if create is None:
                        raise AdapterError(
                            "config",
                            "Der Eintrag existiert beim Anbieter nicht und das Manifest "
                            "beschreibt nicht, wie er angelegt wird.",
                        )
                    spec = RequestSpec.from_manifest(create)
                    break
                # Which step came up empty matters: the first one usually
                # looks for the zone, and telling the user to create a record
                # when the domain is not in the account sends them the wrong way.
                raise AdapterError(
                    "not_found",
                    f"Der Anbieter kennt \"{step['into']}\" nicht. Prüfe, ob die Domain "
                    "in diesem Konto liegt und der Eintrag dort existiert.",
                )
            context[step["into"]] = found

        url = render(spec.url, context, quote=True)
        if PLACEHOLDER.search(spec.url) and not url.strip():
            raise AdapterError("config", "Die Update-Adresse dieses Anbieters ist unvollständig.")

        headers = _non_empty(spec.headers, context)
        auth = self._auth(spec, context, headers)
        params = _non_empty(spec.params, context)
        params.update(auth.pop("params", {}))

        _refuse_header_injection(headers)

        json_body = form_body = None
        if spec.body_type == "json":
            json_body = _render_deep(spec.body, context)
        elif spec.body_type == "form":
            form_body = _non_empty(spec.body or {}, context)

        status, body = self._caller.call(
            url,
            method=spec.method,
            params=params or None,
            headers=headers,
            auth=auth.get("basic"),
            json_body=json_body,
            form_body=form_body,
            allow_http=spec.allow_http,
        )
        return evaluate(spec, status, body)

    @staticmethod
    def _auth(spec: RequestSpec, context: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        """Turn the manifest's auth block into what the caller needs.

        Writes into `headers` for the header-shaped modes and returns the rest,
        so that a query credential never ends up in a header and the other way
        round.

        With several candidates, the first one whose values are all present
        wins. A provider that lists two is saying they are alternatives, so
        "none of them is filled in" is a credentials problem and says so,
        rather than sending an unauthenticated request and letting the
        provider phrase the error.
        """
        problems: list[str] = []

        for candidate in spec.auth:
            mode = candidate.get("mode", "none")

            if mode == "none":
                return {}

            if mode == "basic":
                username = render(candidate["username"], context)
                password = render(candidate["password"], context)
                if username and password:
                    return {"basic": (username, password)}
                problems.append("Benutzername und Passwort")
                continue

            if mode in ("bearer", "header"):
                template = candidate.get("format", "{token}")
                value = render(template, context)
                # An empty credential renders as "Bearer " — a header that is
                # worse than no header, because the provider answers with an
                # auth error the user cannot place.
                if value.strip() and value.strip() not in ("Bearer", "Token"):
                    headers[candidate.get("header", "Authorization")] = (
                        f"Bearer {value}" if mode == "bearer" else value
                    )
                    return {}
                problems.append("Token")
                continue

            if mode == "headers":
                # Cloudflare's legacy mode needs e-mail AND key; either alone
                # authenticates nothing, so they stand or fall together.
                rendered = {name: render(template, context)
                            for name, template in candidate["values"].items()}
                if all(rendered.values()):
                    headers.update(rendered)
                    return {}
                problems.append(" und ".join(candidate["values"]))
                continue

            if mode == "query":
                value = render(candidate["value"], context)
                if value:
                    return {"params": {candidate["param"]: value}}
                problems.append("Zugangsdaten in der Adresse")
                continue

            raise AdapterError("config", f"Unbekannte Authentifizierungsart: {mode!r}")

        raise AdapterError(
            "auth",
            "Es fehlen Zugangsdaten für diesen Anbieter ("
            + " oder ".join(dict.fromkeys(problems))
            + ").",
        )

    def _lookup(self, step: dict[str, Any], spec: RequestSpec, context: dict[str, Any]) -> Any:
        """Run one lookup step and return the value it binds, or None.

        Credentials are not repeated per step: unless the step says otherwise
        it authenticates exactly like the update does. Repeating them would be
        one more place for a manifest to be subtly wrong.
        """
        # The schema promises "the update's auth and headers are used unless
        # overridden here", so the update's headers are the base and the
        # step's win over them. Without this a lookup went out without the
        # Accept or Content-Type the same provider requires on the update.
        headers = _non_empty(spec.headers, context)
        headers.update(_non_empty(step.get("headers") or {}, context))
        auth = self._auth(spec, context, headers)
        params = _non_empty(step.get("params") or {}, context)
        params.update(auth.pop("params", {}))

        _refuse_header_injection(headers)

        json_body = form_body = None
        if step.get("body_type") == "json":
            json_body = _render_deep(step.get("body"), context)
        elif step.get("body_type") == "form":
            form_body = _non_empty(step.get("body") or {}, context)

        status, body = self._caller.call(
            render(step["url"], context, quote=True),
            method=step.get("method", "GET"),
            params=params or None,
            headers=headers,
            auth=auth.get("basic"),
            json_body=json_body,
            form_body=form_body,
            allow_http=spec.allow_http,
        )

        if status in (401, 403):
            raise AdapterError("auth", FAILURE_MESSAGES["auth"], detail=body[:200])
        if status == 404:
            return NOT_FOUND_404
        if not 200 <= status < 300:
            raise AdapterError(
                "provider_response",
                f"Der Anbieter hat die Abfrage mit HTTP {status} beantwortet.",
                detail=body[:200],
            )

        try:
            payload = json.loads(body)
        except ValueError as error:
            raise AdapterError(
                "provider_response",
                "Der Anbieter hat auf die Abfrage keine gültige JSON-Antwort geschickt.",
                detail=body[:200],
            ) from error

        return _select(payload, step["select"], context)

    # -- Probing -----------------------------------------------------------

    def probe(self, spec: dict[str, Any], mode: str = "validate") -> ProbeResult:
        """Check a native provider's settings.

        Validate mode makes no network request at all, DNS included. That is
        deliberate: this runs while the user is still typing in the form, and
        a temporary resolver problem must not be reported as "your settings
        are wrong". The URL is checked for everything that can be judged from
        the text — scheme, embedded credentials, a literal address inside the
        home network — and the settings are checked for completeness.

        Resolution and the address check happen in HTTPCaller before any real
        request, which is where they actually protect something.
        """
        started = time.monotonic()
        adapter = spec.get("adapter", "native")
        protocol = spec.get("protocol")
        request = spec.get("request")
        values = spec.get("values", {})
        allow_http = bool(values.get("allow_http"))

        try:
            if adapter == "unported":
                raise AdapterError(
                    "not_implemented",
                    "Dieser Anbieter ist in dieser Version noch nicht umgesetzt.",
                )
            if adapter == "python":
                raise AdapterError(
                    "not_implemented", "Für diesen Anbieter fehlt noch das Adapter-Modul."
                )

            # Settings first: a missing password is the user's problem to fix,
            # and reporting it beats a message about the URL they got right.
            if protocol == "dyndns2" and request is None:
                _require(values, ["server", "username", "password"])
                url = values.get("server", "")
            elif protocol == "custom_http":
                _require(values, ["url"])
                if values.get("success_mode") == "regex":
                    _compile_regex(values.get("success_regex", ""))
                url = values.get("url", "")
            elif request is not None:
                # A manifest-driven provider. The URL template is ours, so what
                # is worth checking is that the user's values fill it in: a
                # placeholder still standing after rendering means a field the
                # form has not collected.
                url = render(request["url"], {**values, **_PROBE_PLACEHOLDERS}, quote=True)
                # Names a lookup step or a binding will supply are not the
                # user's to fill in — checking for them here would report a
                # record ID as a missing form field.
                supplied = set(_PROBE_PLACEHOLDERS)
                supplied |= {step["into"] for step in spec.get("lookup") or []}
                supplied |= set(spec.get("bindings") or {})
                left = PLACEHOLDER.findall(request["url"])
                missing = [name.split("|")[0] for name in left
                           if not values.get(name.split("|")[0])
                           and name.split("|")[0] not in supplied]
                if missing:
                    raise AdapterError("config", f"Es fehlen Angaben: {', '.join(missing)}.")
                allow_http = bool(request.get("allow_http"))
            else:
                raise AdapterError("config", f"Unbekannter Provider-Typ: {protocol!r}")

            ssrf.check_url(url, allow_http=allow_http, resolve=False)

            if mode == "live" and spec.get("lookup"):
                # A lookup only reads. Running it is the one honest test
                # available before saving: it proves the credentials work and
                # the zone exists, and it changes nothing if they do not.
                return self._probe_lookup(spec, started)

        except ssrf.URLRejected as rejected:
            return ProbeResult(
                ok=False,
                mode=mode,
                duration_ms=_elapsed(started),
                error={"code": rejected.code, "summary": rejected.message},
            )
        except AdapterError as error:
            return ProbeResult(
                ok=False, mode=mode, duration_ms=_elapsed(started), error=error.as_dict()
            )

        return ProbeResult(
            ok=True,
            mode=mode,
            duration_ms=_elapsed(started),
            checked="settings",
            message=(
                "Die Angaben sind vollständig und die Adresse ist zulässig. "
                "Ob der Anbieter sie annimmt, zeigt sich beim ersten Update — "
                "ein echter Testlauf würde hier bereits einen Eintrag schreiben."
            ),
        )

    def _probe_lookup(self, spec: dict[str, Any], started: float) -> ProbeResult:
        """Walk the lookup chain for real and report what it found.

        A step that finds nothing is not necessarily a failure: for the step
        that looks for the record, "not there yet" is the normal state before
        the first update, and saying so is more useful than a red cross.
        """
        values = spec.get("values", {})
        context: dict[str, Any] = {**_PROBE_PLACEHOLDERS, **values}
        context.update({key: value for key, value in spec.get("context", {}).items() if value})

        for name, rule in (spec.get("bindings") or {}).items():
            context[name] = rule["map"].get(str(context.get(rule["from"], "")), rule.get("default", ""))

        request = RequestSpec.from_manifest(spec["request"])

        try:
            for step in spec["lookup"]:
                found = self._lookup(step, request, context)
                if found is None or found is NOT_FOUND_404:
                    if step.get("on_missing") == "create" and found is not NOT_FOUND_404:
                        return ProbeResult(
                            ok=True, mode="live", duration_ms=_elapsed(started),
                            checked="credentials",
                            message=("Zugangsdaten und Zone stimmen. Den Eintrag gibt es beim "
                                     "Anbieter noch nicht — DNSmith legt ihn beim ersten "
                                     "Update an."),
                        )
                    if found is NOT_FOUND_404:
                        return ProbeResult(
                            ok=False, mode="live", duration_ms=_elapsed(started),
                            checked="credentials",
                            error={"code": "not_found",
                                   "summary": f"Der Anbieter kennt \"{step['into']}\" nicht "
                                              "(HTTP 404). Meist liegt die Domain nicht in "
                                              "diesem Konto oder die Zonen-Angabe stimmt nicht."},
                        )
                    return ProbeResult(
                        ok=False, mode="live", duration_ms=_elapsed(started),
                        checked="credentials",
                        error={"code": "not_found",
                               "summary": "Zugangsdaten stimmen, aber der gesuchte Eintrag "
                                          "wurde beim Anbieter nicht gefunden."},
                    )
                context[step["into"]] = found
        except AdapterError as error:
            return ProbeResult(ok=False, mode="live", duration_ms=_elapsed(started),
                               checked="credentials", error=error.as_dict())

        return ProbeResult(
            ok=True, mode="live", duration_ms=_elapsed(started), checked="credentials",
            message="Zugangsdaten stimmen und der Eintrag wurde beim Anbieter gefunden.",
        )


# Stand-ins for the runtime values during a probe. Nothing is sent, so they
# only need to keep the URL well formed.
_PROBE_PLACEHOLDERS = {
    "domain": "example.com",
    "zone": "example.com",
    "owner": "host",
    "hostname": "host.example.com",
    "ip": "203.0.113.7",
    "ipv4": "203.0.113.7",
    "ipv6": "2001:db8::1",
    "ipversion": "4",
    "v6prefix": "",
    "rrtype": "A",
    "subdomain": "host",
}


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _require(values: dict[str, Any], names: list[str]) -> None:
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise AdapterError("config", f"Es fehlen Angaben: {', '.join(missing)}.")


def _compile_regex(pattern: str):
    """Compile a success pattern, case-insensitively.

    Case-insensitive because the alternative was a trap nobody could see. The
    sibling rule, body_contains, has always matched against a lowercased body,
    so a manifest author reasonably expects the same here - and freedns proved
    what happens otherwise: its pattern read "^(updated |no ip change
    detected)", the service answers "Updated ...", and every successful update
    was reported as a failure. Nothing in a provider's answer is meaningfully
    case-sensitive, and a rule that silently never matches is worse than one
    that matches a little too eagerly.
    """
    if not pattern:
        raise AdapterError("config", "Es wurde kein Erfolgsmuster angegeben.")
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as error:
        raise AdapterError(
            "config", f"Das Erfolgsmuster ist kein gültiger regulärer Ausdruck: {error}"
        ) from error


def interpret_dyndns2(status: int, body: str) -> UpdateOutcome:
    """Turn a DynDNS2 response into an outcome.

    The protocol answers with a keyword on an HTTP 200, so the body is what
    matters. A 401 still has to be handled, because several providers answer
    that way instead of sending `badauth`.
    """
    text = (body or "").strip()
    first = text.split()[0].lower() if text.split() else ""

    if first in DYNDNS2_RESPONSES:
        ok, code, message = DYNDNS2_RESPONSES[first]
        return UpdateOutcome(ok=ok, code=code, message=message, raw=text[:200])

    if status == 401:
        return UpdateOutcome(
            ok=False,
            code="auth",
            message="Benutzername oder Passwort wurden abgelehnt.",
            raw=text[:200],
        )
    if status == 429:
        return UpdateOutcome(
            ok=False,
            code="rate_limit",
            message="Der Anbieter hat zu viele Anfragen erhalten.",
            raw=text[:200],
        )
    if status >= 500:
        return UpdateOutcome(
            ok=False,
            code="provider_response",
            message="Der Anbieter meldet einen Serverfehler.",
            raw=text[:200],
        )
    if status >= 400:
        return UpdateOutcome(
            ok=False,
            code="provider_response",
            message=f"Der Anbieter hat die Anfrage mit HTTP {status} abgelehnt.",
            raw=text[:200],
        )

    return UpdateOutcome(
        ok=False,
        code="unknown",
        message="Die Antwort des Anbieters war nicht zu deuten.",
        raw=text[:200],
    )


def interpret_custom(
    status: int, body: str, success_mode: str, success_regex: str
) -> UpdateOutcome:
    text = (body or "").strip()

    if success_mode == "regex":
        pattern = _compile_regex(success_regex)
        if pattern.search(text):
            return UpdateOutcome(True, "success", "Der Eintrag wurde aktualisiert.", text[:200])
        return UpdateOutcome(
            False,
            "provider_response",
            "Die Antwort des Anbieters enthielt das erwartete Erfolgsmuster nicht.",
            text[:200],
        )

    if 200 <= status < 300:
        return UpdateOutcome(True, "success", "Der Eintrag wurde aktualisiert.", text[:200])
    if status == 401 or status == 403:
        return UpdateOutcome(False, "auth", "Die Zugangsdaten wurden abgelehnt.", text[:200])
    if status == 429:
        return UpdateOutcome(
            False, "rate_limit", "Der Anbieter hat zu viele Anfragen erhalten.", text[:200]
        )
    return UpdateOutcome(
        False,
        "provider_response",
        f"Der Anbieter hat mit HTTP {status} geantwortet.",
        text[:200],
    )


# ---------------------------------------------------------------------------
# The declarative executor.
#
# A provider whose manifest carries a "request" block needs no code. This is
# what runs that block. Everything it knows about a provider arrives as data;
# nothing here may grow a branch named after a company.
# ---------------------------------------------------------------------------

# A placeholder is a chain: {ipv6|'preserve'} means "the IPv6 address, or the
# literal preserve if there is none", and {username|hostname} means "the
# username field, or the host name". Two providers need it and neither is an
# exotic case: deSEC clears the other family's record unless it is told to
# preserve it, and spDYN's token mode puts the host name where the user name
# goes. A literal is quoted so that a mistyped field name is a mistyped field
# name rather than silently becoming text.
PLACEHOLDER = re.compile(r"\{([a-z0-9_]+(?:\|(?:[a-z0-9_]+|'[^'{}|]*'))*)\}")

# Values the updater supplies rather than the form. Kept in step with
# RUNTIME_VALUES in tools/manifest_merge.py, which refuses a manifest naming
# anything outside this set.
# Values the updater supplies. The four family-dependent ones - ip,
# ipversion, v6prefix and rrtype - are also what tells the scheduler that a
# provider has to be called once per address family.
RUNTIME_KEYS = (
    "ip", "ipv4", "ipv6", "ipversion", "v6prefix", "rrtype",
    "hostname", "domain", "owner", "subdomain", "zone",
)

# A request whose shape depends on which family is being updated cannot carry
# both at once: the record type, the host name or the single address
# parameter would have to be two things.
FAMILY_DEPENDENT = frozenset({"ip", "ipversion", "v6prefix", "rrtype"})

DEFAULT_SUCCESS_STATUS = range(200, 300)


def _auth_candidates(block: Any) -> list[dict[str, Any]]:
    """Normalise the auth block into a list of candidates.

    A provider may accept several credential styles that are not variations of
    one request but different requests — Gigahost takes either a bearer token
    or the account's e-mail and password. Listing them lets the executor pick
    the one the user actually filled in, which is what the Go implementation
    did with an `if apiKey == ""`.
    """
    if not block:
        return [{"mode": "none"}]
    if isinstance(block, dict):
        return [block]
    return list(block)


@dataclass(frozen=True)
class RequestSpec:
    """One provider's update call, as the manifest describes it."""

    url: str
    method: str = "GET"
    allow_http: bool = False
    auth: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body_type: str = "none"
    body: Any = None
    success: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, block: dict[str, Any]) -> "RequestSpec":
        return cls(
            url=block["url"],
            method=block.get("method", "GET"),
            allow_http=bool(block.get("allow_http", False)),
            auth=_auth_candidates(block.get("auth")),
            params=block.get("params") or {},
            headers=block.get("headers") or {},
            body_type=block.get("body_type", "none"),
            body=block.get("body"),
            success=block.get("success") or {},
            failures=block.get("failures") or {},
        )


def render(template: str, values: dict[str, Any], *, quote: bool = False) -> str:
    """Fill {name} placeholders from values.

    An unknown or empty placeholder renders as an empty string rather than
    raising. That is deliberate: it lets the caller decide, per destination,
    whether "empty" means "drop this parameter" (usually) or "the request
    cannot be built" (the URL).
    """

    def replace(match: re.Match[str]) -> str:
        for part in match.group(1).split("|"):
            if part.startswith("'") and part.endswith("'"):
                text = part[1:-1]
            else:
                raw = values.get(part)
                if raw is None or raw is False:
                    continue
                text = str(raw)
            if text:
                return urllib.parse.quote(text, safe="") if quote else text
        return ""

    return PLACEHOLDER.sub(replace, template)


WHOLE_PLACEHOLDER = re.compile(r"^\{([a-z0-9_]+(?:\|(?:[a-z0-9_]+|'[^'{}|]*'))*)\}$")


def _render_deep(value: Any, values: dict[str, Any]) -> Any:
    """Fill in a JSON body, keeping types where the value is the whole field.

    A TTL is a number to most APIs and Cloudflare's "proxied" is a boolean;
    bunny.net numbers its record types. Rendering those through str() would
    send "300", "false" and "0", which an API is entitled to reject — and
    "false" is worse than rejected, because a non-empty string is truthy in
    several languages.

    An embedded placeholder is still text: "v{ipversion}-suffix" can only be
    a string.
    """
    if isinstance(value, str):
        whole = WHOLE_PLACEHOLDER.match(value)
        if whole:
            for part in whole.group(1).split("|"):
                if part.startswith("'"):
                    return part[1:-1]
                resolved = values.get(part)
                # Only "absent" falls through to the next candidate. False and
                # 0 are answers: Cloudflare's proxied flag is legitimately
                # false and bunny.net's A record is legitimately type 0, and
                # "x in (None, False, '')" would swallow both, because 0 == False.
                if resolved is None:
                    continue
                if isinstance(resolved, str) and not resolved:
                    continue
                return resolved
            return ""
        return render(value, values)
    if isinstance(value, dict):
        return {key: _render_deep(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_deep(item, values) for item in value]
    return value


def _non_empty(mapping: dict[str, str], values: dict[str, Any]) -> dict[str, str]:
    """Render a mapping and drop whatever came out empty.

    Sending "myip=" is not the same as not sending myip: several providers
    read the empty value as "clear this record".
    """
    rendered = {key: render(template, values) for key, template in mapping.items()}
    return {key: text for key, text in rendered.items() if text}


def _select(payload: Any, select: dict[str, Any], context: dict[str, Any]) -> Any:
    """Pick one value out of an answer.

    Matching is textual on purpose. An ID comes back as a number from one
    provider and as a string from the next, and a record name may or may not
    carry a trailing dot; comparing the rendered forms means the manifest does
    not have to know which.
    """
    where = {key: render(template, context)
             for key, template in (select.get("where") or {}).items()}
    take = select["take"]

    subject = _json_path(payload, select["path"]) if select.get("path") else payload

    if isinstance(subject, dict) and not where:
        return subject.get(take)

    for entry in subject if isinstance(subject, list) else []:
        if not isinstance(entry, dict):
            continue
        if all(_same(entry.get(key), wanted) for key, wanted in where.items()):
            return entry.get(take)

    return None


def _same(value: Any, wanted: str) -> bool:
    if value is None:
        return False
    return str(value).rstrip(".").lower() == wanted.rstrip(".").lower()


def _same_value(value: Any, expected: Any) -> bool:
    """Compare a value from a JSON answer against what the manifest expects.

    Booleans stay exact - true and "true" are not the same claim, and treating
    them alike is how a "proxied": false ends up read as true. Everything else
    is compared as text, because a provider is free to answer 300 or "300" for
    the same status code and both mean the update worked.
    """
    if isinstance(expected, bool) or isinstance(value, bool):
        return value is expected
    if value is None:
        return False
    return str(value) == str(expected)


class _NotFound404:
    """Distinguishes "the provider answered 404" from "the list was empty".

    Both mean "no value bound" to the update, which goes on to create the
    record. They mean very different things to the connection test: an empty
    list is the normal state before the first update, while a 404 usually says
    the zone or the account is not what the user thinks it is. Reporting that
    as "credentials and zone are fine" is the one answer a test button must
    never give.
    """

    def __bool__(self) -> bool:
        return False


NOT_FOUND_404 = _NotFound404()


def _contains_marker(haystack: str, marker: str) -> bool:
    """Does the answer carry this confirmation, as a word rather than a fragment?

    A plain substring test is too generous for the short markers providers
    like to use. "ok" occurs inside "token", so "Invalid token" read as a
    successful update; "no_error" would match inside a longer identifier the
    same way. Anchoring at word boundaries keeps the marker meaning what it
    says, while leaving markers that start or end in punctuation alone -
    "<status>ok" has no boundary to anchor to on its left.
    """
    marker = marker.lower()
    if not marker:
        return False
    pattern = re.escape(marker)
    if marker[0].isalnum() or marker[0] == "_":
        pattern = r"\b" + pattern
    if marker[-1].isalnum() or marker[-1] == "_":
        pattern = pattern + r"\b"
    return re.search(pattern, haystack) is not None


def _refuse_header_injection(headers: dict[str, str]) -> None:
    """A rendered header may not carry a line break.

    The values come from user input by way of a manifest placeholder, so this
    has to hold on every path that builds headers - the update and every
    lookup step alike.
    """
    for name, value in headers.items():
        if "\n" in value or "\r" in value:
            raise AdapterError(
                "config", f"Der Kopfzeilenwert für {name!r} enthält einen Zeilenumbruch.")


def _json_path(payload: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(payload, list):
            try:
                payload = payload[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(payload, dict):
            payload = payload.get(part)
        else:
            return None
    return payload


def evaluate(spec: RequestSpec, status: int, body: str) -> UpdateOutcome:
    """Decide what the provider's answer means.

    Order matters. The mapped failures are checked first, because a provider
    that answers "badauth" with an HTTP 200 would otherwise be reported as a
    success — which is exactly the trap DynDNS2 sets.
    """
    text = (body or "").strip()
    lowered = text.lower()

    for marker, code in spec.failures.items():
        if marker.lower() in lowered:
            return UpdateOutcome(False, code, FAILURE_MESSAGES.get(code, FAILURE_MESSAGES["unknown"]),
                                 text[:200])

    if spec.success.get("vocabulary") == "dyndns2":
        return interpret_dyndns2(status, text)

    rules = spec.success
    checked = False

    # The status is checked either way. It used to be skipped as soon as the
    # manifest carried any body rule, on the assumption that the body says
    # more than the code - but a gateway error page or a login form can carry
    # the success marker by accident, and then a failed update was reported as
    # a success, silently and for good. A body rule narrows success; it does
    # not widen it to codes the provider never meant as success.
    checked = True
    if "status" in rules:
        if status not in rules["status"]:
            return _http_failure(status, text)
    elif status not in DEFAULT_SUCCESS_STATUS:
        return _http_failure(status, text)

    if "body_contains" in rules:
        checked = True
        if not any(_contains_marker(lowered, marker) for marker in rules["body_contains"]):
            return UpdateOutcome(
                False, "provider_response",
                "Die Antwort des Anbieters enthielt keine der erwarteten Bestätigungen.", text[:200])

    if "body_regex" in rules:
        checked = True
        if not _compile_regex(rules["body_regex"]).search(text):
            return UpdateOutcome(
                False, "provider_response",
                "Die Antwort des Anbieters entsprach nicht dem erwarteten Muster.", text[:200])

    if "json_path_equals" in rules:
        checked = True
        try:
            payload = json.loads(text)
        except ValueError:
            return UpdateOutcome(
                False, "provider_response",
                "Der Anbieter hat keine gültige JSON-Antwort geschickt.", text[:200])
        for path, expected in rules["json_path_equals"].items():
            if not _same_value(_json_path(payload, path), expected):
                return UpdateOutcome(
                    False, "provider_response",
                    f"Der Anbieter meldet in \"{path}\" nicht den erwarteten Wert.", text[:200])

    if not checked:  # pragma: no cover - the schema forbids an empty rule set
        raise AdapterError("config", "Für diesen Provider ist kein Erfolgskriterium hinterlegt.")

    return UpdateOutcome(True, "success", "Der Eintrag wurde aktualisiert.", text[:200])


FAILURE_MESSAGES = {
    "auth": "Die Zugangsdaten wurden abgelehnt.",
    "account": "Diese Funktion ist im gewählten Tarif nicht enthalten.",
    "config": "Der Anbieter hat die Angaben als ungültig zurückgewiesen.",
    "not_found": "Den Eintrag gibt es beim Anbieter nicht.",
    "banned": "Der Anbieter hat den Zugang gesperrt.",
    "rate_limit": "Der Anbieter hat zu viele Anfragen erhalten.",
    "provider_response": "Der Anbieter hat die Aktualisierung abgelehnt.",
    "ip": "Der Anbieter hat die übermittelte IP-Adresse abgelehnt.",
    "unknown": "Die Antwort des Anbieters war nicht zu deuten.",
}


def _http_failure(status: int, text: str) -> UpdateOutcome:
    if status in (401, 403):
        return UpdateOutcome(False, "auth", FAILURE_MESSAGES["auth"], text[:200])
    if status == 404:
        return UpdateOutcome(False, "not_found", FAILURE_MESSAGES["not_found"], text[:200])
    if status == 429:
        return UpdateOutcome(False, "rate_limit", FAILURE_MESSAGES["rate_limit"], text[:200])
    if status >= 500:
        return UpdateOutcome(False, "provider_response",
                             "Der Anbieter meldet einen Serverfehler.", text[:200])
    return UpdateOutcome(False, "provider_response",
                         f"Der Anbieter hat mit HTTP {status} geantwortet.", text[:200])
