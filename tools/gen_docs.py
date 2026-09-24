#!/usr/bin/env python3
"""Generate the provider documentation from the provider manifests.

WHY THIS IS GENERATED AND NOT WRITTEN

Every fact a provider page would state — which credentials exist, what each
one is, where the user gets it, whether IPv6 works, what the TTL limits are —
already lives in dnsmith/providers/*.yaml, because the form is built from it.
Writing the same facts a second time in prose would guarantee only one thing:
that the two drift apart, and that the page keeps telling users to paste their
account password long after the form learned better.

So the manifests stay the single source, and these pages are a view of them.
Edit providers/src/*.yaml, run this, commit the result.

    python3 tools/gen_docs.py            write docs/providers/
    python3 tools/gen_docs.py --check    fail if the pages are out of date

The text here is deliberately DNSmith's own, written from each provider's own
API documentation. Descriptions copied from elsewhere have already cost this
project real broken forms — mutually exclusive credentials listed as all
compulsory, hetzner's optional ttl marked required, dyn documented without a
password. Prose written once, from the source, is cheaper than prose corrected
forever.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFESTS = ROOT / "dnsmith" / "providers"
OUT = ROOT / "docs" / "providers"

CATEGORY_LABELS = {
    "free_ddns": "kostenlos",
    "commercial_ddns": "kommerziell",
    "dns_provider": "DNS-Anbieter",
    "cloud_dns": "Cloud-DNS",
    "registrar": "Registrar",
    "german": "deutschsprachig",
    "ipv6_focused": "IPv6-orientiert",
    "dyndns2_compatible": "DynDNS2",
    "generic": "generisch",
}

TYPE_LABELS = {
    "text": "Text",
    "secret": "Zugangsdaten",
    "multiline_secret": "Zugangsdaten (mehrzeilig)",
    "boolean": "Ja/Nein",
    "integer": "Zahl",
    "select": "Auswahl",
    "email": "E-Mail",
    "hostname": "Hostname",
    "domain": "Domain",
    "url": "URL",
    "ipv6_prefix": "IPv6-Präfix",
}

HEADER = "<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->\n"


def load() -> list[dict]:
    providers = []
    for path in sorted(MANIFESTS.glob("*.yaml")):
        providers.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return sorted(providers, key=lambda m: m["name"].lower())


def one_line(value) -> str:
    """Collapse a folded YAML string to one line."""
    return " ".join(str(value).split()) if value else ""


def capability_lines(manifest: dict) -> list[str]:
    caps = manifest["capabilities"]
    lines = []

    versions = []
    if caps.get("ipv4"):
        versions.append("IPv4")
    if caps.get("ipv6"):
        versions.append("IPv6")
    lines.append("| IP-Versionen | " + (" und ".join(versions) or "—") + " |")

    if caps.get("ipv4") and not caps.get("ipv6"):
        # The one case that silently disappoints: an AAAA record that never
        # updates, with nothing anywhere saying why.
        lines.append("| Hinweis | Dieser Anbieter kann **kein IPv6**. |")

    for key, label in (
        ("ipv6_suffix", "IPv6-Suffix"),
        ("wildcard", "Wildcard-Einträge"),
        ("ttl", "TTL einstellbar"),
        ("proxy", "Proxy-Schalter"),
        ("multiple_records", "mehrere Einträge je Domain"),
    ):
        if key in caps:
            lines.append(f"| {label} | {'ja' if caps[key] else 'nein'} |")

    return lines


def field_rows(manifest: dict) -> list[str]:
    in_variant = {
        name
        for variant in (manifest.get("auth") or {}).get("one_of", [])
        for name in variant["fields"]
    }

    rows = []
    for field in manifest["fields"]:
        if field.get("required"):
            need = "erforderlich"
        elif field["id"] in in_variant:
            need = "je nach Verfahren"
        else:
            need = "optional"

        when = field.get("when")
        if when:
            need += f" (nur bei {when['field']} = {when['equals']})"

        help_text = one_line(field.get("help")) or "—"

        rules = field.get("validate") or {}
        limits = []
        if "min" in rules:
            limits.append(f"min. {rules['min']}")
        if "max" in rules:
            limits.append(f"max. {rules['max']}")
        if limits:
            help_text += f" ({', '.join(limits)})"

        if "default" in field and field["default"] not in (None, ""):
            # Ein Ja/Nein-Feld mit "Vorgabe: `False`" zeigt Pythons Schreibweise,
            # nicht die des Formulars.
            shown_default = field["default"]
            if field["type"] == "boolean":
                shown_default = "ja" if shown_default else "nein"
            default = f"Vorgabe: `{shown_default}`."
            # Ohne Erklärung steht dort ein Gedankenstrich; daran noch einen
            # Satz zu hängen ergibt "— Vorgabe: `x`."
            help_text = default if help_text == "—" else f"{help_text} {default}"

        # Die Form des Wertes ist oft die eigentliche Antwort ("32 Hex-Zeichen",
        # "beginnt mit flux_live_"). Sie steckt im Platzhalter des Formulars
        # oder im Beispiel des Manifests — beides stand bisher nirgends auf der
        # Seite. Der Platzhalter gewinnt: er ist feldgenau gepflegt.
        shape = field.get("placeholder") or (manifest.get("example") or {}).get(field["id"])
        if shape not in (None, ""):
            example = f"Beispiel: `{shape}`."
            help_text = example if help_text == "—" else f"{help_text} {example}"

        rows.append(
            f"| `{field['id']}` | {field['label']} | "
            f"{TYPE_LABELS.get(field['type'], field['type'])} | {need} | {help_text} |"
        )
    return rows


def mode_lines(manifest: dict) -> list[str]:
    """The alternatives modes/mode_field describe, if this provider has any.

    Their labels live on mode_field's own select field, the same field the
    form itself renders the chooser from — so this, like the rest of the
    page, only ever repeats what the manifest already says once.
    """
    mode_field_id = manifest.get("mode_field")
    if not mode_field_id:
        return []
    field = next((f for f in manifest["fields"] if f["id"] == mode_field_id), None)
    if field is None:
        return []

    default = field.get("default")
    lines = [
        "## Verfahren\n",
        "Dieser Anbieter bietet mehr als einen Weg, den Eintrag zu aktualisieren. "
        f"Welche Felder zu welchem gehören, steht dort als \"nur bei "
        f"{mode_field_id} = ...\".\n",
    ]
    for option in field.get("options", []):
        value = option["value"]
        label = option.get("label", str(value))
        suffix = " _(Vorgabe)_" if value == default else ""
        lines.append(f"- **{label}**{suffix}")
    lines.append("")
    return lines


def provenance(generated: dict) -> list[str]:
    """Wie alt ist das hier? Die erste Frage bei einer Anbieter-Doku.

    Die Antwort steht im Manifest unter ``generated:`` und stand bisher auf
    keiner Seite. Provider, die DNSmith selbst ausführt, haben keinen
    Upstream-Stand — die bekommen nur das Datum.
    """
    stamp = (generated.get("generated_at") or "")[:10]
    if not stamp:
        return []
    year, month, day = stamp.split("-")
    line = f"Stand: {day}.{month}.{year}"
    commit = generated.get("upstream_commit")
    if commit:
        line += f", Engine-Stand `{commit[:12]}`"
    return ["---\n", line + "."]


def page(manifest: dict) -> str:
    out = [HEADER, f"# {manifest['name']}\n"]

    if manifest.get("description"):
        out.append(one_line(manifest["description"]) + "\n")

    if manifest.get("website"):
        out.append(f"Website: <{manifest['website']}>\n")

    categories = [CATEGORY_LABELS.get(c, c) for c in manifest.get("categories", [])]
    if categories:
        out.append("Einordnung: " + ", ".join(categories) + "\n")

    out.append("## Was der Anbieter kann\n")
    out.append("| | |")
    out.append("|---|---|")
    out.extend(capability_lines(manifest))
    out.append("")

    out.extend(mode_lines(manifest))

    variants = (manifest.get("auth") or {}).get("one_of", [])
    if variants:
        out.append("## Anmeldeverfahren\n")
        out.append(
            "Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — "
            "du füllst genau einen aus.\n"
        )
        for variant in variants:
            marks = []
            if variant.get("recommended"):
                marks.append("empfohlen")
            if variant.get("deprecated"):
                marks.append("veraltet")
            suffix = f" _({', '.join(marks)})_" if marks else ""
            out.append(f"**{variant['label']}**{suffix}")
            out.append("")
            fields = ", ".join(f"`{name}`" for name in variant["fields"])
            out.append(f"Felder: {fields}")
            out.append("")
            if variant.get("hint"):
                out.append(one_line(variant["hint"]))
                out.append("")

    out.append("## Felder\n")
    out.append("| Feld | Beschriftung | Typ | Nötig | Bedeutung |")
    out.append("|---|---|---|---|---|")
    out.extend(field_rows(manifest))
    out.append("")

    if manifest.get("rate_limit"):
        limit = manifest["rate_limit"]
        out.append("## Ratenbegrenzung\n")
        if limit.get("note"):
            out.append(one_line(limit["note"]))
            out.append("")
        if limit.get("min_interval"):
            out.append(f"Kürzestes sinnvolles Intervall: {limit['min_interval']}.")
            out.append("")

    notes = manifest.get("notes") or []
    if notes:
        # Ohne Überschrift hingen diese Absätze unter "Ratenbegrenzung" und
        # lasen sich wie ein Teil davon — dabei steht hier oft das Wichtigste
        # der Seite, etwa dass der Hostname auf duckdns.org enden muss.
        out.append("## Hinweise\n")
        for note in notes:
            out.append(f"> {one_line(note)}\n")

    # Kein "Technisches"-Abschnitt: welcher Engine-Provider intern ausgeführt
    # wird und wo dessen Upstream-Doku liegt, beantwortet keine Frage, die
    # jemand vor diesem Formular hat. Beides steht weiterhin im Manifest
    # (engine.upstream_id, documentation) — nur nicht auf der Seite.
    out.extend(provenance(manifest.get("generated") or {}))

    return "\n".join(out).rstrip() + "\n"


def index(providers: list[dict]) -> str:
    # The count is derived, never typed: a provider added upstream changes it
    # on the next run. Generic entries carry the "generic" category — they are
    # the ones that cover whatever has no page of its own.
    generic = sum(1 for p in providers if "generic" in (p.get("categories") or []))
    specific = len(providers) - generic
    out = [
        HEADER,
        "# Anbieter\n",
        f"DNSmith kennt {len(providers)} Anbieter: {specific} anbieterspezifische "
        f"und {generic} generische Einträge, die alles abdecken, was hier nicht "
        "eigens aufgeführt ist.\n",
        "Diese Seiten werden aus `dnsmith/providers/*.yaml` erzeugt — derselben "
        "Quelle, aus der die Oberfläche ihre Formulare baut. Sie können deshalb "
        "nicht auseinanderlaufen.\n",
        "| Anbieter | Einordnung | IPv6 | Zugangsdaten |",
        "|---|---|---|---|",
    ]

    for manifest in providers:
        categories = ", ".join(
            CATEGORY_LABELS.get(c, c) for c in manifest.get("categories", [])
        )
        ipv6 = "ja" if manifest["capabilities"].get("ipv6") else "**nein**"
        credentials = [
            field["label"]
            for field in manifest["fields"]
            if field["type"] in ("secret", "multiline_secret")
        ]
        link = f"[{manifest['name']}]({manifest['id']}.md)"
        out.append(
            f"| {link} | {categories or '—'} | {ipv6} | "
            f"{', '.join(credentials) or '—'} |"
        )

    out.append("")
    out.append(
        "Bei 35 dieser Anbieter ist das Passwort **nicht** das Konto-Passwort, "
        "sondern ein eigens erzeugtes Update-Passwort oder ein Token. Auf welcher "
        "Seite das gilt, steht dort jeweils beim Feld."
    )
    return "\n".join(out).rstrip() + "\n"


def render(providers: list[dict]) -> dict[str, str]:
    pages = {f"{manifest['id']}.md": page(manifest) for manifest in providers}
    pages["README.md"] = index(providers)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit non-zero if the committed pages differ",
    )
    args = parser.parse_args()

    pages = render(load())

    if args.check:
        stale = []
        for name, text in pages.items():
            path = OUT / name
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        # A page for a provider that no longer exists is just as wrong as a
        # stale one, and far easier to miss.
        if OUT.is_dir():
            for path in OUT.glob("*.md"):
                if path.name not in pages:
                    stale.append(f"{path.name} (Anbieter existiert nicht mehr)")
        if stale:
            print("Doku ist nicht aktuell: " + ", ".join(sorted(stale)), file=sys.stderr)
            print("Abhilfe: python3 tools/gen_docs.py", file=sys.stderr)
            return 1
        print(f"{len(pages)} Seiten sind aktuell")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.md"):
        if path.name not in pages:
            path.unlink()
    for name, text in pages.items():
        # newline="\n" ist Absicht: ohne das schreibt Python unter Windows
        # CRLF und unter Linux LF, und jede Seite steht nach einem Lauf auf
        # der anderen Plattform als geändert da, ohne es zu sein.
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(pages)} Seiten nach {OUT} geschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
