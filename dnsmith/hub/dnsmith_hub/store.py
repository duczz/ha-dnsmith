"""The configuration store: the single source of truth for DNSmith.

The engine's config.json is a generated artefact, like a build output. It is
written from here and never read back. Nothing else in the system is allowed
to be authoritative about a record, because two authorities is how a user ends
up with a record that exists in one place and not the other.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CONFIG_VERSION, DnsmithConfig, IPVersion, Record, derive_record_id
from .registry import (
    Provider,
    Registry,
    ValidationProblem,
    _looks_like_hostname,
    apply_defaults,
    normalise_values,
    split_values,
    validate_values,
)
from .secrets import SecretStore

logger = logging.getLogger("dnsmith.hub")

CONFIG_FILE_MODE = 0o600


class RecordNotFound(KeyError):
    def __init__(self, record_id: str) -> None:
        super().__init__(record_id)
        self.record_id = record_id


class DuplicateRecord(ValueError):
    """Two records with the same identity would collide in the engine."""

    def __init__(self, record_id: str, fqdn: str) -> None:
        super().__init__(
            f"Für {fqdn} gibt es bereits einen Eintrag mit demselben Anbieter "
            f"und derselben IP-Version."
        )
        self.record_id = record_id
        self.fqdn = fqdn


class ConfigUnreadable(RuntimeError):
    """The stored configuration could not be read, so it must not be written."""


class ConfigStore:
    def __init__(self, path: Path, secrets: SecretStore, registry: Registry) -> None:
        self._path = Path(path)
        self._secrets = secrets
        self._registry = registry
        self._config = DnsmithConfig()
        self._loaded = False
        self._load_error: str | None = None
        # `force_update`/`probe`/`public_ip` now run in a worker thread
        # (asyncio.to_thread) while every other handler still calls this
        # store inline on the event loop thread — the same records list and
        # config object can genuinely be read and mutated at once. Reentrant
        # because update_record/delete_record call self.record() while
        # already holding it.
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------

    def load(self) -> None:
        """Read the configuration, or record why it could not be read.

        A configuration that does not load used to end the process: the
        add-on then restarted every few seconds, and the one thing that could
        have explained the problem — the interface — was exactly what never
        came up. So a failure is remembered instead of raised, the add-on
        starts with nothing configured, and the reason is shown where the
        user is looking.

        The file itself is left exactly as it is. Nothing here repairs it and
        nothing may overwrite it, because it holds the only copy of the
        user's records.
        """
        with self._lock:
            self._load_error = None

            if not self._path.is_file():
                self._config = DnsmithConfig()
                self._loaded = True
                return

            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                raw = migrate(raw)
                self._config = DnsmithConfig.model_validate(raw)
            except Exception as error:  # noqa: BLE001 - every cause has the same remedy
                self._config = DnsmithConfig()
                self._load_error = _describe_load_failure(self._path, error)
                logger.error("configuration could not be read: %s", self._load_error)

            self._loaded = True

    @property
    def load_error(self) -> str | None:
        """Why the configuration is not the one on disk, if it is not."""
        with self._lock:
            self._ensure_loaded()
            return self._load_error

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        with self._lock:
            # The in-memory configuration is empty because reading failed,
            # not because the user emptied it. Writing it out would replace
            # their records with nothing — the one outcome worse than not
            # starting.
            if self._load_error:
                raise ConfigUnreadable(self._load_error)

            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._config.model_dump(mode="json", exclude_none=False)

            handle, temporary = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".config-", suffix=".tmp"
            )
            try:
                os.fchmod(handle, CONFIG_FILE_MODE)
                with os.fdopen(handle, "w", encoding="utf-8") as file:
                    json.dump(payload, file, indent=2, sort_keys=False)
                    file.write("\n")
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self._path)
            except BaseException:
                try:
                    os.unlink(temporary)
                except OSError:  # pragma: no cover
                    pass
                raise

    # -- reading -----------------------------------------------------------

    @property
    def config(self) -> DnsmithConfig:
        with self._lock:
            self._ensure_loaded()
            return self._config

    def records(self) -> list[Record]:
        with self._lock:
            return list(self.config.records)

    def record(self, record_id: str) -> Record:
        with self._lock:
            for record in self.config.records:
                if record.id == record_id:
                    return record
            raise RecordNotFound(record_id)

    # -- writing -----------------------------------------------------------

    def create_record(
        self,
        provider_id: str,
        domain: str,
        owner: str,
        ip_version: str,
        values: dict[str, Any],
        *,
        label: str = "",
        ipv6_suffix: str | None = None,
        auth_variant: str | None = None,
        enabled: bool = True,
    ) -> Record:
        with self._lock:
            self._ensure_loaded()
            provider = self._registry.get(provider_id)

            problems: dict[str, str] = {}
            if not _looks_like_hostname(domain):
                problems["domain"] = "Das sieht nicht wie ein Hostname aus."
            if owner not in ("", "@") and not _looks_like_hostname(owner):
                problems["owner"] = "Das sieht nicht wie ein Hostname aus."
            try:
                IPVersion(ip_version)
            except ValueError:
                problems["ip_version"] = "Möglich sind: ipv4, ipv6, ipv4_or_ipv6, dual_stack."
            if problems:
                raise ValidationProblem(problems)

            values = normalise_values(provider, values)
            validate_values(provider, values, auth_variant=auth_variant)
            values = apply_defaults(provider, values)
            plain, secret = split_values(provider, values)

            record_id = self._identity(provider, domain, owner, ip_version, ipv6_suffix)
            if any(existing.id == record_id for existing in self._config.records):
                raise DuplicateRecord(record_id, f"{owner}.{domain}".lstrip("@."))

            now = _now()
            record = Record(
                id=record_id,
                provider_id=provider_id,
                label=label,
                domain=domain,
                owner=owner or "@",
                ip_version=ip_version,
                ipv6_suffix=ipv6_suffix,
                fields=plain,
                secret_fields=sorted(key for key, value in secret.items() if value),
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )

            self._config.records.append(record)
            # Secrets first: if the process dies between the two writes, an
            # orphaned secret is harmless, whereas a record whose credentials
            # were never stored would fail on every update with no way to
            # tell why.
            if secret:
                self._secrets.set_many(record_id, secret)
            self.save()

            return record

    def update_record(
        self,
        record_id: str,
        *,
        values: dict[str, Any] | None = None,
        label: str | None = None,
        enabled: bool | None = None,
        auth_variant: str | None = None,
    ) -> Record:
        """Change a record in place.

        The identity fields — provider, domain, owner, IP version — are not
        editable, because changing one changes the record's derived ID, which
        would orphan its history and every Home Assistant entity built on it.
        The UI offers delete-and-recreate for that, which is honest about what
        happens.
        """
        with self._lock:
            self._ensure_loaded()
            record = self.record(record_id)
            provider = self._registry.get(record.provider_id)

            if values is not None:
                known = set(self._secrets.field_names(record_id))
                values = normalise_values(provider, values)
                validate_values(provider, values, known_secrets=known, auth_variant=auth_variant)
                values = apply_defaults(provider, values)
                plain, secret = split_values(provider, values)

                record.fields = plain
                if secret:
                    self._secrets.set_many(record_id, secret)
                if auth_variant is not None:
                    self._secrets.forget_fields(
                        record_id, _stale_variant_fields(provider, auth_variant)
                    )
                record.secret_fields = self._secrets.field_names(record_id)

            if label is not None:
                record.label = label
            if enabled is not None:
                record.enabled = enabled

            record.updated_at = _now()
            self.save()
            return record

    def delete_record(self, record_id: str) -> Record:
        with self._lock:
            self._ensure_loaded()
            record = self.record(record_id)

            self._config.records = [
                existing for existing in self._config.records if existing.id != record_id
            ]
            # Config first, credentials second - the mirror image of
            # create_record and for the same reason. If save() fails here,
            # the record is still listed; had the credentials gone first, it
            # would be listed WITHOUT them and fail every update with no way
            # to tell why.
            self.save()
            self._secrets.forget(record_id)

            return record

    def update_settings(self, changes: dict[str, Any]) -> None:
        with self._lock:
            self._ensure_loaded()
            merged = self._config.settings.model_dump(mode="json")
            merged.update(changes)
            self._config.settings = type(self._config.settings).model_validate(merged)
            self.save()

    def prune_orphaned_secrets(self) -> list[str]:
        """Drop credentials no record refers to any more.

        Refused while the configuration is unreadable: "no record refers to
        them" would then be true of every credential in the store, and the
        tidy-up would delete all of them.
        """
        with self._lock:
            self._ensure_loaded()
            if self._load_error:
                return []
            return self._secrets.retain_only({record.id for record in self._config.records})

    # -- presentation ------------------------------------------------------

    def record_payload(self, record: Record) -> dict[str, Any]:
        """A record as the API returns it.

        Secret values never appear. Each secret field is reported as set or
        unset, which is all the UI needs to render the form correctly.
        """
        with self._lock:
            provider = self._registry.get(record.provider_id)

            secrets = {
                field_id: {"set": self._secrets.has(record.id, field_id)}
                for field_id in provider.secret_field_ids()
            }

            return {
                "id": record.id,
                "provider_id": record.provider_id,
                "provider_name": provider.name,
                "label": record.label,
                "display_name": record.display_name,
                "domain": record.domain,
                "owner": record.owner,
                "fqdn": record.fqdn,
                "ip_version": record.ip_version.value,
                "ipv6_suffix": record.ipv6_suffix,
                "fields": dict(record.fields),
                "secrets": secrets,
                "enabled": record.enabled,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }

    def export(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """A backup.

        Without secrets by default. The export is a file that ends up in
        cloud-synced folders and support threads, so the safe shape is the
        default and the complete one is a deliberate act.
        """
        with self._lock:
            self._ensure_loaded()
            payload: dict[str, Any] = {
                "config_version": self._config.config_version,
                "exported_at": _now(),
                "includes_secrets": include_secrets,
                "settings": self._config.settings.model_dump(mode="json"),
                "records": [record.model_dump(mode="json") for record in self._config.records],
            }

            if include_secrets:
                payload["secrets"] = {
                    record.id: self._secrets.for_record(record.id)
                    for record in self._config.records
                }

            return payload

    # -- helpers -----------------------------------------------------------

    def _identity(
        self,
        provider: Provider,
        domain: str,
        owner: str,
        ip_version: str,
        ipv6_suffix: str | None,
    ) -> str:
        """The record's stable ID.

        Derived from provider, domain, owner and address family, so the same
        entry keeps its ID across restarts and configuration rewrites.
        """
        identity_provider = f"native:{provider.id}"
        engine_version = _primary_engine_version(ip_version)
        return derive_record_id(identity_provider, domain, owner, engine_version, ipv6_suffix)


def _stale_variant_fields(provider: Provider, active_variant: str) -> set[str]:
    """Which fields belong to an auth variant other than the active one.

    Only called with an explicit `auth_variant` — never with the resolved
    default, so a caller that omits it (a partial update, a script) cannot be
    misread as "switched to the default variant" and lose its real secrets.
    A field shared between two variants (none today, but the schema allows
    it) is never stale, since dropping it would still break the variant that
    keeps using it.
    """
    variants = provider.auth_variants
    if not variants:
        return set()

    active_fields = set()
    other_fields = set()
    for variant in variants:
        target = active_fields if variant["id"] == active_variant else other_fields
        target.update(variant["fields"])

    return other_fields - active_fields


def _primary_engine_version(ip_version: str) -> str:
    """The engine ip_version that identifies this record.

    A dual-stack record becomes two engine records; the IPv4 one is used as
    the identity so the ID does not change if the user later narrows the
    record to IPv4 only.
    """
    if ip_version in ("dual_stack", "ipv4"):
        return "ipv4"
    if ip_version == "ipv6":
        return "ipv6"
    return "ipv4 or ipv6"


def _describe_load_failure(path: Path, error: Exception) -> str:
    """Say what is wrong in terms the user can act on."""
    if isinstance(error, json.JSONDecodeError):
        detail = (
            f"Die Datei ist keine gültige JSON-Datei (Zeile {error.lineno}, "
            f"Spalte {error.colno})."
        )
    elif isinstance(error, ValueError) and "neueren DNSmith-Version" in str(error):
        detail = str(error)
    else:
        detail = f"Der Inhalt passt nicht zum erwarteten Format: {error}"

    return (
        f"Die gespeicherte Konfiguration konnte nicht gelesen werden. {detail} "
        f"DNSmith läuft deshalb ohne Einträge weiter und hat die Datei "
        f"unverändert gelassen: {path}. Solange dieser Hinweis steht, wird "
        f"nichts gespeichert — so geht nichts verloren."
    )


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Bring a stored configuration up to the current version.

    Each step is separate and one-directional. There is only one version so
    far; the machinery exists now so that the first real migration is a
    function and a test, not a redesign.
    """
    version = int(raw.get("config_version", 0))

    if version > CONFIG_VERSION:
        raise ValueError(
            f"Diese Konfiguration stammt aus einer neueren DNSmith-Version "
            f"(Format {version}, unterstützt wird {CONFIG_VERSION}). "
            f"Bitte DNSmith aktualisieren."
        )

    if version == 0:
        raw = dict(raw)
        raw["config_version"] = 1
        raw.setdefault("settings", {})
        raw.setdefault("records", [])

    if raw.get("config_version") == 1:
        # Settings that were only ever written, never read: "resolver" and
        # "notifications" had no implementation behind them, and the IP
        # sources carried three fields of an idea that was never built. The
        # model forbids unknown keys, so leaving them would make an older
        # configuration fail to load rather than quietly carry dead weight.
        raw = dict(raw)
        settings = dict(raw.get("settings") or {})
        for gone in ("resolver", "notifications"):
            settings.pop(gone, None)

        for key in ("ip_source_v4", "ip_source_v6"):
            source = settings.get(key)
            if isinstance(source, dict):
                source = dict(source)
                for gone in ("http_providers", "dns_providers", "prefix_source", "suffix"):
                    source.pop(gone, None)
                if source.get("mode") == "prefix_suffix":
                    # The mode never did anything, so the honest replacement
                    # is the behaviour the user actually got: automatic.
                    source["mode"] = "auto"
                settings[key] = source

        raw["settings"] = settings
        raw["config_version"] = 2

    if raw.get("config_version") == 2:
        # log_level was settable and persisted but never read anywhere:
        # configure_logging() only ever looked at the DNSMITH_LOG_LEVEL
        # environment variable. Same situation as the version-1 fields
        # above, same remedy.
        raw = dict(raw)
        settings = dict(raw.get("settings") or {})
        settings.pop("log_level", None)
        raw["settings"] = settings
        raw["config_version"] = 3

    return raw


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
