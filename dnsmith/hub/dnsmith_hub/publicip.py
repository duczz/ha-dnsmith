"""Finding this connection's public addresses.

The Go engine used to do this. Without it the hub has to, and the job is
smaller than it looks: ask a service that echoes the address it sees, and
believe the first sane answer.

Two details matter more than the choice of service.

The address family is decided by the hostname, not by a flag. ``ipv4.…`` has
only an A record and ``ipv6.…`` only an AAAA, so the connection can only go
out over that family — which is precisely the question being asked. Asking a
dual-stack host and hoping is how a DS-Lite connection ends up reporting a
v4 address it cannot actually be reached on.

And a failure to find one family is not an error. A connection with no public
IPv4 is normal in 2026; the caller gets None and the notices in service.py
explain what that means.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
from dataclasses import dataclass

from .adapters.base import PublicIP
from .models import IPSourceMode

logger = logging.getLogger("dnsmith.hub")

# Several services, because any one of them can be down or start answering
# with an advertising page. They are tried in order and the first plausible
# answer wins.
IPV4_SERVICES = (
    "https://ipv4.icanhazip.com",
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
)
IPV6_SERVICES = (
    "https://ipv6.icanhazip.com",
    "https://api6.ipify.org",
)

TIMEOUT = 10.0
MAX_BYTES = 128

# How long an address is believed. Short enough that a reconnection is noticed
# within a cycle, long enough that ten records do not mean ten lookups.
CACHE_SECONDS = 120

CGNAT = ipaddress.ip_network("100.64.0.0/10")


@dataclass
class _Cached:
    value: PublicIP
    at: float


class PublicIPResolver:
    """Asks the echo services, and remembers the answer for a couple of minutes."""

    def __init__(
        self,
        *,
        ipv4_services: tuple[str, ...] = IPV4_SERVICES,
        ipv6_services: tuple[str, ...] = IPV6_SERVICES,
        transport=None,
        clock=time.monotonic,
    ) -> None:
        self._ipv4_services = ipv4_services
        self._ipv6_services = ipv6_services
        self._transport = transport
        self._clock = clock
        self._cache: _Cached | None = None

    def get(self, refresh: bool = False) -> PublicIP:
        if not refresh and self._cache and self._clock() - self._cache.at < CACHE_SECONDS:
            return self._cache.value

        ipv4, ipv4_source = self._first(self._ipv4_services, want_version=4)
        ipv6, ipv6_source = self._first(self._ipv6_services, want_version=6)

        value = PublicIP(
            ipv4=ipv4,
            ipv6=ipv6,
            ipv4_source=ipv4_source,
            ipv6_source=ipv6_source,
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._cache = _Cached(value, self._clock())
        return value

    def _first(self, services: tuple[str, ...], *, want_version: int) -> tuple[str | None, str | None]:
        for url in services:
            try:
                text = self._fetch(url)
            except Exception as error:  # noqa: BLE001 - any failure means "try the next one"
                logger.debug("public IP service %s unavailable: %s", url, error)
                continue

            address = _parse(text, want_version)
            if address:
                return address, url

        return None, None

    def _fetch(self, url: str) -> str:
        import httpx

        with httpx.Client(
            timeout=httpx.Timeout(TIMEOUT, connect=5.0),
            transport=self._transport,
            follow_redirects=False,
        ) as client:
            response = client.get(url, headers={"User-Agent": "DNSmith"})
        # TODO(security): unlike TimeoutException/TransportError, str() on an
        # httpx.HTTPStatusError includes the full request URL with its query
        # string, and _first() above logs that error text via %s. Harmless
        # today because IPV4_SERVICES/IPV6_SERVICES are fixed, query-free
        # URLs - but if these services ever become user-configurable, a
        # credential in that URL would reach the log unredacted (the value
        # redactor only catches known secrets, and these are not among them).
        response.raise_for_status()
        return response.content[:MAX_BYTES].decode("utf-8", errors="replace")


def _parse(text: str, want_version: int) -> str | None:
    """Accept an address only if it is public and of the family we asked for.

    A service answering an error page, a private address, or the wrong family
    is a service that has stopped being useful for this question.
    """
    candidate = (text or "").strip().split()[0] if (text or "").strip() else ""
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None

    if address.version != want_version:
        return None

    # CGNAT has to pass. is_global() says no — correctly, it is not globally
    # reachable — but it IS the address the provider gave this connection, and
    # DNS updates with it succeed. Rejecting it here would leave the user with
    # "no address found" instead of the CGNAT notice in service.py, which is
    # the one message that actually explains their situation.
    if address in CGNAT:
        return str(address)

    if address.is_private or address.is_loopback or address.is_link_local:
        return None
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        return None
    return str(address)


# ---------------------------------------------------------------------------
# Where an address may come from
#
# Asking the internet is the obvious way and the wrong one often enough to
# matter. An add-on container frequently has no IPv6 route at all, while Home
# Assistant already knows the external address from the router integration —
# a DS-Lite connection, common with German ISPs, is exactly that case. The
# interface offered this as a hint long before anything implemented it; this
# is the part that makes the hint true.
# ---------------------------------------------------------------------------


class SupervisorUnavailable(Exception):
    """Home Assistant could not be asked."""


class SupervisorClient:
    """Reads entity states through the Supervisor's proxy to Home Assistant.

    Deliberately not routed through the SSRF guard: the host is a fixed
    internal name the container is given, not something a user typed, and the
    guard exists to refuse exactly such addresses. What IS user input is the
    entity ID, so it is quoted into the path rather than pasted.
    """

    BASE = "http://supervisor/core/api"

    def __init__(self, token: str | None = None, *, base: str | None = None,
                 transport=None) -> None:
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
        self._base = base or self.BASE
        self._transport = transport

    @property
    def available(self) -> bool:
        """Whether there is a token to authenticate with at all.

        Without one the add-on is running outside Home Assistant — during
        development, say — and the entity modes cannot work. Saying so beats
        a connection error.
        """
        return bool(self._token)

    def state(self, entity_id: str) -> str:
        import httpx
        import urllib.parse

        if not self.available:
            raise SupervisorUnavailable(
                "Kein Supervisor-Zugang. Läuft DNSmith außerhalb von Home Assistant?"
            )

        url = f"{self._base}/states/{urllib.parse.quote(entity_id, safe='')}"
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0),
                              transport=self._transport) as client:
                response = client.get(
                    url, headers={"Authorization": f"Bearer {self._token}"}
                )
        except Exception as error:  # noqa: BLE001 - every failure means "cannot ask"
            raise SupervisorUnavailable(f"Home Assistant war nicht erreichbar: {error}") from error

        if response.status_code == 404:
            raise SupervisorUnavailable(f"Die Entität {entity_id} gibt es nicht.")
        if response.status_code != 200:
            raise SupervisorUnavailable(
                f"Home Assistant hat mit HTTP {response.status_code} geantwortet."
            )

        state = (response.json() or {}).get("state")
        if state in (None, "", "unknown", "unavailable"):
            raise SupervisorUnavailable(
                f"Die Entität {entity_id} hat gerade keinen Wert ({state or 'leer'})."
            )
        return str(state)


class AddressSources:
    """Resolves both families according to the configured sources."""

    def __init__(self, *, http: "PublicIPResolver | None" = None,
                 supervisor: SupervisorClient | None = None) -> None:
        self.http = http or PublicIPResolver()
        self.supervisor = supervisor or SupervisorClient()

    def get(self, settings, refresh: bool = False) -> PublicIP:
        # The HTTP lookup is made once and only if some family actually wants
        # it: a setup that reads both families from entities should not be
        # reaching out to the internet at all.
        wants_http = any(
            getattr(settings, name).mode == IPSourceMode.AUTO
            for name in ("ip_source_v4", "ip_source_v6")
        )
        automatic = self.http.get(refresh) if wants_http else PublicIP()

        ipv4, ipv4_source, ipv4_error = self._family(
            settings.ip_source_v4, 4, automatic.ipv4, automatic.ipv4_source)
        ipv6, ipv6_source, ipv6_error = self._family(
            settings.ip_source_v6, 6, automatic.ipv6, automatic.ipv6_source)

        return PublicIP(
            ipv4=ipv4, ipv6=ipv6,
            ipv4_source=ipv4_source, ipv6_source=ipv6_source,
            ipv4_error=ipv4_error, ipv6_error=ipv6_error,
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _family(self, source, version: int, automatic: str | None,
                automatic_source: str | None) -> tuple[str | None, str | None, str | None]:
        mode = source.mode

        if mode == IPSourceMode.DISABLED:
            return None, None, None

        if mode == IPSourceMode.AUTO:
            return automatic, automatic_source, None

        if mode == IPSourceMode.STATIC:
            address = _parse(source.value or "", version)
            if address:
                return address, "fest eingetragen", None
            return None, None, (
                f"Die fest eingetragene IPv{version}-Adresse ist keine gültige "
                f"öffentliche Adresse."
            )

        if mode == IPSourceMode.HA_ENTITY:
            entity_id = source.entity_id or ""
            if not entity_id:
                return None, None, f"Für IPv{version} ist keine Entität angegeben."
            try:
                raw = self.supervisor.state(entity_id)
            except SupervisorUnavailable as error:
                return None, None, str(error)

            address = _parse(raw, version)
            if address:
                return address, entity_id, None
            return None, None, (
                f"Die Entität {entity_id} liefert „{raw[:60]}“ — das ist keine "
                f"gültige öffentliche IPv{version}-Adresse."
            )

        return None, None, f"Unbekannte Adressquelle: {mode}"
