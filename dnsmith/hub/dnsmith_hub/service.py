"""The Service: everything the API handlers need, assembled in one place.

Handlers stay free of construction so the whole API can be tested against a
Service built over temporary files and a stubbed scheduler.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .adapters.base import AdapterError, ProbeResult, RecordStatus
from .adapters.native import NativeAdapter
from .errors import explain
from .models import Record, build_fqdn
from .redact import ValueRedactor
from .registry import Registry, normalise_values, split_values, validate_values
from .scheduler import Scheduler
from .secrets import SecretStore
from .store import ConfigStore

logger = logging.getLogger("dnsmith.hub")


class Service:
    def __init__(
        self,
        *,
        registry: Registry,
        store: ConfigStore,
        secrets: SecretStore,
        scheduler: Scheduler,
        native: NativeAdapter | None = None,
        redactor: ValueRedactor | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.secrets = secrets
        self.scheduler = scheduler
        self.native = native or NativeAdapter()
        self.redactor = redactor or ValueRedactor()
        self._refresh_redactor()

    # -- configuration changes ---------------------------------------------

    def apply(self) -> bool:
        """React to a configuration change.

        There is no longer an engine to push a file to: the scheduler reads the
        store on every pass, so a saved change is live by definition. What is
        still needed is the redactor, which has to learn any new secret before
        it can appear in a log line.
        """
        self._refresh_redactor()
        return True

    def _refresh_redactor(self) -> None:
        """Teach the log filter every stored secret.

        Called on construction and after every change, because a value the
        redactor has not seen is a value that can appear in a log line.
        """
        self.redactor.update(self.secrets.all_values())

    # -- records -----------------------------------------------------------

    def create_record(self, payload: dict[str, Any]) -> Record:
        record = self.store.create_record(
            provider_id=payload["provider_id"],
            domain=payload["domain"],
            owner=payload.get("owner", "@"),
            ip_version=payload.get("ip_version", "ipv4_or_ipv6"),
            values=payload.get("values", {}),
            label=payload.get("label", ""),
            ipv6_suffix=payload.get("ipv6_suffix"),
            auth_variant=payload.get("auth_variant"),
            enabled=payload.get("enabled", True),
        )
        self.apply()
        return record

    def delete_record(self, record_id: str) -> Record:
        record = self.store.delete_record(record_id)
        self.scheduler.forget(record_id)
        self.apply()
        return record

    def record_payload(self, record: Record) -> dict[str, Any]:
        payload = self.store.record_payload(record)
        status = self._statuses().get(record.id)
        payload["status"] = _status_payload(status, record.enabled, self.redactor)
        return payload

    def records_payload(self) -> dict[str, Any]:
        statuses = self._statuses()
        records = self.store.records()

        payloads = []
        for record in records:
            payload = self.store.record_payload(record)
            payload["status"] = _status_payload(
                statuses.get(record.id), record.enabled, self.redactor
            )
            payloads.append(payload)

        return {
            "records": payloads,
            "total": len(payloads),
            "failed": sum(1 for payload in payloads if payload["status"]["state"] == "fail"),
        }

    def _statuses(self) -> dict[str, RecordStatus]:
        """Status for every record, as the scheduler last saw it.

        A record the scheduler has not reached yet is simply absent, and
        _status_payload() renders that as "unset" — which is the truth, and
        better than inventing a state for it.
        """
        return self.scheduler.statuses()

    # -- actions -----------------------------------------------------------

    def force_update(self, record_id: str | None) -> dict[str, Any]:
        """Update now, because the user said so.

        The old version had to translate a DNSmith record into the engine's
        own derived ID, and a dual-stack record into two of them. The
        scheduler addresses records by the ID they already have.
        """
        statuses = (
            self.scheduler.update_all() if record_id is None else [self.scheduler.update(record_id)]
        )

        failures = [status for status in statuses if status.state.value == "fail"]
        return {
            "ok": not failures,
            "requested": len(statuses),
            "failed": len(failures),
            "errors": [
                explain(status.error, redactor=self.redactor) for status in failures if status.error
            ],
        }

    def probe(self, payload: dict[str, Any], mode: str) -> ProbeResult:
        """Check a set of values before they are saved.

        Values arrive from the form, so they include secrets in the clear.
        They are handed to the adapter and never stored, never logged and
        never echoed back.
        """
        provider = self.registry.get(payload["provider_id"])
        values = normalise_values(provider, payload.get("values", {}))

        # The record whose stored credentials may be reused for this probe.
        # It has to be a record that exists AND belongs to the same provider:
        # without that check, a caller could name any record and have its
        # credentials sent to a different provider's endpoint.
        record_id = payload.get("record_id")
        if record_id:
            existing = next(
                (item for item in self.store.records() if item.id == record_id), None)
            if existing is None or existing.provider_id != provider.id:
                record_id = None

        known = set(self.secrets.field_names(record_id)) if record_id else set()
        validate_values(
            provider, values, known_secrets=known, auth_variant=payload.get("auth_variant")
        )

        plain, secret = split_values(provider, values)

        # On an edit the form may leave stored secrets blank; fill them back
        # in so the probe tests what would actually be sent.
        if record_id:
            allowed = {field["id"] for field in provider.fields}
            for field_id, stored in self.secrets.for_record(record_id).items():
                if field_id in allowed and not secret.get(field_id):
                    secret[field_id] = stored

        owner = payload.get("owner", "@")
        domain = payload.get("domain", "")

        return self.native.probe(
            {
                "adapter": provider.adapter,
                "protocol": provider.protocol,
                "request": provider.request,
                "lookup": provider.lookup,
                "bindings": provider.bindings,
                "values": {**plain, **secret},
                # The real names, so a live lookup asks about the record the
                # user is actually configuring rather than a stand-in.
                "context": {
                    "domain": domain,
                    "zone": domain,
                    "owner": owner,
                    "subdomain": "" if owner in ("@", "") else owner,
                    "hostname": build_fqdn(owner, domain),
                },
            },
            mode,
        )


    def public_ip(self, refresh: bool = False) -> dict[str, Any]:
        address = self.scheduler.public_ip(refresh)
        payload = {
            "ipv4": address.ipv4,
            "ipv6": address.ipv6,
            "ipv4_source": address.ipv4_source,
            "ipv6_source": address.ipv6_source,
            "fetched_at": address.fetched_at,
            "notices": [],
        }
        payload["notices"] = _address_notices(
            address.ipv4, address.ipv6, address.ipv4_error, address.ipv6_error
        )
        return payload

    def status_payload(self) -> dict[str, Any]:
        records = self.records_payload()
        try:
            address = self.public_ip(False)
        except AdapterError as error:
            address = {
                "ipv4": None,
                "ipv6": None,
                "error": explain(error.as_dict(), redactor=self.redactor),
            }

        return {
            "public_ip": address,
            "records_total": records["total"],
            "records_failed": records["failed"],
            "records": records["records"],
            # Present only when the stored configuration could not be read.
            # The interface leads with it: an empty record list is otherwise
            # indistinguishable from a fresh installation.
            "config_error": self.store.load_error,
        }

    def readiness(self) -> dict[str, Any]:
        """Whether the hub can do its job.

        There is no second process to be degraded by any more. What can still
        be wrong is the thing the hub needs before it can update anything: a
        public address.
        """
        if self.store.load_error:
            return {"status": "degraded", "error": {
                "code": "config_unreadable",
                "summary": self.store.load_error,
            }}

        try:
            address = self.scheduler.public_ip(False)
        except AdapterError as error:
            return {
                "status": "degraded",
                "error": explain(error.as_dict(), redactor=self.redactor),
            }

        if not address.ipv4 and not address.ipv6:
            return {"status": "degraded", "error": {
                "code": "ip",
                "summary": "Es wurde bisher keine öffentliche IP-Adresse ermittelt.",
            }}
        return {"status": "ready"}


def _status_payload(
    status: RecordStatus | None, enabled: bool, redactor: ValueRedactor
) -> dict[str, Any]:
    if not enabled:
        return {"state": "disabled", "error": None}

    if status is None:
        return {"state": "unset", "error": None}

    return {
        "state": status.state.value,
        "current_ipv4": status.current_ipv4,
        "current_ipv6": status.current_ipv6,
        "last_attempt": status.last_attempt,
        "last_success": status.last_success,
        "banned_until": status.banned_until,
        "ip_change_count": status.ip_change_count,
        "previous_ips": status.previous_ips,
        # A stored status can sit here for days before anyone requests it;
        # whatever a provider put in `detail` goes through the same redactor
        # the log path uses, not just the ones that fail on this request.
        "error": explain(status.error, redactor=redactor),
    }


def _address_notices(
    ipv4: str | None,
    ipv6: str | None,
    ipv4_error: str | None = None,
    ipv6_error: str | None = None,
) -> list[dict[str, str]]:
    """Explain the situations users most often misdiagnose.

    A configured source that failed comes first and replaces the generic
    message: "no IPv6 found" and "the entity you named has no value right
    now" lead to different places, and only one of them is about the network.
    """
    notices: list[dict[str, str]] = []

    for version, problem in (("ipv4", ipv4_error), ("ipv6", ipv6_error)):
        if problem:
            notices.append({"code": f"{version}_source_failed", "message": problem})

    if ipv4:
        import ipaddress

        try:
            address = ipaddress.ip_address(ipv4)
        except ValueError:
            address = None

        if address is not None and address in ipaddress.ip_network("100.64.0.0/10"):
            notices.append(
                {
                    "code": "cgnat",
                    "message": (
                        "Diese IPv4-Adresse liegt im CGNAT-Bereich deines Providers. "
                        "Der DNS-Eintrag lässt sich aktualisieren, aber dein Anschluss "
                        "bleibt über IPv4 von außen nicht erreichbar. "
                        "Für Erreichbarkeit brauchst du IPv6 oder einen Tarif mit "
                        "öffentlicher IPv4-Adresse."
                    ),
                }
            )

    if not ipv4 and ipv6 and not ipv4_error:
        notices.append(
            {
                "code": "ipv6_only",
                "message": (
                    "Es wurde keine öffentliche IPv4-Adresse gefunden, wohl aber IPv6. "
                    "Das ist typisch für DS-Lite-Anschlüsse. Stelle betroffene Einträge "
                    "auf „Nur IPv6“ um, sonst scheitern die IPv4-Updates dauerhaft."
                ),
            }
        )

    if ipv4 and not ipv6 and not ipv6_error:
        notices.append(
            {
                "code": "no_ipv6",
                "message": (
                    "Es wurde keine öffentliche IPv6-Adresse gefunden. Add-on-Container "
                    "haben nur dann IPv6, wenn es für Docker aktiviert ist: "
                    "„ha docker options --enable-ipv6=true“ und danach neu starten. "
                    "Alternativ lässt sich die IPv6-Adresse unter Einstellungen "
                    "aus einer Home-Assistant-Entität übernehmen — zum Beispiel "
                    "aus der externen Adresse, die deine Router-Integration kennt."
                ),
            }
        )

    return notices
