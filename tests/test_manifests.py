"""Contract tests for the provider manifests.

A manifest is now the whole provider: the form, the documentation page, and —
for most of the catalogue — the update call itself. The failure these catch
has changed shape but not kind. It used to be an upstream rename that DNSmith
kept writing the old name for; it is now a request block naming a value that
nothing supplies. Both stop a user's updates silently, and neither shows up
as a crash, so it has to show up here instead.

Written against unittest rather than pytest so they run with nothing
installed. pytest picks them up unchanged if the project adds it later.

Run with:  python3 -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_docs  # noqa: E402
import manifest_merge  # noqa: E402

SCHEMA_PATH = ROOT / "schemas/provider-manifest-v1.json"
SRC_DIR = ROOT / "dnsmith/providers/src"
MANIFEST_DIR = ROOT / "dnsmith/providers"

# German suspended compounds ("DNS- und Netzwerkdienste") legitimately end a
# word on a hyphen. Everything else that does is a broken compound.
SUSPENDING_CONJUNCTIONS = {"und", "oder", "bzw", "beziehungsweise", "sowie"}


def walk_strings(value, path=""):
    """Every string in a manifest, with the path it sits at."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f"{path}[{index}]")


class ManifestTestCase(unittest.TestCase):
    """Base class: loads everything once for the whole file."""

    schema: dict
    manifests: dict
    committed: dict
    adapters: pathlib.Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.manifests = manifest_merge.build(SRC_DIR)
        cls.adapters = ROOT / "dnsmith/hub/dnsmith_hub/adapters/providers"
        cls.committed = {
            path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted(MANIFEST_DIR.glob("*.yaml"))
        }

    def check(self, manifests=None):
        return manifest_merge.validate(
            self.manifests if manifests is None else manifests, self.schema, self.adapters
        )


class TestContract(ManifestTestCase):
    """The manifests must describe something DNSmith can actually perform."""

    def test_every_manifest_satisfies_the_contract(self):
        problems = self.check()
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_source_file_produced_a_manifest(self):
        sources = {path.stem for path in SRC_DIR.glob("*.yaml")}
        self.assertEqual(sorted(sources - set(self.manifests)), [])

    def test_committed_manifests_are_up_to_date(self):
        """Guards against someone hand-editing providers/*.yaml."""
        for identifier, manifest in self.manifests.items():
            with self.subTest(provider=identifier):
                self.assertIn(identifier, self.committed, f"{identifier}.yaml was never generated")
                self.assertEqual(
                    manifest_merge.strip_provenance(self.committed[identifier]),
                    manifest_merge.strip_provenance(manifest),
                    f"{identifier}.yaml is stale; run tools/manifest_merge.py",
                )


class TestContractActuallyFails(ManifestTestCase):
    """A check that cannot fail is not a check.

    Each of these breaks something deliberately and asserts that the
    validation notices.
    """

    def test_a_request_naming_an_unknown_value_is_rejected(self):
        """The scenario this file exists for, in its new shape.

        A provider's request asks for {api_token} while the form collects
        "token". Nothing would crash: the request would simply go out with an
        empty credential, and every record on that provider would start
        failing authentication with no error anywhere in DNSmith itself.
        """
        broken = copy.deepcopy(self.manifests)
        broken["dyndns2"]["engine"] = {"adapter": "native", "protocol": "http"}
        broken["dyndns2"]["request"] = {
            "url": "https://example.org/update",
            "params": {"token": "{api_token}"},
        }

        problems = self.check(broken)

        self.assertTrue(
            any("api_token" in problem for problem in problems),
            "a request naming a value no field supplies must be reported",
        )

    def test_runtime_values_are_allowed_in_a_request(self):
        """The other half of the same check: {ipv4} is not an unknown field."""
        ok = copy.deepcopy(self.manifests)
        ok["dyndns2"]["engine"] = {"adapter": "native", "protocol": "http"}
        ok["dyndns2"]["request"] = {
            "url": "https://example.org/update",
            "params": {"myip": "{ipv4}", "hostname": "{hostname}"},
        }

        self.assertEqual([p for p in self.check(ok) if "dyndns2" in p], [])

    def test_a_python_adapter_without_a_module_file_is_rejected(self):
        broken = copy.deepcopy(self.manifests)
        broken["duckdns"]["engine"] = {"adapter": "python", "module": "no_such_module"}
        broken["duckdns"].pop("request", None)

        problems = self.check(broken)

        self.assertTrue(any("no_such_module" in problem for problem in problems))

    def test_an_unported_provider_carrying_a_request_is_rejected(self):
        """Half-ported is the state that would lie to the user.

        The UI greys out an unported provider. One that also carries a request
        block is claiming both at once, and whichever the UI believes, the
        other is wrong.
        """
        broken = copy.deepcopy(self.manifests)
        broken["duckdns"]["engine"] = {"adapter": "unported"}
        broken["duckdns"]["request"] = {"url": "https://example.org/update"}

        problems = self.check(broken)

        self.assertTrue(any("duckdns" in problem for problem in problems))

    def test_auth_variant_with_unknown_field_is_rejected(self):
        broken = copy.deepcopy(self.manifests)
        broken["cloudflare"]["auth"]["one_of"][0]["fields"] = ["nonexistent_field"]

        problems = self.check(broken)

        self.assertTrue(any("nonexistent_field" in problem for problem in problems))

    def test_dangling_when_condition_is_rejected(self):
        broken = copy.deepcopy(self.manifests)
        broken["custom_http"]["fields"][1]["when"] = {"field": "no_such_field", "equals": "x"}

        problems = self.check(broken)

        self.assertTrue(any("no_such_field" in problem for problem in problems))

    def test_schema_violation_is_rejected(self):
        broken = copy.deepcopy(self.manifests)
        broken["duckdns"]["fields"][0]["type"] = "not_a_field_type"

        problems = self.check(broken)

        self.assertTrue(any("duckdns" in problem for problem in problems))


class TestManifestProperties(ManifestTestCase):
    """Properties that must hold for every provider, overlaid or not."""

    def test_credentials_are_never_plain_text_fields(self):
        """A token rendered as a normal text input is a shoulder-surfing bug."""
        offenders = []
        for identifier, manifest in self.manifests.items():
            for field in manifest["fields"]:
                looks_secret = field["id"] in manifest_merge.SECRET_FIELDS
                visible_on_purpose = field["id"] in manifest_merge.VISIBLE_OVERRIDES
                if looks_secret and not visible_on_purpose:
                    if field["type"] not in ("secret", "multiline_secret"):
                        offenders.append(f"{identifier}.{field['id']} is {field['type']}")
        self.assertEqual(offenders, [], offenders)

    def test_no_field_is_both_required_and_defaulted(self):
        """A field with a default can always be satisfied, so requiring it is noise."""
        offenders = [
            f"{identifier}.{field['id']}"
            for identifier, manifest in self.manifests.items()
            for field in manifest["fields"]
            if field.get("required") and "default" in field
        ]
        self.assertEqual(offenders, [], offenders)

    def test_auth_variant_fields_are_not_unconditionally_required(self):
        """Cloudflare's docs list alternative credentials as all compulsory.

        Taken at face value that yields a form nobody can complete, because
        token and email+key exclude each other. The merge tool has to undo
        it.
        """
        offenders = []
        for identifier, manifest in self.manifests.items():
            in_variant = {
                name
                for variant in manifest.get("auth", {}).get("one_of", [])
                for name in variant["fields"]
            }
            for field in manifest["fields"]:
                if field["id"] in in_variant and field.get("required"):
                    offenders.append(f"{identifier}.{field['id']}")
        self.assertEqual(offenders, [], offenders)

    def test_select_fields_offer_their_own_default(self):
        offenders = []
        for identifier, manifest in self.manifests.items():
            for field in manifest["fields"]:
                if field["type"] != "select" or "default" not in field:
                    continue
                values = {option["value"] for option in field["options"]}
                if field["default"] not in values:
                    offenders.append(
                        f"{identifier}.{field['id']}: default {field['default']!r} not in {values}"
                    )
        self.assertEqual(offenders, [], offenders)

    def test_ipv4_only_providers_are_marked_as_such(self):
        """Today that is Namecheap and nothing else.

        The list used to be derived from the Go source. It is now an assertion
        about the manifests, which means adding an IPv4-only provider has to
        be a deliberate edit here rather than something that slips through and
        surfaces as a user's AAAA record quietly never updating.
        """
        reported = {
            identifier
            for identifier, manifest in self.manifests.items()
            if not manifest["capabilities"]["ipv6"]
        }
        self.assertEqual(reported, {"namecheap"})

    def test_native_providers_declare_an_implementation(self):
        native = {
            identifier: manifest
            for identifier, manifest in self.manifests.items()
            if manifest["engine"]["adapter"] == "native"
        }
        for identifier, manifest in native.items():
            with self.subTest(provider=identifier):
                self.assertIn(
                    manifest["engine"].get("protocol"),
                    ("dyndns2", "http", "custom_http"),
                    f"{identifier} is native and needs a protocol",
                )

    def test_only_the_generic_providers_lack_a_request(self):
        """Everything else has to say what it sends.

        A native provider without a request block would fall through to the
        code path meant for the two providers whose endpoint the user types
        in — and then fail on a field that provider does not have.
        """
        without = {
            identifier
            for identifier, manifest in self.manifests.items()
            if manifest["engine"]["adapter"] == "native" and not manifest.get("request")
        }
        self.assertEqual(
            without,
            {"dyndns2", "custom_http"},
            "the two generic providers are what make the catalogue open-ended",
        )

    def test_examples_carry_no_plausible_real_credentials(self):
        """Examples come from upstream docs and must stay obviously fake."""
        suspicious = []
        for identifier, manifest in self.manifests.items():
            for key, value in (manifest.get("example") or {}).items():
                if key in manifest_merge.SECRET_FIELDS and len(str(value)) > 40:
                    suspicious.append(f"{identifier}.{key} looks like a real credential")
        self.assertEqual(suspicious, [], suspicious)

    def test_every_credential_is_explained(self):
        """A bare "Password" label is a support ticket waiting to happen.

        For a good third of these providers the value is NOT the account
        password but a separately generated update key — Namecheap, STRATO,
        Infomaniak, Hurricane Electric, easyDNS, ZoneEdit and more. A user who
        types their login password gets an authentication failure and nothing
        that explains it. So every credential has to carry either its own help
        text or an auth-variant hint that covers it.
        """
        unexplained = []
        for identifier, manifest in self.manifests.items():
            covered = {
                name
                for variant in manifest.get("auth", {}).get("one_of", [])
                if variant.get("hint")
                for name in variant["fields"]
            }
            for field in manifest["fields"]:
                if field["type"] not in ("secret", "multiline_secret"):
                    continue
                if field.get("help") or field["id"] in covered:
                    continue
                unexplained.append(f"{identifier}.{field['id']}")
        self.assertEqual(
            unexplained,
            [],
            "credentials with no explanation: " + ", ".join(unexplained),
        )

    def test_mutually_exclusive_credentials_are_modelled_as_such(self):
        """Upstream's doc tables list alternatives as all "compulsory".

        Taken literally that produced forms nobody could complete: spdyn
        demanding a token AND a username AND a password, ovh demanding both
        the DynHost pair and all three API keys, gigahostno demanding an API
        key AND the email login. Each provider below was read in the Go source
        and must stay expressed as alternatives — either auth.one_of, or
        fields gated behind a `when` on a mode selector.
        """
        for identifier in ("spdyn", "ovh", "gigahostno", "gandi", "dyn", "cloudflare"):
            with self.subTest(provider=identifier):
                manifest = self.manifests[identifier]
                has_variants = bool(manifest.get("auth", {}).get("one_of"))
                gated = any(field.get("when") for field in manifest["fields"])
                self.assertTrue(
                    has_variants or gated,
                    f"{identifier} has mutually exclusive credentials upstream "
                    "but offers no alternative in the form",
                )

    def test_ttl_bounds_match_the_engine(self):
        """Five providers reject a TTL outside their range — at engine start.

        Without the same bounds in the form, a user types 30 for Bunny, the
        record saves cleanly, and the failure appears minutes later as a
        provider-wide engine error that names neither the field nor the
        limit. These numbers are the minTTL/maxTTL constants read out of each
        provider's Go source.
        """
        expected = {
            "bunny": (60, 3600),
            "hetznercloud": (60, None),
            "name.com": (300, None),
            "namesilo": (3600, 2592001),
            "spaceship": (60, 3600),
        }
        for identifier, (low, high) in expected.items():
            with self.subTest(provider=identifier):
                field = next(
                    field for field in self.manifests[identifier]["fields"]
                    if field["id"] == "ttl"
                )
                rules = field.get("validate") or {}
                self.assertEqual(rules.get("min"), low)
                self.assertEqual(rules.get("max"), high)

    def test_no_placeholder_merely_restates_its_field(self):
        """A placeholder reading "username" under a label reading "Benutzername".

        Upstream's examples are literal placeholders — twenty-one visible
        fields carried one. They fill the single slot that could have shown
        the shape of the value, and they teach people to ignore the grey text
        everywhere, including where it carries a 32-character hex ID.
        """
        offenders = []
        for identifier, manifest in self.manifests.items():
            example = manifest.get("example") or {}
            for field in manifest["fields"]:
                value = field.get("placeholder") or example.get(field["id"])
                if value is None:
                    continue
                if manifest_merge.is_empty_example(field["id"], value):
                    offenders.append(f"{identifier}.{field['id']} = {value!r}")
        self.assertEqual(offenders, [], offenders)

    def test_no_line_break_splits_a_compound_word(self):
        """A folded source-file scalar that breaks after a hyphen.

        YAML folds every line break in a ">-" block into a space. Break the
        line after the hyphen of a compound and the space lands inside the
        word: "mehrere DDNS-\n  Dienste" is read back as "mehrere DDNS-
        Dienste", and that is what the form and the generated page show. Four
        of these shipped before anyone noticed, because the source file reads
        correctly — only the folded result is wrong.
        """
        pattern = re.compile(r"\w+-\s+(\w+)")
        offenders = []
        for identifier, manifest in self.manifests.items():
            for path, text in walk_strings(manifest):
                for match in pattern.finditer(text):
                    if match.group(1).lower() in SUSPENDING_CONJUNCTIONS:
                        continue
                    offenders.append(f"{identifier}{path}: {match.group(0)!r}")
        self.assertEqual(
            offenders,
            [],
            "broken compounds (move the line break in the source file): " + "; ".join(offenders),
        )

    def test_every_provider_offers_at_least_one_way_in(self):
        """A provider with no fields and no auth variants cannot be configured."""
        offenders = [
            identifier
            for identifier, manifest in self.manifests.items()
            if not manifest["fields"]
        ]
        self.assertEqual(offenders, [], offenders)


class TestDocs(ManifestTestCase):
    """The provider pages are a view of the manifests, not a second copy."""

    def test_committed_pages_are_up_to_date(self):
        """Guards the failure this generator exists to prevent.

        Documentation written by hand next to a machine-readable source drifts
        silently: the form learns that Namecheap's password is not the account
        password, the page keeps saying it is, and the page is what people
        find in a search engine.
        """
        rendered = gen_docs.render(gen_docs.load())
        out = gen_docs.OUT

        stale = []
        for name, text in rendered.items():
            path = out / name
            if not path.is_file():
                stale.append(f"{name} fehlt")
            elif path.read_text(encoding="utf-8") != text:
                stale.append(f"{name} ist veraltet")
        for path in out.glob("*.md"):
            if path.name not in rendered:
                stale.append(f"{path.name} gehört zu keinem Anbieter mehr")

        self.assertEqual(stale, [], "run python3 tools/gen_docs.py: " + "; ".join(stale))

    def test_every_provider_has_a_page(self):
        rendered = gen_docs.render(gen_docs.load())
        for identifier in self.manifests:
            self.assertIn(f"{identifier}.md", rendered)

    def test_no_manifest_points_at_upstream_documentation(self):
        """The pages and the form are DNSmith's own text, not a link out.

        Upstream's provider docs are wrong in places this project already had
        to correct, and the form linked to them under the label
        "Dokumentation des Anbieters" — which they never were.
        """
        offenders = [
            identifier
            for identifier, manifest in self.manifests.items()
            if manifest.get("documentation")
        ]
        self.assertEqual(offenders, [], offenders)


if __name__ == "__main__":
    unittest.main(verbosity=2)
