"""Deciding when a record gets updated, and remembering how it went.

The Go engine used to own this. Moving it here is what the rewrite is really
about: the interesting part of a DDNS client is not the HTTP call, it is
knowing when NOT to make one.

Three rules do most of the work.

An unchanged address is not sent again. Every provider rate-limits, several
ban clients that update needlessly, and a record whose IP has not moved has
nothing to say. This is why `previous_ips` exists.

A failure backs off. A provider that just answered "server error" will not
answer differently two seconds later, and a client that keeps asking is the
kind that gets banned. The delay doubles up to a ceiling and resets on the
first success.

A ban is honoured. When a provider says abuse or badagent, the record stops
until `banned_until` has passed. That is the one state where doing nothing is
the entire correct behaviour.

Status is held in memory and never written to disk, matching the contract in
adapters/base.py: it is rebuilt from what actually happened, and a backup
that carried it would be wrong the moment it was restored.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from .adapters.base import AdapterError, PublicIP, RecordStatus, UpdateState
from .adapters.native import NativeAdapter
from .models import Record
from .publicip import AddressSources
from .registry import Registry

logger = logging.getLogger("dnsmith.hub")

DURATION = re.compile(r"^(\d+)(ms|s|m|h)$")
_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

# Backoff after a failure: five minutes, doubling, capped at six hours. The cap
# matters more than the curve — a provider that is down for a day should still
# be retried four times in it, not once.
BACKOFF_START = 300.0
BACKOFF_MAX = 6 * 3600.0


def parse_duration(text: str, fallback: float) -> float:
    match = DURATION.match((text or "").strip())
    if not match:
        return fallback
    return int(match.group(1)) * _UNITS[match.group(2)]


class Scheduler:
    """Runs the updates and holds what is known about each record.

    Deliberately not an asyncio component. `tick()` is a plain synchronous
    call that does one pass, which makes the whole decision table testable
    without a loop, a clock or a task. app.py is what calls it on a timer.
    """

    def __init__(
        self,
        *,
        registry: Registry,
        store,
        secrets,
        native: NativeAdapter | None = None,
        sources: AddressSources | None = None,
        clock=time.monotonic,
    ) -> None:
        self.registry = registry
        self.store = store
        self.secrets = secrets
        self.native = native or NativeAdapter()
        self.sources = sources or AddressSources()
        self._clock = clock
        self._lock = threading.Lock()
        self._statuses: dict[str, RecordStatus] = {}
        self._next_attempt: dict[str, float] = {}
        self._backoff: dict[str, float] = {}
        self._last_write: dict[str, float] = {}

    # -- what the API asks for --------------------------------------------

    def statuses(self) -> dict[str, RecordStatus]:
        with self._lock:
            return dict(self._statuses)

    def public_ip(self, refresh: bool = False) -> PublicIP:
        return self.sources.get(self.store.config.settings, refresh)

    def forget(self, record_id: str) -> None:
        """Drop everything known about a record that no longer exists."""
        with self._lock:
            self._statuses.pop(record_id, None)
            self._next_attempt.pop(record_id, None)
            self._backoff.pop(record_id, None)
            self._last_write.pop(record_id, None)

    # -- doing the work ----------------------------------------------------

    def tick(self) -> list[RecordStatus]:
        """One scheduled pass over every record. Skips whatever is not due."""
        address = self._address()
        return [
            self._guarded(record, address)
            for record in self.store.records()
            if self._due(record)
        ]

    def _guarded(self, record: Record, address: PublicIP, *, force: bool = False) -> RecordStatus:
        """Run one record so that its failure stays its own.

        _run raises AdapterError for everything a provider can do wrong, and
        that is handled inside. What is left over is the unexpected: a
        URLRejected from a DNS hiccup (it derives from Exception, not from
        AdapterError), a KeyError from credentials that a restored backup left
        behind, a provider id whose manifest was removed from the catalogue.

        Without this, one such record ends the whole pass. Worse, it never
        reaches _schedule, so it stays due forever and takes down every pass
        after it - silently, while the interface still looks healthy.
        """
        try:
            return self._run(record, address, force=force)
        except Exception as error:  # noqa: BLE001 - deliberately everything
            logger.exception("record %s failed unexpectedly", record.id)
            return self._failed(
                record,
                self._statuses.get(record.id),
                "unknown",
                {
                    "code": "unknown",
                    "summary": "Beim Aktualisieren ist ein unerwarteter Fehler aufgetreten.",
                    "detail": f"{type(error).__name__}: {error}"[:200],
                },
            )

    def update(self, record_id: str, *, force: bool = True) -> RecordStatus:
        """Update one record now, on the user's say-so.

        Force skips the due-check and the unchanged-address check, because a
        user pressing the button has usually done so precisely to overrule
        DNSmith's opinion that nothing needs doing.
        """
        record = self.store.record(record_id)
        return self._guarded(record, self._address(), force=force)

    def update_all(self, *, force: bool = True) -> list[RecordStatus]:
        address = self._address()
        return [
            self._guarded(record, address, force=force) for record in self.store.records()
        ]

    # -- the decision table -------------------------------------------------

    def _due(self, record: Record) -> bool:
        if not record.enabled:
            return False
        with self._lock:
            return self._clock() >= self._next_attempt.get(record.id, 0.0)

    def _address(self) -> PublicIP:
        try:
            return self.sources.get(self.store.config.settings)
        except Exception as error:  # noqa: BLE001
            logger.warning("public address unavailable: %s", error)
            return PublicIP()

    def _run(self, record: Record, address: PublicIP, *, force: bool = False) -> RecordStatus:
        if not record.enabled:
            return self._remember(RecordStatus(record_id=record.id, state=UpdateState.DISABLED))

        previous = self._statuses.get(record.id)
        ipv4 = address.ipv4 if record.ip_version.wants_ipv4 else None
        ipv6 = address.ipv6 if record.ip_version.wants_ipv6 else None

        if not force and previous is not None and previous.healthy:
            if previous.current_ipv4 == ipv4 and previous.current_ipv6 == ipv6:
                # Nothing moved. This is the common case and the whole reason
                # DNSmith is not rate-limited out of its providers.
                self._schedule(record, ok=True)
                return self._remember(
                    RecordStatus(
                        record_id=record.id,
                        state=UpdateState.UP_TO_DATE,
                        current_ipv4=ipv4,
                        current_ipv6=ipv6,
                        last_attempt=_stamp(),
                        last_success=previous.last_success,
                        ip_change_count=previous.ip_change_count,
                        previous_ips=previous.previous_ips,
                    )
                )

        waited = self._cooldown_remaining(record)
        if waited and not force:
            self._defer(record, waited)
            # The address changed, but not long enough ago. Providers ban
            # clients that write on every flap, and an address that moves
            # twice in a minute is a flap: waiting costs a minute of
            # staleness, writing costs the account.
            return self._remember(
                RecordStatus(
                    record_id=record.id,
                    state=previous.state if previous else UpdateState.UNSET,
                    current_ipv4=previous.current_ipv4 if previous else None,
                    current_ipv6=previous.current_ipv6 if previous else None,
                    last_attempt=_stamp(),
                    last_success=previous.last_success if previous else None,
                    ip_change_count=previous.ip_change_count if previous else 0,
                    previous_ips=previous.previous_ips if previous else [],
                )
            )

        try:
            outcome = self._perform(record, ipv4, ipv6)
        except AdapterError as error:
            return self._failed(record, previous, error.code, error.as_dict())

        if not outcome.ok:
            return self._failed(
                record, previous, outcome.code,
                {"code": outcome.code, "summary": outcome.message, "detail": outcome.raw or None},
            )

        self._schedule(record, ok=True)
        with self._lock:
            # What the cooldown counts from. Without this line _last_write
            # stayed empty, _cooldown_remaining always returned 0, and the
            # whole update_cooldown setting did nothing at all.
            self._last_write[record.id] = self._clock()
        # Der erste erfolgreiche Lauf ist kein Wechsel: davor war nichts
        # bekannt. "ip_change_count" soll zaehlen, wie oft sich die Adresse
        # geaendert hat, nicht wie oft DNSmith hingeschaut hat.
        changed = previous is not None and (previous.current_ipv4, previous.current_ipv6) != (
            ipv4,
            ipv6,
        )
        history = list(previous.previous_ips) if previous else []
        if previous is not None:
            # Only the family that actually changed goes into the history —
            # the other one is still current, not "previous".
            for old, new in ((previous.current_ipv4, ipv4), (previous.current_ipv6, ipv6)):
                if old and old != new:
                    history.append(old)

        return self._remember(
            RecordStatus(
                record_id=record.id,
                state=UpdateState.SUCCESS,
                current_ipv4=ipv4,
                current_ipv6=ipv6,
                last_attempt=_stamp(),
                last_success=_stamp(),
                ip_change_count=(previous.ip_change_count if previous else 0) + (1 if changed else 0),
                previous_ips=history[-10:],
            )
        )

    def _perform(self, record: Record, ipv4: str | None, ipv6: str | None):
        """Hand the record to whatever can update it."""
        provider = self.registry.get(record.provider_id)

        if not provider.ported:
            raise AdapterError(
                "not_implemented",
                f"{provider.name} ist in dieser Version noch nicht umgesetzt. "
                f"Bis dahin lässt sich der Anbieter über \"Generisches DynDNS2\" "
                f"oder den eigenen HTTP-Provider einrichten.",
            )

        values: dict[str, Any] = {**record.fields, **self.secrets.for_record(record.id)}

        if provider.adapter == "python":
            # Ein Modul bekommt genau eine Adressfamilie je Aufruf: sein
            # Kontext traegt einen Recordtyp, nicht zwei.
            if ipv4 and ipv6:
                first = self._perform_module(provider, record, values, ipv4, None)
                if not first.ok:
                    return first
                return self._perform_module(provider, record, values, None, ipv6)
            return self._perform_module(provider, record, values, ipv4, ipv6)

        if provider.protocol == "dyndns2" and provider.request is None:
            return self.native.update_dyndns2(
                server=values["server"],
                username=values["username"],
                password=values["password"],
                hostname=record.fqdn,
                ipv4=ipv4,
                ipv6=ipv6,
                ipv4_parameter=values.get("ipv4_parameter", "myip"),
                ipv6_parameter=values.get("ipv6_parameter", "myipv6"),
                hostname_parameter=values.get("hostname_parameter", "hostname"),
            )

        if provider.protocol == "custom_http":
            return self.native.update_custom_http(
                hostname=record.fqdn, ipv4=ipv4, ipv6=ipv6,
                **{key: value for key, value in values.items() if key != "hostname"},
            )

        request = provider.request or {}

        def send(one_v4: str | None, one_v6: str | None):
            return self.native.update_declarative(
                request,
                values,
                lookup=provider.lookup,
                create=provider.create,
                bindings=provider.bindings,
                ipv4=one_v4,
                ipv6=one_v6,
                hostname=record.fqdn,
                domain=record.domain,
                owner=record.owner,
            )

        # Some providers cannot be told about both families in one call: the
        # address goes in a single "myip", or the record type, or the host
        # name, depends on which family is meant. The manifest says so by
        # using a family-dependent value — {ip}, {rrtype}, {ipversion},
        # {v6prefix} — and a dual-stack record then simply calls twice. The
        # old Go engine did the same thing by keeping two records per entry.
        if ipv4 and ipv6 and _one_address_at_a_time(
            {"request": request, "lookup": provider.lookup, "create": provider.create}
        ):
            first = send(ipv4, None)
            if not first.ok:
                return first
            return send(None, ipv6)

        return send(ipv4, ipv6)

    def _perform_module(self, provider, record: Record, values: dict[str, Any],
                        ipv4: str | None, ipv6: str | None):
        """Hand the record to a provider module.

        The module is named by the manifest and nothing else; there is no
        registry to keep in step, and manifest_merge.py already refused a
        manifest whose module has no file. What the module gets is the same
        set of values the declarative path would have templated.
        """
        from .adapters.providers import support

        module = self._module(provider)
        api = support.Api(self.native.caller)
        context = support.Context(
            ip=ipv6 or ipv4 or "",
            ipv4=ipv4,
            ipv6=ipv6,
            rrtype="AAAA" if ipv6 else "A",
            hostname=record.fqdn,
            domain=record.domain,
            owner=record.owner,
            subdomain="" if record.owner in ("@", "") else record.owner,
        )
        return module.update(api, values, context)

    def _module(self, provider):
        import importlib

        try:
            return importlib.import_module(
                f".adapters.providers.{provider.module}", package="dnsmith_hub"
            )
        except ImportError as error:
            raise AdapterError(
                "config",
                f"Für {provider.name} fehlt das Adapter-Modul {provider.module!r}.",
                detail=str(error),
            ) from error

    # -- bookkeeping -------------------------------------------------------

    def _failed(self, record, previous, code, error) -> RecordStatus:
        banned_until = None
        if code == "banned":
            # A ban is not a retry problem. Sit out an hour rather than
            # confirming the provider's opinion of this client.
            with self._lock:
                self._next_attempt[record.id] = self._clock() + 3600.0
            banned_until = _stamp(3600)
        else:
            self._schedule(record, ok=False)

        return self._remember(
            RecordStatus(
                record_id=record.id,
                state=UpdateState.FAIL,
                current_ipv4=previous.current_ipv4 if previous else None,
                current_ipv6=previous.current_ipv6 if previous else None,
                last_attempt=_stamp(),
                last_success=previous.last_success if previous else None,
                banned_until=banned_until,
                ip_change_count=previous.ip_change_count if previous else 0,
                previous_ips=previous.previous_ips if previous else [],
                error=error,
            )
        )

    def _cooldown_remaining(self, record: Record) -> float:
        """How long this record still has to wait before it may be written.

        Zero when it may go now. The clock starts at the last successful
        write, not at the last attempt: a failed update should be retried on
        the backoff schedule, not held back by a cooldown it never used.
        """
        cooldown = parse_duration(self.store.config.settings.update_cooldown, 0.0)
        if cooldown <= 0:
            return 0.0

        with self._lock:
            last = self._last_write.get(record.id)
        if last is None:
            return 0.0

        remaining = cooldown - (self._clock() - last)
        return max(remaining, 0.0)

    def _schedule(self, record: Record, *, ok: bool) -> None:
        interval = parse_duration(self.store.config.settings.poll_interval, 300.0)

        with self._lock:
            if ok:
                self._backoff.pop(record.id, None)
                delay = interval
            else:
                delay = min(self._backoff.get(record.id, 0.0) * 2 or BACKOFF_START, BACKOFF_MAX)
                self._backoff[record.id] = delay
                # Never back off to less often than the normal interval would
                # have been, and never more often either.
                delay = max(delay, interval)
            self._next_attempt[record.id] = self._clock() + delay

    def _defer(self, record: Record, seconds: float) -> None:
        """Hold this record back for a while without touching its backoff.

        A cooldown is not a failure. It only delays the next look, so the pass
        does not keep re-evaluating a record it has already decided to leave
        alone - which is what happened while the cooldown branch returned
        without setting a next attempt.
        """
        with self._lock:
            self._next_attempt[record.id] = self._clock() + max(seconds, 1.0)

    def _remember(self, status: RecordStatus) -> RecordStatus:
        with self._lock:
            self._statuses[status.record_id] = status
        return status


def _one_address_at_a_time(request: dict[str, Any]) -> bool:
    from .adapters.native import FAMILY_DEPENDENT

    return bool(FAMILY_DEPENDENT & _placeholder_names(request))


def _placeholder_names(value: Any) -> set[str]:
    from .adapters.native import PLACEHOLDER

    if isinstance(value, str):
        names: set[str] = set()
        for chain in PLACEHOLDER.findall(value):
            names.update(part for part in chain.split("|") if not part.startswith("'"))
        return names
    if isinstance(value, dict):
        return set().union(*(_placeholder_names(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_placeholder_names(item) for item in value)) if value else set()
    return set()


def _stamp(offset: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))
