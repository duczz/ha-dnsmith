"""The data model DNSmith stores.

Two rules shape everything here.

Configuration and status are separate. Configuration is versioned, backed up
and exported; status is derived and thrown away. A backup that
carries status is wrong the moment it is restored.

Secrets are never part of a record. A record holds the *names* of the secret
fields it uses; the values live in the secret store. That way a record can be
logged, exported, diffed and sent to the frontend without a redaction step
that somebody will one day forget to apply.
"""

from __future__ import annotations

import enum
import hashlib
import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIG_VERSION = 3

# A record ID is 16 hex characters, see derive_record_id().
RECORD_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")


class IPVersion(str, enum.Enum):
    """Which address families a record maintains.

    DUAL_STACK keeps both families in one record; the updater makes one call
    per family where the provider cannot take both at once.
    """

    IPV4 = "ipv4"
    IPV6 = "ipv6"
    IPV4_OR_IPV6 = "ipv4_or_ipv6"
    DUAL_STACK = "dual_stack"

    @property
    def engine_versions(self) -> list[str]:
        """The single-family ip_version values this record covers."""
        if self is IPVersion.DUAL_STACK:
            return ["ipv4", "ipv6"]
        if self is IPVersion.IPV4_OR_IPV6:
            return ["ipv4 or ipv6"]
        return [self.value]

    @property
    def wants_ipv4(self) -> bool:
        return self in (IPVersion.IPV4, IPVersion.IPV4_OR_IPV6, IPVersion.DUAL_STACK)

    @property
    def wants_ipv6(self) -> bool:
        return self in (IPVersion.IPV6, IPVersion.IPV4_OR_IPV6, IPVersion.DUAL_STACK)


class IPSourceMode(str, enum.Enum):
    """The ways DNSmith can learn an address.

    Four, not five. PREFIX_SUFFIX was in this list and in nothing else — no
    implementation, no interface, no test. A mode nobody can pick and nothing
    honours is not a feature, it is a note to self in a place where notes to
    self look like promises.
    """

    AUTO = "auto"
    HA_ENTITY = "ha_entity"
    STATIC = "static"
    DISABLED = "disabled"


class IPSource(BaseModel):
    """Where a public address comes from.

    HA_ENTITY is the one that matters on Home Assistant: add-on containers
    often have no IPv6 route, while Home Assistant already knows the external
    address from the router integration. Asking it beats asking the internet.
    """

    model_config = ConfigDict(extra="forbid")

    mode: IPSourceMode = IPSourceMode.AUTO
    entity_id: str | None = None
    value: str | None = None

    @field_validator("entity_id")
    @classmethod
    def _entity_id_shape(cls, value: str | None) -> str | None:
        if value is not None and "." not in value:
            raise ValueError("an entity ID looks like sensor.something")
        return value


class GlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval: str = "5m"
    update_cooldown: str = "5m"
    ip_source_v4: IPSource = Field(default_factory=IPSource)
    ip_source_v6: IPSource = Field(default_factory=IPSource)


class Record(BaseModel):
    """One DNS name DNSmith keeps current.

    `fields` holds plain values only. Secret values live in the secret store
    under this record's ID; `secret_fields` says which field IDs those are, so
    the UI can show "set" without the value ever leaving the store.
    """

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(pattern=RECORD_ID_PATTERN.pattern)]
    provider_id: str
    label: str = ""
    domain: str
    owner: str = "@"
    ip_version: IPVersion = IPVersion.IPV4_OR_IPV6
    ipv6_suffix: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    secret_fields: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def fqdn(self) -> str:
        return build_fqdn(self.owner, self.domain)

    @property
    def display_name(self) -> str:
        return self.label or self.fqdn


class DnsmithConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: int = CONFIG_VERSION
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    records: list[Record] = Field(default_factory=list)


def build_fqdn(owner: str, domain: str) -> str:
    """Join owner and domain into the record's hostname.

    "@" and an empty owner both mean the zone apex. Everything that shows or
    sends a hostname goes through here, so the UI and Home Assistant agree.
    """
    owner = (owner or "").strip()
    domain = (domain or "").strip().rstrip(".")
    if owner in ("", "@"):
        return domain
    return f"{owner}.{domain}"


def derive_record_id(
    provider_id: str,
    domain: str,
    owner: str,
    ip_version: str,
    ipv6_suffix: str | None = None,
) -> str:
    """Derive the record's stable ID.

    The ID is computed when a record is created and stored with it. It also
    decides whether a new entry duplicates an existing one, so this function
    should stay exactly as it is — same normalisation, same length-prefixed
    encoding, same digest — or an entry that already exists would no longer
    be recognised as a duplicate.

    tests/test_hub.py pins the exact values.
    """
    parts = [
        "v1",
        _normalise(provider_id),
        _normalise_host(domain),
        _normalise_host(owner),
        _normalise(ip_version),
        _normalise(ipv6_suffix or ""),
    ]

    digest = hashlib.sha256()
    for part in parts:
        # Length-prefixed: a plain separator would let "a|b" + "c" collide
        # with "a" + "b|c".
        #
        # The length is in BYTES, not characters. len() on a Python str
        # counts characters, so anything outside ASCII — an internationalised
        # domain that was not punycoded — would otherwise get a different ID
        # than the one already stored for it.
        encoded = part.encode("utf-8")
        digest.update(f"{len(encoded)}:".encode("ascii") + encoded + b"|")

    return digest.hexdigest()[:16]


def _normalise(value: str) -> str:
    return (value or "").strip().lower()


def _normalise_host(value: str) -> str:
    return _normalise(value).rstrip(".")
