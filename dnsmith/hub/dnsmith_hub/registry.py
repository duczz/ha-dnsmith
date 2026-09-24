"""The provider catalogue, and the form contract built from it.

The registry is the only thing that knows what a provider needs. Nothing in
the API layer, the adapters or the frontend contains a provider name — a new
provider is a YAML file, not a code change.

The form contract is the shape the frontend renders. It is deliberately a
separate structure from the manifest: the manifest describes the provider,
the contract describes the form, and the second is allowed to reorder,
regroup and hide things the first does not talk about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .adapters.base import AdapterError

# Field types whose value is a credential and therefore never returned.
SECRET_TYPES = frozenset({"secret", "multiline_secret"})


class ProviderNotFound(KeyError):
    def __init__(self, provider_id: str) -> None:
        super().__init__(provider_id)
        self.provider_id = provider_id


class ValidationProblem(Exception):
    """One or more submitted values do not satisfy the manifest."""

    def __init__(self, problems: dict[str, str]) -> None:
        super().__init__("; ".join(f"{field}: {text}" for field, text in problems.items()))
        self.problems = problems


@dataclass(frozen=True)
class ResolvedMode:
    """The protocol/request/lookup/create/bindings blocks one mode of a

    provider resolves to. Never partial: a manifest's own top-level blocks
    and each entry of ``modes`` carry the same five keys, and resolve()
    always returns exactly one of them whole — nothing is merged between a
    mode and the default, or between two modes.
    """

    protocol: str | None
    request: dict[str, Any] | None
    lookup: list[dict[str, Any]] | None
    create: dict[str, Any] | None
    bindings: dict[str, Any] | None


@dataclass(frozen=True)
class Provider:
    """A manifest, with the lookups the rest of the hub needs."""

    manifest: dict[str, Any]

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def name(self) -> str:
        return self.manifest["name"]

    @property
    def adapter(self) -> str:
        return self.manifest["engine"]["adapter"]

    @property
    def protocol(self) -> str | None:
        """Which shape the declarative executor uses, for native providers."""
        return self.manifest["engine"].get("protocol")

    @property
    def module(self) -> str | None:
        """Module under adapters/providers/, for providers that need code."""
        return self.manifest["engine"].get("module")

    @property
    def request(self) -> dict[str, Any] | None:
        """The update call as data. Absent for the two user-configured
        providers and for everything not ported yet."""
        return self.manifest.get("request")

    @property
    def lookup(self) -> list[dict[str, Any]] | None:
        """Calls made before the update, each binding a value it needs."""
        return self.manifest.get("lookup")

    @property
    def bindings(self) -> dict[str, Any] | None:
        """Extra values derived from the others, for providers with their own
        spelling of something standard."""
        return self.manifest.get("bindings")

    @property
    def create(self) -> dict[str, Any] | None:
        """The call that creates the record when the lookup finds none."""
        return self.manifest.get("create")

    @property
    def mode_field(self) -> str | None:
        """ID of the select field that chooses among modes, if this provider has any."""
        return self.manifest.get("mode_field")

    @property
    def modes(self) -> dict[str, dict[str, Any]]:
        """Alternatives to the manifest's own top-level blocks, by id."""
        return self.manifest.get("modes") or {}

    @property
    def ported(self) -> bool:
        return self.adapter != "unported"

    @property
    def fields(self) -> list[dict[str, Any]]:
        return self.manifest.get("fields", [])

    @property
    def categories(self) -> list[str]:
        return self.manifest.get("categories", [])

    @property
    def auth_variants(self) -> list[dict[str, Any]]:
        return self.manifest.get("auth", {}).get("one_of", [])

    def field(self, field_id: str) -> dict[str, Any] | None:
        for field in self.fields:
            if field["id"] == field_id:
                return field
        return None

    def secret_field_ids(self) -> list[str]:
        return [field["id"] for field in self.fields if field["type"] in SECRET_TYPES]

    def maps_to(self, field_id: str) -> str:
        field = self.field(field_id)
        if field is None:
            return field_id
        return field.get("maps_to", field_id)

    def search_text(self) -> str:
        parts = [self.id, self.name, self.manifest.get("description", "")]
        parts.extend(self.categories)
        return " ".join(parts).lower()

    def resolve(self, values: dict[str, Any]) -> ResolvedMode:
        """The blocks that apply for whatever mode `values` names.

        Absent, empty, or equal to mode_field's own default all count as the
        default mode — the manifest's own top-level blocks — which is what
        covers every record saved before modes existed, and any API caller
        that has never heard of mode_field, without either needing a
        migration. A value that names neither the default nor a real mode is
        refused rather than quietly treated as the default: falling back
        silently would let a typo'd or stale mode send one mode's
        credentials to another's endpoint.
        """
        default = ResolvedMode(
            protocol=self.protocol,
            request=self.request,
            lookup=self.lookup,
            create=self.create,
            bindings=self.bindings,
        )

        mode_field = self.mode_field
        if mode_field is None:
            return default

        chosen = values.get(mode_field)
        if chosen in (None, ""):
            return default

        default_id = (self.field(mode_field) or {}).get("default")
        if chosen == default_id:
            return default

        block = self.modes.get(chosen)
        if block is None:
            raise AdapterError(
                "config",
                f"{self.name} kennt das Verfahren {chosen!r} nicht.",
            )

        return ResolvedMode(
            protocol=block.get("protocol", self.protocol),
            request=block.get("request"),
            lookup=block.get("lookup"),
            create=block.get("create"),
            bindings=block.get("bindings"),
        )


class Registry:
    """Loads providers/*.yaml once and answers questions about them."""

    def __init__(self, directory: Path, logo_dir: Path | None = None) -> None:
        self._directory = Path(directory)
        # Provider logos live in the repository, but not every provider has
        # one: a few sites offer no usable icon, and tools/fetch_logos.py
        # leaves those out rather than inventing something. The directory is
        # read at startup and may be missing entirely, so everything below has
        # to work without it - the interface then draws initials.
        self._logo_dir = Path(logo_dir) if logo_dir else None
        self._logos: dict[str, str] = {}
        self._providers: dict[str, Provider] = {}

    def _load_logos(self) -> dict[str, str]:
        """Map provider id -> relative logo URL, for the ids that have one."""
        if not self._logo_dir or not self._logo_dir.is_dir():
            return {}
        found = {}
        # Favicons come in whatever format the provider serves. Sorting by
        # the extension order below means a provider with both an .svg and a
        # leftover .ico gets the vector one.
        paths = sorted(
            (path for path in self._logo_dir.iterdir()
             if path.suffix.lower() in (".ico", ".gif", ".jpg", ".webp", ".png", ".svg")),
            key=lambda path: (path.stem, path.suffix.lower()),
        )
        for path in paths:
            # The file name IS the provider id. A file for an unknown provider
            # is ignored rather than reported: the fetch script is allowed to
            # run ahead of a manifest being added.
            found[path.stem] = f"assets/logos/{path.name}"
        return found

    def load(self) -> None:
        providers: dict[str, Provider] = {}

        for path in sorted(self._directory.glob("*.yaml")):
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or "id" not in manifest:
                raise ValueError(f"{path} is not a provider manifest")
            provider = Provider(manifest)
            if provider.id in providers:
                raise ValueError(f"duplicate provider {provider.id!r} in {path}")
            providers[provider.id] = provider

        if not providers:
            raise ValueError(f"no provider manifests found in {self._directory}")

        self._providers = providers
        self._logos = self._load_logos()

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, provider_id: object) -> bool:
        return provider_id in self._providers

    def get(self, provider_id: str) -> Provider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ProviderNotFound(provider_id) from error

    def all(self) -> list[Provider]:
        return sorted(self._providers.values(), key=lambda provider: provider.name.lower())

    def search(self, query: str = "", category: str | None = None) -> list[Provider]:
        needle = (query or "").strip().lower()
        results = []
        for provider in self.all():
            if category and category not in provider.categories:
                continue
            if needle and needle not in provider.search_text():
                continue
            results.append(provider)
        return results

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for provider in self._providers.values():
            for category in provider.categories:
                counts[category] = counts.get(category, 0) + 1
        return dict(sorted(counts.items()))

    def summaries(self) -> list[dict[str, Any]]:
        """The picker's payload: enough to list and filter, no form detail."""
        return [
            {
                "id": provider.id,
                "name": provider.name,
                "description": provider.manifest.get("description", ""),
                "categories": provider.categories,
                "popular": bool(provider.manifest.get("popular", False)),
                "capabilities": provider.manifest["capabilities"],
                # False while a provider has no updater behind it yet. The
                # picker still lists it — knowing DNSmith is aware of your
                # provider is worth something — but marks it, and the form
                # says so rather than letting the user save a record that
                # would fail on its first pass.
                "ported": provider.ported,
                "website": provider.manifest.get("website"),
                # None when no logo file is present, which is the normal case
                # for the long tail of DDNS providers. The frontend falls back
                # to a monogram and must never assume this is set.
                "logo": self._logos.get(provider.id),
                "brand_color": (provider.manifest.get("brand") or {}).get("color"),
            }
            for provider in self.all()
        ]


# ---------------------------------------------------------------------------
# Form contract
# ---------------------------------------------------------------------------


def build_form(provider: Provider) -> dict[str, Any]:
    """Turn a manifest into the description the frontend renders.

    The frontend has no provider knowledge whatsoever: it reads this and draws
    inputs. Everything provider-specific — which credential styles exist,
    which fields depend on which, what a value must look like — arrives here.
    """
    manifest = provider.manifest
    variants = provider.auth_variants
    in_variant = {name for variant in variants for name in variant["fields"]}

    form: dict[str, Any] = {
        "provider_id": provider.id,
        "name": provider.name,
        "description": manifest.get("description", ""),
        "website": manifest.get("website"),
        "capabilities": manifest["capabilities"],
        "notes": manifest.get("notes", []),
        "rate_limit": manifest.get("rate_limit"),
        "ip_versions": _offered_ip_versions(manifest["capabilities"]),
        # Whether a check before saving can reach the provider at all. Only
        # providers whose update begins with a lookup can be asked something
        # read-only; for the rest the update IS the write, so there is nothing
        # safe to try. The form says which kind this is, so the button can be
        # honest before it is pressed rather than after.
        #
        # Deliberately reads the manifest's own top-level lookup, not
        # provider.resolve(...)'s — a provider with modes gets one label for
        # every mode, even where a mode's own lookup differs from the
        # default's. Fine while a mode with a lookup is new enough to be
        # marked untested anyway; worth revisiting (a label and a probe per
        # mode) once that stops being true for whichever provider first
        # needs it.
        "live_test": bool(provider.lookup),
        "auth": None,
        "fields": [],
    }

    if variants:
        form["auth"] = {
            "variants": [
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "fields": variant["fields"],
                    "recommended": bool(variant.get("recommended", False)),
                    "deprecated": bool(variant.get("deprecated", False)),
                    "hint": variant.get("hint"),
                }
                for variant in variants
            ],
            "default": _default_variant(variants),
        }

    for field in provider.fields:
        entry = {
            "id": field["id"],
            "type": field["type"],
            "label": field["label"],
            "required": bool(field.get("required", False)),
            "secret": field["type"] in SECRET_TYPES,
            "help": field.get("help"),
            "placeholder": field.get("placeholder") or _placeholder(manifest, field),
            "default": field.get("default"),
            "options": field.get("options"),
            "when": field.get("when"),
            "validate": field.get("validate"),
            "ui": field.get("ui", {}),
            # The frontend needs to know a field only appears once its
            # variant is chosen, so it can hide it rather than mark it wrong.
            "auth_variant_only": field["id"] in in_variant,
        }
        form["fields"].append(entry)

    return form


def _default_variant(variants: list[dict[str, Any]]) -> str:
    for variant in variants:
        if variant.get("recommended"):
            return variant["id"]
    return variants[0]["id"]


def _offered_ip_versions(capabilities: dict[str, Any]) -> list[dict[str, str]]:
    """Which IP-version choices to offer for this provider.

    A provider that cannot do IPv6 must not be offered it — namecheap is the
    current example. Offering it would produce a record that can never
    succeed, and a user with no way to tell why.

    Dual-stack comes first when a provider can do both: the frontend
    preselects whichever option this list returns first (`app.js`), and most
    home networks have working IPv6 today, so defaulting to the fuller answer
    beats defaulting to IPv4-only and leaving IPv6 support undiscovered.
    """
    can_both = bool(capabilities.get("ipv4")) and bool(capabilities.get("ipv6"))
    offered = []
    if can_both:
        offered.append({"value": "dual_stack", "label": "IPv4 und IPv6"})
    if capabilities.get("ipv4"):
        offered.append({"value": "ipv4", "label": "Nur IPv4"})
    if capabilities.get("ipv6"):
        offered.append({"value": "ipv6", "label": "Nur IPv6"})
    if can_both:
        offered.append(
            {
                "value": "ipv4_or_ipv6",
                "label": "IPv4 oder IPv6, je nachdem was verfügbar ist",
            }
        )
    return offered


def _placeholder(manifest: dict[str, Any], field: dict[str, Any]) -> str | None:
    if field["type"] in SECRET_TYPES:
        return None
    example = manifest.get("example") or {}
    value = example.get(field["id"])
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def split_values(
    provider: Provider, values: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Separate submitted values into plain fields and secrets.

    This is the single point where a secret is recognised. Everything
    downstream — storage, export, logging — relies on the split having
    happened here and nowhere else.
    """
    secret_ids = set(provider.secret_field_ids())
    plain: dict[str, Any] = {}
    secret: dict[str, str] = {}

    for field_id, value in values.items():
        if field_id in secret_ids:
            secret[field_id] = "" if value is None else str(value)
        else:
            plain[field_id] = value

    return plain, secret


def apply_defaults(provider: Provider, values: dict[str, Any]) -> dict[str, Any]:
    """Fill in the manifest defaults the user did not supply.

    Without this, a default is decoration: it fills the form control, and the
    moment the user submits without touching it, the value never reaches the
    engine. Cloudflare is where that stopped being cosmetic — its Go
    constructor rejects a zero TTL with ErrTTLNotSet, so a record created by
    accepting the form as offered would be refused by the engine at startup,
    with an error that names Cloudflare rather than the missing field.

    Only fields that are actually visible get a default. A field hidden behind
    an unmet `when` condition must stay absent, or the engine receives settings
    for a mode the user did not choose.
    """
    filled = dict(values)
    for field in provider.fields:
        if "default" not in field:
            continue
        if filled.get(field["id"]) not in (None, ""):
            continue
        if not _is_visible(provider, field, filled):
            continue
        filled[field["id"]] = field["default"]
    return filled


def normalise_values(provider: Provider, values: dict[str, Any]) -> dict[str, Any]:
    """Accept what a provider actually hands its users.

    Several providers do not give out a key, they give out a finished update
    URL with the key inside it — IPv64 shows
    "https://ipv64.net/nic/update?key=...", FreeDNS a sync URL with the token
    as a path segment. Telling people to cut the right part out of it is a
    step that exists only because the form is picky, and the ones who get it
    wrong get an authentication error that points nowhere.

    So a field may declare where its value sits inside such a URL, and a
    pasted URL is reduced to the value before anything else looks at it. A
    value that is not a URL passes through untouched, which is the normal
    case.

    Runs before validation on purpose: the pattern on the field would
    otherwise reject the paste before this had a chance to fix it.
    """
    result = dict(values)

    for field in provider.fields:
        rule = field.get("extract")
        raw = result.get(field["id"])
        if not rule or not isinstance(raw, str) or not raw.strip():
            continue
        extracted = _extract_from_url(raw.strip(), rule)
        if extracted:
            result[field["id"]] = extracted

    return result


def _extract_from_url(raw: str, rule: dict[str, Any]) -> str | None:
    from urllib.parse import parse_qs, urlsplit

    if not raw.lower().startswith(("http://", "https://")):
        return None

    parsed = urlsplit(raw)
    if "url_query" in rule:
        found = parse_qs(parsed.query).get(rule["url_query"])
        return found[0] if found else None
    if rule.get("url_path") == "last":
        segments = [segment for segment in parsed.path.split("/") if segment]
        return segments[-1] if segments else None
    return None


def validate_values(
    provider: Provider,
    values: dict[str, Any],
    *,
    known_secrets: set[str] | None = None,
    auth_variant: str | None = None,
) -> None:
    """Check submitted values against the manifest, or raise ValidationProblem.

    `known_secrets` names secret fields that are already stored, so an edit
    form may leave them blank without the record becoming invalid.
    """
    known_secrets = known_secrets or set()
    problems: dict[str, str] = {}

    declared = {field["id"] for field in provider.fields}
    for field_id in values:
        if field_id not in declared:
            problems[field_id] = f"{provider.name} kennt kein Feld mit diesem Namen."

    variant_fields = _required_variant_fields(provider, auth_variant, problems)

    for field in provider.fields:
        field_id = field["id"]

        if not _is_visible(provider, field, values):
            continue

        raw = values.get(field_id)
        supplied = raw not in (None, "")
        if not supplied and field_id in known_secrets:
            supplied = True

        required = bool(field.get("required", False)) or field_id in variant_fields
        if required and not supplied:
            problems.setdefault(field_id, f"„{field['label']}“ ist erforderlich.")
            continue

        if not supplied or raw in (None, ""):
            continue

        problem = _check_value(field, raw)
        if problem:
            problems.setdefault(field_id, problem)

    if problems:
        raise ValidationProblem(problems)


def _required_variant_fields(
    provider: Provider, auth_variant: str | None, problems: dict[str, str]
) -> set[str]:
    variants = provider.auth_variants
    if not variants:
        return set()

    if auth_variant is None:
        auth_variant = _default_variant(variants)

    for variant in variants:
        if variant["id"] == auth_variant:
            return set(variant["fields"])

    problems["auth_variant"] = (
        f"Unbekanntes Anmeldeverfahren {auth_variant!r}. "
        f"Möglich sind: {', '.join(variant['id'] for variant in variants)}."
    )
    return set()


def _is_visible(provider: Provider, field: dict[str, Any], values: dict[str, Any]) -> bool:
    """Whether `field`'s `when` condition is met.

    A record written before its controlling field existed, or submitted by a
    caller that never sent it, simply lacks a value for it — that is not the
    same as the condition being unmet. The controlling field's own default is
    what a fresh form shows and what such a record implicitly meant, so an
    absent value falls back to it rather than to None, which nothing in a
    manifest ever equals. Only a value that is genuinely absent falls back;
    one explicitly cleared to "" is not, matching how required-ness elsewhere
    in this module already treats "" as "nothing supplied".
    """
    condition = field.get("when")
    if not condition:
        return True
    actual = values.get(condition["field"])
    if actual is None:
        source = provider.field(condition["field"])
        if source is not None:
            actual = source.get("default")
    return actual == condition["equals"]


def _check_value(field: dict[str, Any], raw: Any) -> str | None:
    field_type = field["type"]
    rules = field.get("validate") or {}

    if field_type == "boolean":
        if not isinstance(raw, bool):
            return "Erwartet wird ja oder nein."
        return None

    if field_type == "integer":
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return "Erwartet wird eine ganze Zahl."
        if "min" in rules and number < rules["min"]:
            return f"Der Wert muss mindestens {rules['min']} sein."
        if "max" in rules and number > rules["max"]:
            return f"Der Wert darf höchstens {rules['max']} sein."
        return None

    text = str(raw)

    if field_type == "select":
        allowed = {str(option["value"]) for option in field.get("options", [])}
        if text not in allowed:
            return f"Möglich sind: {', '.join(sorted(allowed))}."
        return None

    if field_type == "email" and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
        return "Das sieht nicht wie eine E-Mail-Adresse aus."

    if field_type in ("hostname", "domain") and not _looks_like_hostname(text):
        return "Das sieht nicht wie ein Hostname aus."

    if field_type == "ipv6_prefix" and "/" not in text:
        return "Erwartet wird ein Präfix wie ::1/64."

    if "pattern" in rules and not re.search(rules["pattern"], text):
        return "Das Format stimmt nicht."

    if "min_length" in rules and len(text) < rules["min_length"]:
        return f"Mindestens {rules['min_length']} Zeichen."
    if "max_length" in rules and len(text) > rules["max_length"]:
        return f"Höchstens {rules['max_length']} Zeichen."

    return None


def _looks_like_hostname(value: str) -> bool:
    value = value.rstrip(".")
    if not value or len(value) > 253:
        return False
    # A leading "*." is a wildcard record, which several providers support.
    if value.startswith("*."):
        value = value[2:]
    labels = value.split(".")
    return all(re.fullmatch(r"[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?", label)
               for label in labels)
