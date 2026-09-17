"""Guard for URLs the user supplies and DNSmith then fetches.

The custom HTTP provider lets a user type a URL that this process calls. That
is the textbook shape of a server-side request forgery, and this server sits
inside a home network next to a Home Assistant instance, a router admin page
and whatever else the user runs. Upstream's own custom provider checks only
that the scheme is https, which stops nothing.

What this module does, in order:

1. Rejects anything that is not https (http only on explicit opt-in).
2. Rejects credentials embedded in the URL — they end up in logs.
3. Resolves the host and rejects the request if ANY returned address is not
   publicly routable. Checking only the first would let a round-robin record
   alternate between a public and a private address.
4. Hands back the address it approved, so the caller connects to THAT and not
   to a second resolution that could answer differently (DNS rebinding).

The caller is responsible for using `pinned_addresses` and for refusing
cross-host redirects; see adapters/native.py.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# 169.254.169.254 is link-local, so it is already covered — but cloud metadata
# is the single most valuable SSRF target, so it is named explicitly to make
# the intent obvious to anyone reading or changing this.
METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)

# Carrier-grade NAT. Not "private" in every Python version, and a plausible
# address for a router the user should not be able to reach this way.
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


class URLRejected(Exception):
    """A URL was refused. `code` is stable; `message` is shown to the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GuardedURL:
    url: str
    scheme: str
    host: str
    port: int
    pinned_addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...] = field(
        default_factory=tuple
    )

    @property
    def pinned_address(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        return self.pinned_addresses[0]


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether an address may be contacted on the user's behalf.

    Deliberately conservative: everything that is not unambiguously public
    internet is refused. A false refusal is an error message; a false accept
    is a door into the home network.
    """
    # An IPv4 address tunnelled through IPv6 must be judged as the IPv4 it is,
    # or ::ffff:192.168.1.1 would sail through.
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return is_public_address(address.ipv4_mapped)
        if address.sixtofour is not None:
            return is_public_address(address.sixtofour)
        if address.teredo is not None:
            # (server, client) — the client side is the interesting one.
            return is_public_address(address.teredo[1])

    if address in METADATA_ADDRESSES:
        return False
    if address.version == 4 and address in CGNAT_NETWORK:
        return False

    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False

    # is_global is the authoritative check where it exists; the explicit tests
    # above are there because its coverage has varied between versions.
    return bool(getattr(address, "is_global", True))


def check_url(
    raw: str,
    *,
    allow_http: bool = False,
    resolve: bool = True,
    resolver=None,
) -> GuardedURL:
    """Validate a user-supplied URL, or raise URLRejected.

    `resolve=False` skips the DNS step, for validating a form field without
    touching the network. It is NOT safe on its own — the address check is
    what stops the request, so anything that will actually be fetched must be
    checked with resolution on.
    """
    raw = (raw or "").strip()
    if not raw:
        raise URLRejected("url_missing", "Es wurde keine URL angegeben.")

    try:
        parsed = urlsplit(raw)
    except ValueError as error:
        raise URLRejected("url_malformed", f"Die URL ist ungültig: {error}") from error

    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme not in allowed_schemes:
        raise URLRejected(
            "scheme_not_allowed",
            "Die URL muss mit https:// beginnen. "
            "Unverschlüsselte Aufrufe übertragen die Zugangsdaten im Klartext.",
        )

    if parsed.username or parsed.password:
        raise URLRejected(
            "credentials_in_url",
            "Zugangsdaten dürfen nicht in der URL stehen — sie landen dort in Logs "
            "und Fehlermeldungen. Trage sie stattdessen in die Felder für "
            "Benutzername und Passwort ein.",
        )

    host = parsed.hostname
    if not host:
        raise URLRejected("host_missing", "Die URL enthält keinen Hostnamen.")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise URLRejected("port_invalid", "Die Portangabe in der URL ist ungültig.") from error

    # A literal IP needs no lookup, and must be judged directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not is_public_address(literal):
            raise URLRejected("address_not_public", _not_public_message(str(literal)))
        return GuardedURL(url=raw, scheme=parsed.scheme, host=host, port=port,
                          pinned_addresses=(literal,))

    if not resolve:
        return GuardedURL(url=raw, scheme=parsed.scheme, host=host, port=port)

    addresses = _resolve(host, port, resolver)
    if not addresses:
        raise URLRejected(
            "host_unresolvable",
            f"Der Hostname {host} konnte nicht aufgelöst werden.",
        )

    # Every address must pass. One bad answer in a round-robin set is enough
    # to reach an internal host on a later attempt.
    for address in addresses:
        if not is_public_address(address):
            raise URLRejected("address_not_public", _not_public_message(str(address), host))

    return GuardedURL(
        url=raw, scheme=parsed.scheme, host=host, port=port, pinned_addresses=tuple(addresses)
    )


def _resolve(host: str, port: int, resolver) -> list:
    lookup = resolver or socket.getaddrinfo
    try:
        infos = lookup(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise URLRejected(
            "host_unresolvable", f"Der Hostname {host} konnte nicht aufgelöst werden."
        ) from error
    except OSError as error:  # pragma: no cover - platform dependent
        raise URLRejected("host_unresolvable", f"Auflösung von {host} fehlgeschlagen.") from error

    addresses = []
    for info in infos:
        sockaddr = info[4]
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:  # pragma: no cover - would mean a broken resolver
            continue
        if address not in addresses:
            addresses.append(address)
    return addresses


def _not_public_message(address: str, host: str | None = None) -> str:
    where = f"{host} zeigt auf {address}" if host else f"{address}"
    return (
        f"{where} — diese Adresse liegt im lokalen Netz oder ist reserviert. "
        "DNSmith ruft die URL selbst auf und darf dabei nicht als Sprungbrett "
        "ins eigene Netzwerk dienen."
    )
