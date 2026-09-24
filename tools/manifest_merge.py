#!/usr/bin/env python3
"""Build DNSmith provider manifests from the source files in providers/src/.

Until the rewrite a manifest had two halves: an engine-facing half that was
generated, and a human-facing source file (once called an "overlay", from
when it was laid over that generated half — the name outlived the thing it
described). The generated half is gone — so ``providers/src/<id>.yaml`` is
now the single source a person writes, and this script validates it and
writes ``providers/<id>.yaml`` beside it.

What replaced the old contract check is the placeholder check in
validate(): every ``{name}`` in a provider's request block has to resolve to
a field the form actually collects, or to a value the updater supplies. That
is the same failure it used to catch — a manifest promising something the
updater cannot deliver — only now it is checkable inside this repository
instead of against somebody else's Go.

Usage:
    manifest_merge.py            # write providers/<id>.yaml
    manifest_merge.py --check    # fail if the committed manifests are stale
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("PyYAML is required: pip install pyyaml")

try:  # jsonschema 4 names the draft explicitly; 3.x only ships Draft7.
    from jsonschema import Draft202012Validator as SchemaValidator
except ImportError:  # pragma: no cover
    from jsonschema import Draft7Validator as SchemaValidator


SCHEMA_VERSION = 1

# Values the updater puts in by itself. Everything else a template names has to
# be a field on the form, or the request would go out with a hole in it.
RUNTIME_VALUES = {
    "ip",         # whichever family this run is updating
    "ipv4",
    "ipv6",
    "ipversion",  # "4" or "6", for hosts like dyndns6.variomedia.de
    "v6prefix",   # "v6." or "", for hosts like v6.sync.afraid.org
    "rrtype",     # "A" or "AAAA"
    "hostname",   # owner + domain, assembled
    "domain",
    "owner",
    "subdomain",  # owner, but empty at the apex
    "zone",       # the domain, for APIs that call it that
}

# Mirrors PLACEHOLDER in adapters/native.py. A placeholder may be a chain of
# fallbacks: {ipv6|'preserve'}. Quoted parts are literals and need no field.
PLACEHOLDER = re.compile(r"\{([a-z0-9_]+(?:\|(?:[a-z0-9_]+|'[^'{}|]*'))*)\}")

# Field names whose value is a credential. Matching is exact: a substring rule
# would catch "access_key_id" as a secret, and an ID is not a secret — it is
# something the user needs to be able to read back to check it.
#
# Nothing derives a field's type from this any more; the source file states
# the type outright. It stays because the manifest tests use it to assert the
# other direction: that no field named like a credential is rendered as a
# plain text input.
SECRET_FIELDS = {
    "access_key", "access_secret", "access_token", "api_key", "api_secret",
    "apikey", "app_key", "app_secret", "client_key", "consumer_key",
    "credentials", "key", "password", "personal_access_token", "secret",
    "secret_api_key", "secret_key", "token",
}

# Fields that are identifiers rather than credentials, even though their name
# looks secret-ish. Kept visible so the user can verify what they pasted.
VISIBLE_OVERRIDES = {"access_key_id", "customer_number", "zone_identifier", "zone_id"}

MULTILINE_SECRETS = {"credentials"}


def is_empty_example(field_id: str, value: Any) -> bool:
    """Does this example show the user anything?

    A placeholder that merely restates its own label — "username" under
    "Benutzername" — teaches nothing, and trains people to ignore the grey
    text, including where it matters.
    """
    flat = re.sub(r"[^a-z0-9]", "", str(value).lower())
    if not flat:
        return True
    if flat == re.sub(r"[^a-z0-9]", "", field_id.lower()):
        return True
    if flat == "your" + re.sub(r"[^a-z0-9]", "", field_id.lower()):
        return True
    return flat in {"username", "user", "password", "domain", "example", "host", "someid"}


RESERVED_IN_SRC = ("schema_version", "generated")


def placeholders(value: Any) -> set[str]:
    """Every value name a structure refers to, at any depth.

    Literals inside a fallback chain are dropped: they need nothing to exist.
    """
    if isinstance(value, str):
        names: set[str] = set()
        for chain in PLACEHOLDER.findall(value):
            names.update(part for part in chain.split("|") if not part.startswith("'"))
        return names
    if isinstance(value, dict):
        return set().union(*(placeholders(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(placeholders(v) for v in value)) if value else set()
    return set()


def normalise(manifest: dict[str, Any]) -> dict[str, Any]:
    """Fix the two ways "required" ends up wrong, mechanically.

    A field that belongs to an authentication variant is required by that
    variant, never on its own — Cloudflare's four mutually exclusive
    credentials would otherwise produce a form nobody can fill in. And a field
    with a default can always be satisfied, so it is never required either.
    """
    in_variant = {
        name
        for variant in manifest.get("auth", {}).get("one_of", [])
        for name in variant["fields"]
    }

    for field in manifest.get("fields", []):
        if field["id"] in in_variant or "default" in field:
            field.pop("required", None)

    return manifest


def build(src_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifests: dict[str, dict[str, Any]] = {}

    for src_path in sorted(src_dir.glob("*.yaml")):
        identifier = src_path.stem
        manifest = yaml.safe_load(src_path.read_text(encoding="utf-8")) or {}

        for reserved in RESERVED_IN_SRC:
            manifest.pop(reserved, None)

        manifest = {"schema_version": SCHEMA_VERSION, "id": identifier, **manifest}
        manifest["generated"] = {"generated_at": generated_at, "source": "src"}
        manifests[identifier] = normalise(manifest)

    return manifests


def _fields_hidden_in_mode(
    manifest: dict[str, Any], mode_field: str | None, mode_id: Any
) -> set[str]:
    """Field IDs this manifest's own "when" conditions hide when mode_id is active.

    Only conditions on the field named by mode_field count — a manifest with
    modes is expected to gate its per-mode fields on exactly that field, the
    same way OVH already gates its two auth blocks on "mode". A field with no
    "when", or one that depends on some other field entirely, is never hidden
    by this and stays available to every mode.
    """
    if mode_field is None:
        return set()
    hidden = set()
    for field in manifest.get("fields", []):
        condition = field.get("when")
        if condition and condition.get("field") == mode_field and condition.get("equals") != mode_id:
            hidden.add(field["id"])
    return hidden


def _validate_native_call(
    identifier: str,
    label: str,
    blocks: dict[str, Any],
    known: set[str],
    field_ids: set[str],
    problems: list[str],
) -> None:
    """The placeholder/lookup/create checks for one request/lookup/create/bindings

    set. `blocks` is either the manifest itself (the default mode) or one
    entry of `modes` — both carry the same four keys, read directly rather
    than assuming which container it is. `known` is what is available before
    this call's own bindings and lookup steps add to it; `field_ids` is only
    used to spell out what a provider's form actually offers when a
    placeholder cannot be resolved.
    """
    bindings = blocks.get("bindings") or {}
    for name, rule in bindings.items():
        if rule["from"] not in known:
            problems.append(
                f"{identifier}{label}: binding {name!r} reads {rule['from']!r}, which nothing supplies"
            )
    known = known | set(bindings)

    for index, step in enumerate(blocks.get("lookup") or []):
        for name in sorted(placeholders(step) - known):
            problems.append(
                f"{identifier}{label}: lookup step {index + 1} uses {{{name}}}, which nothing "
                f"supplies at that point"
            )
        known = known | {step["into"]}

    for section in ("request", "create"):
        block = blocks.get(section)
        if block is None:
            continue
        for name in sorted(placeholders(block) - known):
            problems.append(
                f"{identifier}{label}: {section} uses {{{name}}}, which is neither a field on "
                f"this provider's form, nor a value the updater supplies, nor anything "
                f"a lookup binds (fields: {', '.join(sorted(field_ids)) or 'none'})"
            )

    wants_create = any((step.get("on_missing") == "create")
                       for step in blocks.get("lookup") or [])
    if wants_create and not blocks.get("create"):
        problems.append(
            f"{identifier}{label}: a lookup says to create the record when it is missing, "
            f"but there is no create block that says how"
        )
    if blocks.get("create") and not wants_create:
        problems.append(
            f"{identifier}{label}: there is a create block but no lookup asks for it"
        )


def validate(
    manifests: dict[str, dict[str, Any]],
    schema: dict[str, Any],
    adapter_dir: pathlib.Path,
) -> list[str]:
    """Schema validation plus the checks a schema cannot express."""
    validator = SchemaValidator(schema)
    problems: list[str] = []

    for identifier, manifest in sorted(manifests.items()):
        for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
            location = "/".join(str(part) for part in error.path) or "(root)"
            problems.append(f"{identifier}: {location}: {error.message}")

        if "engine" not in manifest or "fields" not in manifest:
            continue  # the schema already said so; further checks would be noise

        engine = manifest["engine"]
        adapter = engine.get("adapter")
        field_ids = {field["id"] for field in manifest["fields"]}
        modes = manifest.get("modes")
        mode_field_name = manifest.get("mode_field")

        # mode_field/modes have to describe one consistent choice: a select
        # field whose options are exactly the alternatives (the manifest's
        # own top-level blocks are always one of them, implicitly, and never
        # repeated as a modes entry) — otherwise resolve() would have no way
        # to tell which mode a record without a stored value should fall back
        # to, or the wizard would offer an option that selects nothing.
        default_mode_id: Any = None
        if mode_field_name is not None:
            mode_field_obj = next(
                (f for f in manifest["fields"] if f["id"] == mode_field_name), None
            )
            if mode_field_obj is None:
                problems.append(f"{identifier}: mode_field {mode_field_name!r} names no field")
            else:
                if mode_field_obj.get("type") != "select":
                    problems.append(
                        f"{identifier}: mode_field {mode_field_name!r} must be a select field, "
                        f"not {mode_field_obj.get('type')!r}"
                    )
                default_mode_id = mode_field_obj.get("default")
                mode_ids = set((modes or {}).keys())
                option_values = {option["value"] for option in mode_field_obj.get("options", [])}
                if default_mode_id is None:
                    problems.append(
                        f"{identifier}: mode_field {mode_field_name!r} needs a default — the "
                        f"mode a record gets when nothing overrides it"
                    )
                elif default_mode_id in mode_ids:
                    problems.append(
                        f"{identifier}: mode_field {mode_field_name!r}'s default "
                        f"{default_mode_id!r} must not also be a key of modes — the default is "
                        f"the manifest's own top-level blocks, implicit, never one of modes"
                    )
                expected = mode_ids | ({default_mode_id} if default_mode_id is not None else set())
                if option_values != expected:
                    problems.append(
                        f"{identifier}: mode_field {mode_field_name!r} options "
                        f"{sorted(map(str, option_values))} must be exactly modes plus the "
                        f"default ({sorted(map(str, expected))})"
                    )

        if adapter == "native":
            hidden = _fields_hidden_in_mode(manifest, mode_field_name, default_mode_id)
            known = (field_ids - hidden) | RUNTIME_VALUES
            _validate_native_call(identifier, "", manifest, known, field_ids - hidden, problems)

            for mode_id, mode_block in (modes or {}).items():
                hidden = _fields_hidden_in_mode(manifest, mode_field_name, mode_id)
                known = (field_ids - hidden) | RUNTIME_VALUES
                _validate_native_call(
                    identifier, f" mode {mode_id!r}", mode_block, known, field_ids - hidden, problems
                )
        elif adapter == "python":
            module = engine.get("module")
            if module and not (adapter_dir / f"{module}.py").is_file():
                problems.append(
                    f"{identifier}: engine.module {module!r} has no file at "
                    f"{adapter_dir.name}/{module}.py"
                )
            if modes:
                problems.append(f"{identifier}: modes require adapter: native")
        elif adapter == "unported":
            if "request" in manifest or "lookup" in manifest or modes:
                problems.append(
                    f"{identifier}: an unported provider must not carry a request block — "
                    f"either it is ported and the adapter says so, or it is not"
                )

        # An auth variant naming a field that does not exist renders an empty
        # step in the wizard.
        for variant in manifest.get("auth", {}).get("one_of", []):
            for name in variant["fields"]:
                if name not in field_ids:
                    problems.append(
                        f"{identifier}: auth variant {variant['id']!r} names unknown field {name!r}"
                    )

        # A "when" condition pointing at a missing field means the dependent
        # field can never appear — and one pointing at mode_field but naming a
        # value that is neither a mode nor the default is the same failure in
        # a typo's clothing: equally never shown, just harder to notice.
        for field in manifest["fields"]:
            condition = field.get("when")
            if not condition:
                continue
            if condition["field"] not in field_ids:
                problems.append(
                    f"{identifier}: field {field['id']!r} depends on unknown "
                    f"field {condition['field']!r}"
                )
            elif condition["field"] == mode_field_name:
                valid = set((modes or {}).keys())
                if default_mode_id is not None:
                    valid = valid | {default_mode_id}
                if condition["equals"] not in valid:
                    problems.append(
                        f"{identifier}: field {field['id']!r} is shown only when "
                        f"{condition['field']!r} == {condition['equals']!r}, which is not a "
                        f"mode this provider has"
                    )

    return problems


def strip_provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    """A manifest without the bookkeeping that changes on every run.

    Comparing two manifests for equality is only meaningful without it — the
    timestamp differs by construction and says nothing about the content.
    """
    return {key: value for key, value in manifest.items() if key != "generated"}


def dump(manifest: dict[str, Any]) -> str:
    header = (
        "# Generated by tools/manifest_merge.py — do not edit.\n"
        f"# The source is providers/src/{manifest['id']}.yaml\n"
    )
    body = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100)
    return header + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = pathlib.Path(__file__).resolve().parent.parent
    parser.add_argument("--src", type=pathlib.Path, default=root / "dnsmith/providers/src")
    parser.add_argument("--out", type=pathlib.Path, default=root / "dnsmith/providers")
    parser.add_argument("--schema", type=pathlib.Path,
                        default=root / "schemas/provider-manifest-v1.json")
    parser.add_argument("--adapters", type=pathlib.Path,
                        default=root / "dnsmith/hub/dnsmith_hub/adapters/providers")
    parser.add_argument("--check", action="store_true",
                        help="do not write; fail if the committed manifests are stale")
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    manifests = build(args.src)

    problems = validate(manifests, schema, args.adapters)
    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    # A manifest whose source file is gone. Nothing below would ever look at
    # it, because everything here is driven by providers/src/ - so it would
    # sit in providers/ unnoticed, get copied into the image by the Dockerfile
    # and be loaded by the registry at runtime, without ever passing the
    # schema or the placeholder check again. gen_docs.py has handled this case
    # all along.
    orphans = sorted(
        path.stem for path in args.out.glob("*.yaml") if path.stem not in manifests
    )

    stale: list[str] = []
    for identifier, manifest in sorted(manifests.items()):
        target = args.out / f"{identifier}.yaml"
        text = dump(manifest)
        current = target.read_text(encoding="utf-8") if target.is_file() else ""

        if args.check:
            # generated_at changes on every run and would make every manifest
            # look stale, so the comparison ignores it.
            if _without_timestamp(current) != _without_timestamp(text):
                stale.append(identifier)
            continue

        # Only write when something other than the timestamp changed. Otherwise
        # a run over one edited source file produces 64 changed files and
        # buries the one real change in the diff.
        if _without_timestamp(current) != _without_timestamp(text):
            target.write_text(text, encoding="utf-8", newline="\n")

    if not args.check and orphans:
        # Deleting is the one irreversible thing this tool does, so it refuses
        # to do it wholesale. An empty or mistyped --src makes EVERY manifest
        # look orphaned; without this guard a single wrong path would wipe the
        # provider catalogue, and build()/validate() would report nothing
        # amiss because an empty source set has no problems.
        if not manifests:
            print("no source files found - refusing to touch providers/", file=sys.stderr)
            return 1
        if len(orphans) > len(manifests):
            print(f"{len(orphans)} manifests without a source file, but only "
                  f"{len(manifests)} source files - refusing to delete that many. "
                  "Check --src.", file=sys.stderr)
            return 1
        for identifier in orphans:
            (args.out / f"{identifier}.yaml").unlink()
            print(f"removed {identifier}.yaml (no source file)")

    if args.check:
        if orphans:
            print("manifests without a source file: " + ", ".join(orphans), file=sys.stderr)
        if stale:
            print("stale manifests: " + ", ".join(stale), file=sys.stderr)
        if orphans or stale:
            return 1
        print(f"{len(manifests)} manifests up to date.")
        return 0

    tiers: dict[str, int] = {}
    for manifest in manifests.values():
        tiers[manifest["engine"]["adapter"]] = tiers.get(manifest["engine"]["adapter"], 0) + 1
    summary = ", ".join(f"{count}x {adapter}" for adapter, count in sorted(tiers.items()))
    print(f"{len(manifests)} manifests written ({summary}).")
    return 0


def _without_timestamp(text: str) -> str:
    return re.sub(r"^\s*generated_at:.*$", "", text, flags=re.M)


if __name__ == "__main__":
    raise SystemExit(main())
