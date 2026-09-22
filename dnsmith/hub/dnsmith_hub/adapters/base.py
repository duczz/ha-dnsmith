"""The adapter boundary.

This interface is what keeps DNSmith from being a wrapper around one engine.
A provider's manifest names its adapter; nothing above this line knows whether
a record is updated by the Go engine, by DNSmith's own code, or one day by
something else entirely.

Concretely it buys three things:

- A provider upstream drops can be re-homed to the native adapter by editing
  one line of YAML.
- Generic DynDNS2 and the configurable HTTP provider, which the engine cannot
  express, are ordinary providers rather than special cases.
- An engine failure is confined: the hub keeps serving, the affected records
  report an error, the rest keep updating.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol


class UpdateState(str, enum.Enum):
    UNSET = "unset"
    UPDATING = "updating"
    SUCCESS = "success"
    UP_TO_DATE = "up_to_date"
    FAIL = "fail"
    DISABLED = "disabled"


@dataclass(frozen=True)
class RecordStatus:
    """What an adapter can say about one record right now.

    Deliberately not persisted. Status is rebuilt from the adapter on every
    poll; a backup that carried it would be wrong the moment it was restored.
    """

    record_id: str
    state: UpdateState = UpdateState.UNSET
    current_ipv4: str | None = None
    current_ipv6: str | None = None
    last_attempt: str | None = None
    last_success: str | None = None
    banned_until: str | None = None
    ip_change_count: int = 0
    previous_ips: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None

    @property
    def healthy(self) -> bool:
        return self.state in (UpdateState.SUCCESS, UpdateState.UP_TO_DATE)


@dataclass(frozen=True)
class ProbeResult:
    """What a check before saving found.

    `checked` matters as much as `ok`. A check that only read the form is not
    the same as one that asked the provider, and telling the user "der
    Anbieter ist erreichbar" after doing neither is how a test button loses
    its meaning.
    """

    ok: bool
    mode: str
    duration_ms: int = 0
    ip_used: str | None = None
    error: dict[str, Any] | None = None
    checked: str = "settings"          # "settings" or "credentials"
    message: str = ""


@dataclass(frozen=True)
class PublicIP:
    """The addresses this connection has, and where they came from.

    The per-family error matters as much as the address. "No IPv6 found" and
    "the entity you named does not exist" lead to completely different next
    steps, and only one of them is the user's mistake.
    """

    ipv4: str | None = None
    ipv6: str | None = None
    ipv4_source: str | None = None
    ipv6_source: str | None = None
    ipv4_error: str | None = None
    ipv6_error: str | None = None
    fetched_at: str | None = None


class AdapterError(Exception):
    """An adapter could not do its job. `code` matches the engine taxonomy."""

    def __init__(self, code: str, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "summary": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class EngineAdapter(Protocol):
    """What every adapter must provide.

    Intentionally small. Anything that can be done once, above the adapter —
    validation, secret handling, error translation, scheduling policy — is
    done there, so that adding an adapter stays a contained job.
    """

    name: str

    def apply(self, records: list, resolve_secrets) -> None:
        """Make this adapter's configuration match the given records."""

    def statuses(self) -> dict[str, RecordStatus]:
        """Current status for every record this adapter owns."""

    def update(self, record_id: str) -> RecordStatus:
        """Force an update of one record."""

    def update_all(self) -> list[RecordStatus]:
        """Force an update of every record."""

    def probe(self, spec: dict[str, Any], mode: str) -> ProbeResult:
        """Check a record definition that has not been saved yet."""

    def public_ip(self, refresh: bool = False) -> PublicIP:
        """The public addresses as this adapter sees them."""
