"""Tests for the DNSmith hub.

Three things get the most attention here, because they are the three that
would hurt most if they were wrong:

- Secrets. Every path out of the hub is checked for leakage: API responses,
  exports, logs, engine status, error messages.
- The SSRF guard. Every category of non-public address, plus the two bypasses
  that defeat naive implementations.
- The record ID. It is derived independently by the hub and the engine; if the
  two ever disagree, records silently stop being addressable. The expected
  values below were produced by running the Go implementation.

unittest rather than pytest, so they run with nothing installed.

Run with:  python3 -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import ipaddress
import json
import io
import logging
import os
import socket
import pathlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dnsmith/hub"))

# Diese Suite braucht die Laufzeitabhängigkeiten des Hubs. Fehlen sie, wird
# sie übersprungen statt mit einem ImportError abzubrechen: ein roter Lauf auf
# einem Rechner ohne pydantic sagt nichts über den Code aus, und wer ihn sieht,
# gewöhnt sich an rote Läufe. Was zu tun ist, steht in tests/README.md.
try:
    import httpx  # noqa: F401
    import pydantic  # noqa: F401
    import starlette  # noqa: F401
except ImportError as _missing:  # pragma: no cover
    raise unittest.SkipTest(
        f"Abhängigkeit fehlt ({_missing.name}); siehe tests/README.md"
    ) from _missing

from dnsmith_hub import redact, ssrf  # noqa: E402
from dnsmith_hub.adapters import native  # noqa: E402
from dnsmith_hub.adapters.base import AdapterError, RecordStatus, UpdateState  # noqa: E402
from dnsmith_hub.errors import explain  # noqa: E402
from dnsmith_hub.publicip import PublicIPResolver, _parse as parse_public_ip  # noqa: E402
from dnsmith_hub.scheduler import Scheduler  # noqa: E402
from dnsmith_hub.models import IPVersion, build_fqdn, derive_record_id  # noqa: E402
from dnsmith_hub.registry import (  # noqa: E402
    Registry,
    normalise_values,
    apply_defaults,
    ValidationProblem,
    build_form,
    split_values,
    validate_values,
)
from dnsmith_hub.secrets import SecretStore  # noqa: E402
from dnsmith_hub.service import Service  # noqa: E402
from dnsmith_hub.store import ConfigStore, ConfigUnreadable, DuplicateRecord  # noqa: E402

PROVIDERS = ROOT / "dnsmith/providers"


def load_registry() -> Registry:
    registry = Registry(PROVIDERS)
    registry.load()
    return registry


# ---------------------------------------------------------------------------
# Record identity
# ---------------------------------------------------------------------------


class TestRecordID(unittest.TestCase):
    """The hub and the engine must derive the same ID, independently.

    These vectors come from running the Go implementation in
    engine/overlay/internal/api/ids.go. If a change here makes them fail, the
    change is wrong — or the Go side has to change with it.
    """

    VECTORS = [
        (("cloudflare", "example.com", "home", "ipv4", ""), "c8dd186324a05feb"),
        (("duckdns", "home.duckdns.org", "@", "ipv4 or ipv6", ""), "27d19d6172ff1d1c"),
        (("ipv64", "haus.ipv64.net", "@", "ipv6", "::1/64"), "d7b3c991dbcc6f1a"),
        # Cosmetic differences must not change the identity.
        (("Cloudflare", "EXAMPLE.com.", " home ", "ipv4", ""), "c8dd186324a05feb"),
        # Non-ASCII: Go hashes byte lengths, so Python must too.
        (("duckdns", "münchen.example", "haus", "ipv4", ""), "b824a29271a3bdbb"),
    ]

    def test_matches_the_go_implementation(self):
        for arguments, expected in self.VECTORS:
            with self.subTest(arguments=arguments):
                self.assertEqual(derive_record_id(*arguments), expected)

    def test_every_identity_field_changes_the_id(self):
        base = ("duckdns", "example.com", "home", "ipv4", "")
        variants = [
            ("dynu", "example.com", "home", "ipv4", ""),
            ("duckdns", "other.com", "home", "ipv4", ""),
            ("duckdns", "example.com", "vpn", "ipv4", ""),
            ("duckdns", "example.com", "home", "ipv6", ""),
            ("duckdns", "example.com", "home", "ipv4", "::1/64"),
        ]
        ids = {derive_record_id(*base)}
        for variant in variants:
            identifier = derive_record_id(*variant)
            self.assertNotIn(identifier, ids, f"{variant} collided")
            ids.add(identifier)

    def test_field_boundaries_cannot_be_forged(self):
        first = derive_record_id("duckdns", "a|b", "c", "ipv4", "")
        second = derive_record_id("duckdns", "a", "b|c", "ipv4", "")
        self.assertNotEqual(first, second)

    def test_build_fqdn_matches_the_engine(self):
        self.assertEqual(build_fqdn("home", "example.com"), "home.example.com")
        self.assertEqual(build_fqdn("@", "example.com"), "example.com")
        self.assertEqual(build_fqdn("", "example.com"), "example.com")
        self.assertEqual(build_fqdn("home", "example.com."), "home.example.com")


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


class TestAddressClassification(unittest.TestCase):
    def test_public_addresses_are_allowed(self):
        for address in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1111"):
            with self.subTest(address=address):
                self.assertTrue(ssrf.is_public_address(ipaddress.ip_address(address)))

    def test_documentation_ranges_are_refused(self):
        """RFC 5737 addresses exist for examples and route nowhere.

        Python classifies them as private, and refusing them is right: a URL
        pointing at one is a copied-and-not-edited example, and telling the
        user so beats a connection timeout.
        """
        for address in ("203.0.113.9", "198.51.100.1", "192.0.2.1"):
            with self.subTest(address=address):
                self.assertFalse(ssrf.is_public_address(ipaddress.ip_address(address)))

    def test_every_non_public_category_is_refused(self):
        cases = {
            "private v4": "192.168.1.1",
            "private v4 (10)": "10.0.0.1",
            "private v4 (172)": "172.16.0.1",
            "loopback v4": "127.0.0.1",
            "link local": "169.254.1.1",
            "cloud metadata": "169.254.169.254",
            "cgnat": "100.64.0.1",
            "multicast": "224.0.0.1",
            "unspecified": "0.0.0.0",
            "loopback v6": "::1",
            "unique local v6": "fd00::1",
            "link local v6": "fe80::1",
        }
        for name, address in cases.items():
            with self.subTest(case=name):
                self.assertFalse(ssrf.is_public_address(ipaddress.ip_address(address)))

    def test_ipv4_tunnelled_through_ipv6_is_refused(self):
        """The bypass a naive check misses.

        ::ffff:192.168.1.1 is an IPv6 address by type and a private IPv4 one
        in effect. Judging it as IPv6 would let it straight through.
        """
        self.assertFalse(ssrf.is_public_address(ipaddress.ip_address("::ffff:192.168.1.1")))
        self.assertFalse(ssrf.is_public_address(ipaddress.ip_address("::ffff:127.0.0.1")))


class TestURLGuard(unittest.TestCase):
    @staticmethod
    def resolver_for(*addresses: str):
        def resolve(host, port, **_kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
                for address in addresses
            ]

        return resolve

    def test_accepts_a_public_https_url(self):
        guarded = ssrf.check_url(
            "https://dyndns.example.com/nic/update", resolver=self.resolver_for("93.184.216.34")
        )
        self.assertEqual(guarded.host, "dyndns.example.com")
        self.assertEqual(guarded.port, 443)
        self.assertEqual(str(guarded.pinned_address), "93.184.216.34")

    def test_http_is_refused_by_default(self):
        with self.assertRaises(ssrf.URLRejected) as caught:
            ssrf.check_url("http://example.com/update", resolver=self.resolver_for("93.184.216.34"))
        self.assertEqual(caught.exception.code, "scheme_not_allowed")

    def test_credentials_in_the_url_are_refused(self):
        with self.assertRaises(ssrf.URLRejected) as caught:
            ssrf.check_url(
                "https://user:secret@example.com/update",
                resolver=self.resolver_for("93.184.216.34"),
            )
        self.assertEqual(caught.exception.code, "credentials_in_url")
        # The refusal itself must not repeat the password back.
        self.assertNotIn("secret", caught.exception.message)

    def test_a_private_literal_is_refused(self):
        for url in (
            "https://192.168.1.1/update",
            "https://127.0.0.1:8123/update",
            "https://[::1]/update",
            "https://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ssrf.URLRejected) as caught:
                    ssrf.check_url(url)
                self.assertEqual(caught.exception.code, "address_not_public")

    def test_a_hostname_resolving_inward_is_refused(self):
        with self.assertRaises(ssrf.URLRejected) as caught:
            ssrf.check_url(
                "https://sneaky.example.com/update", resolver=self.resolver_for("192.168.1.10")
            )
        self.assertEqual(caught.exception.code, "address_not_public")
        self.assertIn("192.168.1.10", caught.exception.message)

    def test_one_bad_address_in_a_round_robin_is_enough(self):
        """The second bypass a naive check misses.

        Checking only the first answer would let a record that alternates
        between a public and a private address through on the good draw, and
        reach the private one on the next attempt.
        """
        with self.assertRaises(ssrf.URLRejected) as caught:
            ssrf.check_url(
                "https://mixed.example.com/update",
                resolver=self.resolver_for("93.184.216.34", "10.0.0.5"),
            )
        self.assertEqual(caught.exception.code, "address_not_public")

    def test_the_approved_address_is_returned_for_pinning(self):
        """Resolving twice is the rebinding hole; the caller connects to this."""
        guarded = ssrf.check_url(
            "https://example.com/update",
            resolver=self.resolver_for("93.184.216.34", "93.184.216.35"),
        )
        self.assertEqual(len(guarded.pinned_addresses), 2)
        self.assertEqual(str(guarded.pinned_address), "93.184.216.34")

    def test_validation_without_resolution_still_checks_scheme(self):
        guarded = ssrf.check_url("https://example.com/update", resolve=False)
        self.assertEqual(guarded.pinned_addresses, ())
        with self.assertRaises(ssrf.URLRejected):
            ssrf.check_url("ftp://example.com/update", resolve=False)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def honours_file_modes(directory: Path) -> bool:
    """Can this filesystem actually store POSIX permission bits?

    A Windows-backed filesystem — a OneDrive folder reached from WSL, a
    Docker bind mount off an NTFS drive — accepts os.chmod and ignores it.
    The two tests below would then fail forever, for a reason that has
    nothing to do with the code: they assert something the disk cannot do.

    Two permanently red tests are worse than two missing ones. People stop
    reading a red run, and the next real failure hides behind them. So the
    capability is measured once, here, and the tests say plainly when they
    step aside.
    """
    probe = directory / ".mode-probe"
    try:
        probe.touch()
        os.chmod(probe, 0o600)
        return stat.S_IMODE(probe.stat().st_mode) == 0o600
    except OSError:  # pragma: no cover - a filesystem that refuses outright
        return False
    finally:
        probe.unlink(missing_ok=True)


class TestSecretStore(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "secrets.json"
        self.store = SecretStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def skip_without_file_modes(self):
        if not honours_file_modes(Path(self.directory.name)):
            self.skipTest(
                "Dieses Dateisystem speichert keine POSIX-Rechte "
                "(Windows-Ablage, etwa OneDrive über WSL). Im Add-on-Container, "
                "wo die Datei tatsächlich liegt, greifen sie."
            )

    def test_file_is_created_private(self):
        self.skip_without_file_modes()

        self.store.set_many("abc", {"token": "s3cret"})
        mode = stat.S_IMODE(self.path.stat().st_mode)
        self.assertEqual(mode, 0o600, f"expected 0600, got {oct(mode)}")

    def test_loose_permissions_are_repaired_on_load(self):
        self.skip_without_file_modes()

        self.store.set_many("abc", {"token": "s3cret"})
        os.chmod(self.path, 0o644)

        SecretStore(self.path).load()

        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_the_repair_is_attempted_whatever_the_filesystem_does_with_it(self):
        """The call has to happen even where the disk ignores it.

        Skipping the two tests above on such a filesystem must not mean the
        code path goes unchecked there — otherwise a rewrite that drops the
        chmod entirely would pass on exactly the machine somebody develops on.
        """
        self.store.set_many("abc", {"token": "s3cret"})
        # Loosen them first, so the repair has a reason to fire. Where the
        # filesystem ignores this, the mode it reports is loose anyway — which
        # is the situation the repair exists for.
        os.chmod(self.path, 0o644)

        seen = []
        real_chmod = os.chmod

        def recording(path, mode, *args, **kwargs):
            seen.append((str(path), mode))
            return real_chmod(path, mode, *args, **kwargs)

        os.chmod = recording
        try:
            SecretStore(self.path).load()
        finally:
            os.chmod = real_chmod

        self.assertTrue(
            any(str(self.path) == path and mode == 0o600 for path, mode in seen),
            f"kein chmod 600 auf die Datei versucht: {seen}",
        )

    def test_values_round_trip(self):
        self.store.set_many("abc", {"token": "s3cret", "key": "other"})
        reloaded = SecretStore(self.path)
        reloaded.load()
        self.assertEqual(reloaded.get("abc", "token"), "s3cret")
        self.assertEqual(sorted(reloaded.field_names("abc")), ["key", "token"])

    def test_an_empty_value_deletes(self):
        self.store.set_many("abc", {"token": "s3cret"})
        self.store.set_many("abc", {"token": ""})
        self.assertIsNone(self.store.get("abc", "token"))

    def test_an_absent_field_is_left_alone(self):
        """What makes an edit form work.

        The UI cannot prefill a secret input, so it submits it blank. That
        must mean "unchanged", not "delete".
        """
        self.store.set_many("abc", {"token": "s3cret", "key": "other"})
        self.store.set_many("abc", {"key": "changed"})
        self.assertEqual(self.store.get("abc", "token"), "s3cret")
        self.assertEqual(self.store.get("abc", "key"), "changed")

    def test_deleting_a_record_forgets_its_secrets(self):
        self.store.set_many("abc", {"token": "s3cret"})
        self.store.forget("abc")
        self.assertEqual(self.store.for_record("abc"), {})

    def test_orphans_are_prunable(self):
        self.store.set_many("keep", {"token": "a"})
        self.store.set_many("drop", {"token": "b"})
        orphans = self.store.retain_only({"keep"})
        self.assertEqual(orphans, ["drop"])
        self.assertEqual(self.store.for_record("drop"), {})

    def test_write_is_atomic(self):
        """No temporary file may survive a write."""
        self.store.set_many("abc", {"token": "s3cret"})
        leftovers = [p for p in Path(self.directory.name).iterdir() if p.name != "secrets.json"]
        self.assertEqual(leftovers, [])


class TestRedaction(unittest.TestCase):
    def setUp(self):
        self.redactor = redact.ValueRedactor()
        self.redactor.update({"super-secret-token", "another-credential"})

    def test_values_are_masked_anywhere_in_a_string(self):
        text = "update failed for super-secret-token at 12:00"
        self.assertNotIn("super-secret-token", self.redactor.redact(text))
        self.assertIn(redact.MASK, self.redactor.redact(text))

    def test_nested_structures_are_walked(self):
        payload = {"a": ["super-secret-token"], "b": {"c": "another-credential"}}
        cleaned = self.redactor.redact_structure(payload)
        self.assertEqual(cleaned["a"][0], redact.MASK)
        self.assertEqual(cleaned["b"]["c"], redact.MASK)

    def test_very_short_values_are_not_masked(self):
        """Masking a two-character secret would blank ordinary words."""
        redactor = redact.ValueRedactor()
        redactor.update({"ab"})
        self.assertEqual(redactor.redact("a cab drove by"), "a cab drove by")

    def test_a_percent_encoded_secret_is_also_masked(self):
        """httpx builds query strings itself, and encodes as it goes.

        A password like "Sch!Step84" never appears in a request URL the way
        it was typed - httpx turns "!" into "%21" - so a pattern built only
        from the literal value would miss it in any text that renders the
        finished URL (an error message, a future debug line).
        """
        redactor = redact.ValueRedactor()
        redactor.update({"Sch!Step84"})
        text = "GET https://example.test/update?password=Sch%21Step84"
        self.assertNotIn("Sch%21Step84", redactor.redact(text))
        self.assertIn(redact.MASK, redactor.redact(text))

    def test_the_log_filter_masks_messages_and_arguments(self):
        logger = logging.getLogger("dnsmith.test.redact")
        logger.handlers.clear()
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger.addHandler(Capture())
        logger.setLevel(logging.INFO)
        redact.install(logger, self.redactor)

        logger.info("token is super-secret-token")
        logger.info("token is %s", "another-credential")

        self.assertNotIn("super-secret-token", records[0].getMessage())
        self.assertNotIn("another-credential", records[1].getMessage())

    def test_the_filter_covers_the_wiring_the_add_on_actually_uses(self):
        """The two tests above install the filter on the logger they log to.

        Production does neither: every module logs on "dnsmith.hub", a CHILD
        of the logger the filter used to be installed on, and the output goes
        to a handler on the ROOT logger that basicConfig() created. A filter
        on an ancestor logger never sees those records - Logger.handle applies
        only its own filter, and callHandlers asks the handlers, not the
        loggers it passes. So the earlier tests pass while nothing is masked.

        This one reproduces the real wiring: root handler, child logger, and a
        third-party logger nobody thought about.
        """
        stream = io.StringIO()
        root = logging.getLogger()
        previous_handlers = root.handlers[:]
        previous_level = root.level
        root.handlers = [logging.StreamHandler(stream)]
        root.setLevel(logging.INFO)
        try:
            redact.install_everywhere(self.redactor)

            class NotAString:
                """What httpx passes for the URL: an object, not a str."""

                def __str__(self):
                    return "https://example.test/?token=super-secret-token"

            logging.getLogger("dnsmith.hub").warning(
                "update failed: %s", "super-secret-token")
            logging.getLogger("uvicorn.error").warning(
                "boot: %s", "another-credential")
            logging.getLogger("some.third.party").warning("GET %s", NotAString())

            written = stream.getvalue()
        finally:
            root.handlers = previous_handlers
            root.setLevel(previous_level)

        self.assertNotIn("super-secret-token", written)
        self.assertNotIn("another-credential", written)
        self.assertIn(redact.MASK, written)

    def test_noisy_http_loggers_are_quietened(self):
        """httpx logs the full URL on INFO, and the token lives in the URL.

        Masked or not, a line per request is noise - and one library change
        away from carrying something new.
        """
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.NOTSET)
        redact.install_everywhere(self.redactor)
        for name in ("httpx", "httpcore"):
            self.assertEqual(logging.getLogger(name).level, logging.WARNING, name)

    def test_the_log_filter_masks_exception_text(self):
        """The path that usually leaks: a traceback, not a log message."""
        logger = logging.getLogger("dnsmith.test.redact.exc")
        logger.handlers.clear()
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger.addHandler(Capture())
        logger.setLevel(logging.INFO)
        redact.install(logger, self.redactor)

        try:
            raise RuntimeError("request to https://x/?token=super-secret-token failed")
        except RuntimeError:
            logger.exception("update failed")

        rendered = records[0].getMessage()
        self.assertNotIn("super-secret-token", rendered)

    def test_the_log_filter_masks_a_chained_causes_text_too(self):
        """AdapterError is deliberately generic; the secret lives in `__cause__`.

        native.py raises `AdapterError("timeout", "...") from error`, where
        `error` is the original httpx exception. Checking only the top
        exception's text - which is what this filter used to do - would let
        a secret in the cause through untouched, because the cause is never
        rendered by anything upstream of the handler.
        """
        logger = logging.getLogger("dnsmith.test.redact.chain")
        logger.handlers.clear()
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger.addHandler(Capture())
        logger.setLevel(logging.INFO)
        redact.install(logger, self.redactor)

        try:
            try:
                raise ValueError("url carried another-credential")
            except ValueError as cause:
                raise RuntimeError("update failed") from cause
        except RuntimeError:
            logger.exception("generic failure")

        rendered = records[0].getMessage()
        self.assertNotIn("another-credential", rendered)
        self.assertIn(redact.MASK, rendered)


# ---------------------------------------------------------------------------
# Registry and form contract
# ---------------------------------------------------------------------------


class TestDefaults(unittest.TestCase):
    """A default that never reaches the engine is decoration."""

    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_an_untouched_default_is_filled_in(self):
        """Cloudflare's Go constructor rejects ttl == 0 with ErrTTLNotSet.

        So a record created by accepting the form as offered — TTL left
        alone — has to carry ttl=1 into storage, or the engine refuses the
        whole provider at startup and blames Cloudflare rather than the
        missing field.
        """
        provider = self.registry.get("cloudflare")

        filled = apply_defaults(provider, {"zone_identifier": "abc", "token": "t"})

        self.assertEqual(filled["ttl"], 1)
        self.assertIs(filled["proxied"], False)

    def test_a_supplied_value_is_left_alone(self):
        provider = self.registry.get("cloudflare")
        filled = apply_defaults(provider, {"ttl": 3600})
        self.assertEqual(filled["ttl"], 3600)

    def test_a_hidden_field_gets_no_default(self):
        """A field behind an unmet `when` belongs to a mode the user did not
        choose; filling it would configure that mode behind their back."""
        provider = self.registry.get("custom_http")
        hidden = [
            field for field in provider.fields
            if field.get("when") and "default" in field
        ]
        if not hidden:
            self.skipTest("no conditional field with a default to check")
        filled = apply_defaults(provider, {})
        for field in hidden:
            self.assertNotIn(field["id"], filled)


class TestDyn(unittest.TestCase):
    """dyn's credentials were the wrong way round.

    Upstream's Go provider reads client_key and falls back to the deprecated
    password only when client_key is empty. DNSmith used to require password
    and mark client_key as required while telling the user to leave it blank.
    """

    @classmethod
    def setUpClass(cls):
        cls.provider = load_registry().get("dyn")

    def test_neither_credential_is_unconditionally_required(self):
        for field in self.provider.fields:
            if field["id"] in ("client_key", "password"):
                self.assertFalse(field.get("required"), field["id"])

    def test_the_client_key_is_the_recommended_variant(self):
        variants = {variant["id"]: variant for variant in self.provider.auth_variants}
        self.assertTrue(variants["client_key"].get("recommended"))
        self.assertTrue(variants["password"].get("deprecated"))

    def test_the_client_key_alone_satisfies_the_form(self):
        validate_values(
            self.provider,
            {"username": "someone", "client_key": "k"},
            auth_variant="client_key",
        )


class TestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_every_manifest_loads(self):
        self.assertGreaterEqual(len(self.registry), 60)

    def test_summaries_report_no_logo_when_none_were_fetched(self):
        """The default state of a fresh checkout.

        Logos are fetched by tools/fetch-logos.sh and deliberately not
        committed, so every summary has to survive their absence — including
        the case where the directory does not exist at all.
        """
        registry = Registry(PROVIDERS, logo_dir=PROVIDERS / "no-such-directory")
        registry.load()
        self.assertTrue(all(summary["logo"] is None for summary in registry.summaries()))

    def test_a_fetched_logo_reaches_the_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            logos = pathlib.Path(directory)
            (logos / "duckdns.svg").write_text("<svg/>", encoding="utf-8")
            # A file for a provider that does not exist must not break loading.
            (logos / "not-a-provider.svg").write_text("<svg/>", encoding="utf-8")

            registry = Registry(PROVIDERS, logo_dir=logos)
            registry.load()

            summaries = {s["id"]: s for s in registry.summaries()}
            self.assertEqual(summaries["duckdns"]["logo"], "assets/logos/duckdns.svg")
            self.assertIsNone(summaries["cloudflare"]["logo"])
            # The URL must stay relative: a leading slash leaves the add-on
            # when Home Assistant serves it under an Ingress prefix.
            self.assertFalse(summaries["duckdns"]["logo"].startswith("/"))

    def test_a_vector_icon_wins_over_a_leftover_raster(self):
        """Favicons arrive as .ico, .png or .svg, and a re-fetch can leave two.

        Whichever is chosen has to be deterministic, or the picker changes
        appearance between restarts for no visible reason.
        """
        with tempfile.TemporaryDirectory() as directory:
            logos = pathlib.Path(directory)
            (logos / "duckdns.ico").write_bytes(b"\x00\x00\x01\x00")
            (logos / "duckdns.svg").write_text("<svg/>", encoding="utf-8")
            (logos / "ipv64.png").write_bytes(b"\x89PNG\r\n\x1a\n")

            registry = Registry(PROVIDERS, logo_dir=logos)
            registry.load()

            summaries = {s["id"]: s for s in registry.summaries()}
            self.assertEqual(summaries["duckdns"]["logo"], "assets/logos/duckdns.svg")
            self.assertEqual(summaries["ipv64"]["logo"], "assets/logos/ipv64.png")

    def test_search_matches_name_and_category(self):
        self.assertTrue(any(p.id == "duckdns" for p in self.registry.search("duck")))
        german = self.registry.search(category="german")
        self.assertTrue(any(p.id == "ipv64" for p in german))

    def test_form_has_no_provider_specific_code_path(self):
        """Every provider must render from the manifest alone."""
        for provider in self.registry.all():
            with self.subTest(provider=provider.id):
                form = build_form(provider)
                self.assertEqual(form["provider_id"], provider.id)
                self.assertTrue(form["ip_versions"], "a provider with no IP version is unusable")
                for field in form["fields"]:
                    self.assertIn("type", field)
                    self.assertIn("label", field)

    def test_ipv4_only_providers_do_not_offer_ipv6(self):
        offered = [v["value"] for v in build_form(self.registry.get("namecheap"))["ip_versions"]]
        self.assertEqual(offered, ["ipv4"])

    def test_secret_fields_are_flagged(self):
        form = build_form(self.registry.get("duckdns"))
        token = next(field for field in form["fields"] if field["id"] == "token")
        self.assertTrue(token["secret"])

    def test_a_secret_placeholder_cannot_be_mistaken_for_a_credential(self):
        """A shape hint is useful; something that looks filled in is not.

        DuckDNS's token is a UUID, and showing 0000...-0000 tells the user
        what to paste. A placeholder made of real-looking characters would
        instead suggest the field is already set.
        """
        allowed = set("0x•-– ")
        for provider in self.registry.all():
            for field in build_form(provider)["fields"]:
                placeholder = field.get("placeholder")
                if field["secret"] and placeholder:
                    with self.subTest(provider=provider.id, field=field["id"]):
                        self.assertTrue(
                            set(placeholder) <= allowed,
                            f"{provider.id}.{field['id']} placeholder {placeholder!r} "
                            f"looks like an actual credential",
                        )

    def test_secret_placeholders_never_come_from_the_upstream_example(self):
        for provider in self.registry.all():
            example = provider.manifest.get("example") or {}
            for field in build_form(provider)["fields"]:
                if field["secret"] and field.get("placeholder"):
                    with self.subTest(provider=provider.id, field=field["id"]):
                        self.assertNotEqual(field["placeholder"], str(example.get(field["id"])))

    def test_auth_variants_pick_the_recommended_default(self):
        form = build_form(self.registry.get("cloudflare"))
        self.assertEqual(form["auth"]["default"], "api_token")


class TestPastedUpdateURLs(unittest.TestCase):
    """Some providers hand out a URL, not a key.

    IPv64 shows its users a finished update URL with the key in a query
    parameter; FreeDNS puts the token in a path segment. Asking people to cut
    the right piece out of it is a step that exists only because the form is
    picky — and getting it wrong produces an authentication error that points
    at the credentials rather than at the paste.
    """

    def setUp(self):
        self.registry = load_registry()

    def normalise(self, provider_id, **values):
        return normalise_values(self.registry.get(provider_id), values)

    def test_a_pasted_ipv64_url_is_reduced_to_its_key(self):
        self.assertEqual(
            self.normalise("ipv64", key="https://ipv64.net/nic/update?key=abc123"),
            {"key": "abc123"},
        )

    def test_a_pasted_freedns_url_is_reduced_to_its_token(self):
        self.assertEqual(
            self.normalise("freedns", token="https://sync.afraid.org/u/tok123/"),
            {"token": "tok123"},
        )

    def test_a_plain_key_passes_through(self):
        self.assertEqual(self.normalise("ipv64", key="abc123"), {"key": "abc123"})

    def test_a_field_without_the_rule_is_never_touched(self):
        """A password that happens to look like a URL stays what it is."""
        pasted = "https://example.com/x?key=not-the-password"
        self.assertEqual(
            self.normalise("dynu", password=pasted)["password"], pasted
        )

    def test_a_url_without_the_expected_part_is_left_alone(self):
        """Better to fail validation on the paste than to store half of it."""
        pasted = "https://ipv64.net/nic/update"
        self.assertEqual(self.normalise("ipv64", key=pasted), {"key": pasted})

    def test_the_stored_record_holds_the_key_not_the_url(self):
        """The whole point: what reaches the provider must be the key."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)

        secrets = SecretStore(base / "secrets.json")
        store = ConfigStore(base / "config.json", secrets, self.registry)
        record = store.create_record(
            provider_id="ipv64",
            domain="example.com",
            owner="home",
            ip_version="ipv4",
            values={"key": "https://ipv64.net/nic/update?key=abc123"},
        )

        self.assertEqual(secrets.get(record.id, "key"), "abc123")


class TestValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_missing_required_field_is_reported(self):
        with self.assertRaises(ValidationProblem) as caught:
            validate_values(self.registry.get("duckdns"), {})
        self.assertIn("token", caught.exception.problems)

    def test_unknown_field_is_reported(self):
        with self.assertRaises(ValidationProblem) as caught:
            validate_values(self.registry.get("duckdns"), {"token": "x", "surprise": "y"})
        self.assertIn("surprise", caught.exception.problems)

    def test_a_stored_secret_may_be_left_blank_on_edit(self):
        validate_values(self.registry.get("duckdns"), {}, known_secrets={"token"})

    def test_auth_variant_decides_what_is_required(self):
        cloudflare = self.registry.get("cloudflare")

        # The token variant needs the token, not the e-mail and key.
        validate_values(
            cloudflare,
            {"zone_identifier": "0" * 32, "token": "abc"},
            auth_variant="api_token",
        )

        with self.assertRaises(ValidationProblem) as caught:
            validate_values(
                cloudflare, {"zone_identifier": "0" * 32}, auth_variant="api_token"
            )
        self.assertIn("token", caught.exception.problems)

        # The global-key variant needs both of its fields instead.
        validate_values(
            cloudflare,
            {"zone_identifier": "0" * 32, "email": "a@b.de", "key": "abc"},
            auth_variant="global_key",
        )

    def test_pattern_validation_runs(self):
        with self.assertRaises(ValidationProblem) as caught:
            validate_values(
                self.registry.get("cloudflare"),
                {"zone_identifier": "not-a-zone-id", "token": "abc"},
                auth_variant="api_token",
            )
        self.assertIn("zone_identifier", caught.exception.problems)

    def test_integer_bounds_are_enforced(self):
        with self.assertRaises(ValidationProblem) as caught:
            validate_values(
                self.registry.get("cloudflare"),
                {"zone_identifier": "0" * 32, "token": "abc", "ttl": 999999},
                auth_variant="api_token",
            )
        self.assertIn("ttl", caught.exception.problems)

    def test_hidden_fields_are_not_required(self):
        """custom_http's basic-auth fields only exist once basic is chosen."""
        validate_values(
            self.registry.get("custom_http"),
            {"url": "https://example.com/update", "auth_mode": "none"},
        )

    def test_split_values_separates_secrets(self):
        plain, secret = split_values(
            self.registry.get("cloudflare"),
            {"zone_identifier": "0" * 32, "token": "abc", "proxied": True},
        )
        self.assertEqual(secret, {"token": "abc"})
        self.assertNotIn("token", plain)
        self.assertEqual(plain["proxied"], True)


# ---------------------------------------------------------------------------
# Engine configuration rendering
# ---------------------------------------------------------------------------


class StubCaller:
    """Stands in for HTTPCaller. Records what would have gone out."""

    def __init__(self, status: int = 200, body: str = "good") -> None:
        self.status = status
        self.body = body
        self.calls: list[dict] = []
        self.fail_with: AdapterError | None = None

    def call(self, url, **kwargs):
        if self.fail_with:
            raise self.fail_with
        self.calls.append({"url": url, **kwargs})
        return self.status, self.body


class StubSources:
    """A fixed pair of addresses, so nothing here touches the network.

    Stands in for AddressSources, which is what the scheduler asks: the
    settings decide per family whether an address comes from the internet,
    from a Home Assistant entity, or from a fixed value.
    """

    def __init__(self, ipv4="203.0.113.9", ipv6=None, **extra) -> None:
        from dnsmith_hub.adapters.base import PublicIP

        self.value = PublicIP(ipv4=ipv4, ipv6=ipv6, ipv4_source="stub",
                              fetched_at="2026-01-01T00:00:00Z", **extra)
        self.fail_with: AdapterError | None = None
        self.asked_with = []

    def get(self, settings=None, refresh: bool = False):
        self.asked_with.append(settings)
        if self.fail_with:
            raise self.fail_with
        return self.value


class HubTestCase(unittest.TestCase):
    """A complete hub over temporary files, with nothing that reaches out."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        base = Path(self.directory.name)

        self.registry = load_registry()
        self.secrets = SecretStore(base / "secrets.json")
        self.store = ConfigStore(base / "config.json", self.secrets, self.registry)
        self.caller = StubCaller()
        self.sources = StubSources()
        self.scheduler = Scheduler(
            registry=self.registry,
            store=self.store,
            secrets=self.secrets,
            native=native.NativeAdapter(caller=self.caller),
            sources=self.sources,
        )
        self.service = Service(
            registry=self.registry,
            store=self.store,
            secrets=self.secrets,
            scheduler=self.scheduler,
        )

    def tearDown(self):
        self.directory.cleanup()

    def add_duckdns(self, owner="@", domain="home.duckdns.org", token="s3cret-token-value"):
        return self.service.create_record(
            {
                "provider_id": "duckdns",
                "domain": domain,
                "owner": owner,
                "ip_version": "ipv4",
                "values": {"token": token},
            }
        )


    def mark_unported(self, provider_id="duckdns"):
        """Put one provider back into the transitional state.

        The state is by definition temporary — every phase empties it a little
        further — so a test that picked a real unported provider would break
        the moment that provider was ported. Flipping a known one in memory
        keeps the test about the state rather than about a provider.
        """
        manifest = self.registry.get(provider_id).manifest
        manifest["engine"] = {"adapter": "unported"}
        manifest.pop("request", None)

    def add_generic(self, domain="home.example.com", password="update-password", ip_version="ipv4"):
        """A record on a provider that is actually ported, for update tests."""
        return self.service.create_record(
            {
                "provider_id": "dyndns2",
                "domain": domain,
                "owner": "@",
                "ip_version": ip_version,
                "values": {
                    "server": "https://dyndns.example.org/nic/update",
                    "username": "u",
                    "password": password,
                },
            }
        )


class TestSecretsNeverLeak(HubTestCase):
    TOKEN = "extremely-secret-token-value"

    def test_not_in_the_record_payload(self):
        record = self.add_duckdns(token=self.TOKEN)
        payload = json.dumps(self.service.record_payload(record))
        self.assertNotIn(self.TOKEN, payload)
        self.assertTrue(json.loads(payload)["secrets"]["token"]["set"])

    def test_not_in_the_record_list(self):
        self.add_duckdns(token=self.TOKEN)
        self.assertNotIn(self.TOKEN, json.dumps(self.service.records_payload()))

    def test_not_in_the_stored_configuration(self):
        """The config file is the one users open, diff and paste into issues."""
        self.add_duckdns(token=self.TOKEN)
        self.assertNotIn(self.TOKEN, (Path(self.directory.name) / "config.json").read_text())

    def test_not_in_an_export_without_secrets(self):
        self.add_duckdns(token=self.TOKEN)
        self.assertNotIn(self.TOKEN, json.dumps(self.store.export()))

    def test_present_in_an_export_that_asked_for_them(self):
        self.add_duckdns(token=self.TOKEN)
        self.assertIn(self.TOKEN, json.dumps(self.store.export(include_secrets=True)))

    def test_the_redactor_knows_every_stored_value(self):
        self.add_duckdns(token=self.TOKEN)
        self.assertNotIn(self.TOKEN, self.service.redactor.redact(f"failed: {self.TOKEN}"))

    def test_it_reaches_the_request_and_nowhere_else(self):
        """The one place it must appear — and only there."""
        self.add_generic(password=self.TOKEN)
        self.service.force_update(None)

        sent = json.dumps(self.caller.calls)
        self.assertIn(self.TOKEN, sent)
        self.assertNotIn(self.TOKEN, json.dumps(self.service.records_payload()))


class TestUnreadableConfiguration(unittest.TestCase):
    """What happens when the stored configuration cannot be read.

    Before this it ended the process, so the add-on restarted every few
    seconds and the interface — the one thing that could have explained the
    problem — never came up. The rules now: start anyway, say why, and above
    all touch nothing.
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)

        self.path = base / "config.json"
        self.registry = load_registry()
        self.secrets = SecretStore(base / "secrets.json")
        self.secrets.set_many("0123456789abcdef", {"token": "keep-me"})

    def store_over(self, content: str):
        self.path.write_text(content, encoding="utf-8")
        store = ConfigStore(self.path, self.secrets, self.registry)
        store.load()
        return store

    def test_broken_json_does_not_raise(self):
        store = self.store_over("{not json")

        self.assertIsNotNone(store.load_error)
        self.assertEqual(store.records(), [])
        self.assertIn("JSON", store.load_error)

    def test_content_that_does_not_fit_the_model_does_not_raise(self):
        store = self.store_over('{"config_version": 2, "records": "not a list"}')
        self.assertIsNotNone(store.load_error)

    def test_a_newer_format_says_so_rather_than_guessing(self):
        store = self.store_over('{"config_version": 99, "records": []}')
        self.assertIn("neueren DNSmith-Version", store.load_error)

    def test_the_file_is_left_exactly_as_it_was(self):
        original = '{"config_version": 2, "records": "not a list"}'
        store = self.store_over(original)

        with self.assertRaises(ConfigUnreadable):
            store.save()

        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_credentials_are_not_tidied_away(self):
        """Every credential looks orphaned when no record could be read."""
        store = self.store_over("{not json")

        self.assertEqual(store.prune_orphaned_secrets(), [])
        self.assertEqual(self.secrets.get("0123456789abcdef", "token"), "keep-me")

    def test_a_readable_configuration_reports_no_error(self):
        store = self.store_over('{"config_version": 2, "settings": {}, "records": []}')
        self.assertIsNone(store.load_error)
        store.save()  # must not raise


class TestRecordLifecycle(HubTestCase):
    def test_duplicate_records_are_refused(self):
        self.add_duckdns()
        with self.assertRaises(DuplicateRecord):
            self.add_duckdns()

    def test_deleting_removes_the_record_and_its_secrets(self):
        record = self.add_duckdns()
        self.service.delete_record(record.id)

        self.assertEqual(self.store.records(), [])
        self.assertEqual(self.secrets.for_record(record.id), {})
        self.assertEqual(self.scheduler.statuses(), {})

    def test_editing_keeps_a_secret_left_blank(self):
        record = self.add_duckdns(token="original-token-value")
        self.store.update_record(record.id, values={}, label="Zuhause")

        self.assertEqual(self.secrets.get(record.id, "token"), "original-token-value")
        self.assertEqual(self.store.record(record.id).label, "Zuhause")

    def test_the_id_survives_a_reload_from_disk(self):
        record = self.add_duckdns()
        reopened = ConfigStore(
            Path(self.directory.name) / "config.json", self.secrets, self.registry
        )
        reopened.load()
        self.assertEqual([r.id for r in reopened.records()], [record.id])


class TestScheduler(HubTestCase):
    """The decisions that keep DNSmith from being rate-limited out.

    The interesting part of a DDNS client is not the HTTP call; it is knowing
    when not to make one.
    """

    def test_an_unchanged_address_is_not_sent_again(self):
        self.add_generic()

        self.scheduler.update_all()
        self.assertEqual(len(self.caller.calls), 1)

        # A second pass with the same address must send nothing.
        self.scheduler.tick()
        self.assertEqual(len(self.caller.calls), 1)

    def test_a_changed_address_is_sent(self):
        record = self.add_generic()
        self.scheduler.update_all()

        self.sources.value = type(self.sources.value)(
            ipv4="198.51.100.4", ipv6=None, ipv4_source="stub",
            fetched_at="2026-01-01T00:01:00Z")
        status = self.scheduler.update(record.id)

        self.assertEqual(len(self.caller.calls), 2)
        self.assertEqual(status.current_ipv4, "198.51.100.4")
        self.assertEqual(status.ip_change_count, 1)
        self.assertIn("203.0.113.9", status.previous_ips)

    def test_only_the_changed_family_enters_the_history(self):
        """A dual-stack record whose IPv4 changes must not also log the

        unchanged IPv6 as "previous" — that family never stopped being
        current.
        """
        self.sources = StubSources(ipv4="203.0.113.9", ipv6="2001:db8::1")
        self.scheduler.sources = self.sources
        record = self.add_generic(ip_version="dual_stack")
        self.scheduler.update_all()

        self.sources.value = type(self.sources.value)(
            ipv4="198.51.100.4", ipv6="2001:db8::1", ipv4_source="stub",
            fetched_at="2026-01-01T00:01:00Z")
        status = self.scheduler.update(record.id)

        self.assertIn("203.0.113.9", status.previous_ips)
        self.assertNotIn("2001:db8::1", status.previous_ips)

    def test_a_ban_stops_the_record_rather_than_retrying(self):
        """Retrying after "abuse" is how a client confirms the accusation."""
        record = self.add_generic()
        self.caller.body = "abuse"

        status = self.scheduler.update(record.id)

        self.assertEqual(status.state.value, "fail")
        self.assertEqual(status.error["code"], "banned")
        self.assertIsNotNone(status.banned_until)

        before = len(self.caller.calls)
        self.scheduler.tick()
        self.assertEqual(len(self.caller.calls), before)

    def test_a_failure_backs_off_instead_of_hammering(self):
        record = self.add_generic()
        self.caller.body = "dnserr"

        self.scheduler.update(record.id)
        before = len(self.caller.calls)
        self.scheduler.tick()

        self.assertEqual(len(self.caller.calls), before)

    def test_a_disabled_record_is_skipped(self):
        record = self.add_generic()
        self.store.update_record(record.id, enabled=False)

        self.scheduler.tick()

        self.assertEqual(self.caller.calls, [])

    def test_an_unported_provider_fails_with_a_usable_message(self):
        record = self.add_duckdns()
        self.mark_unported()

        status = self.scheduler.update(record.id)

        self.assertEqual(status.state.value, "fail")
        self.assertEqual(status.error["code"], "not_implemented")
        # The message has to name the way out, not just the problem.
        self.assertIn("DynDNS2", status.error["summary"])
        self.assertEqual(self.caller.calls, [])


class TestUpdateCooldown(HubTestCase):
    """The shortest gap allowed between two writes for the same record.

    The unchanged-address check already prevents most writes; this catches
    the other case — an address that keeps moving. Providers ban clients that
    write on every flap, so a minute of staleness is the cheaper mistake.
    """

    def move_address(self, ipv4):
        self.sources.value = type(self.sources.value)(
            ipv4=ipv4, ipv6=None, ipv4_source="stub", fetched_at="2026-01-01T00:00:00Z")

    def test_a_second_change_too_soon_is_held_back(self):
        record = self.add_generic()
        self.scheduler.update(record.id)
        self.assertEqual(len(self.caller.calls), 1)

        self.move_address("198.51.100.4")
        self.scheduler.tick()

        self.assertEqual(len(self.caller.calls), 1, "written again within the cooldown")

    def test_the_cooldown_is_what_holds_it_back_and_not_the_poll_interval(self):
        """The test above passes even with the cooldown switched off.

        A successful write schedules the next attempt one poll interval away,
        so tick() skips the record as "not due" and never reaches the cooldown
        at all. For a long time that hid the fact that the cooldown did
        nothing whatsoever: _last_write was read but never written, so
        _cooldown_remaining always returned zero.

        This asks the scheduler directly, with the interval out of the way.
        """
        clock = [1000.0]
        self.scheduler._clock = lambda: clock[0]  # noqa: SLF001

        record = self.add_generic()
        self.scheduler.update(record.id)
        self.assertEqual(len(self.caller.calls), 1)

        # Far enough that the poll interval is no longer the reason to wait,
        # but inside the five-minute cooldown.
        clock[0] += 299
        self.assertGreater(self.scheduler._cooldown_remaining(record), 0)  # noqa: SLF001

        self.move_address("198.51.100.4")
        self.scheduler.update(record.id, force=False)
        self.assertEqual(len(self.caller.calls), 1, "the cooldown did not hold it back")

        clock[0] += 2
        self.scheduler.update(record.id, force=False)
        self.assertEqual(len(self.caller.calls), 2, "still held back after the cooldown passed")

    def test_the_cooldown_branch_sets_a_next_attempt(self):
        """Holding a record back has to schedule it, not just skip it.

        This needs a cooldown LONGER than the poll interval. With the default
        five minutes for both, a record that just wrote is never due again
        before its cooldown has expired anyway - so the cooldown branch is
        unreachable and a test built on the defaults measures the interval
        while believing it measures the cooldown.

        Without a next attempt the record stays due and every pass re-evaluates
        it until the cooldown runs out. Cheap, but endless.
        """
        self.store.update_settings({"poll_interval": "5m", "update_cooldown": "1h"})
        clock = [1000.0]
        self.scheduler._clock = lambda: clock[0]  # noqa: SLF001

        record = self.add_generic()
        self.scheduler.update(record.id)
        self.assertEqual(len(self.caller.calls), 1)

        # Due by the interval, but well inside the hour-long cooldown.
        clock[0] += 301
        self.move_address("198.51.100.8")
        self.scheduler.tick()

        self.assertEqual(len(self.caller.calls), 1, "written inside the cooldown")
        deferred = self.scheduler._next_attempt[record.id]  # noqa: SLF001
        self.assertGreater(
            deferred, clock[0] + 3000,
            "held back without scheduling a next look - the record stays due "
            "and every pass re-evaluates it")

    def test_a_record_that_blows_up_does_not_take_the_pass_with_it(self):
        """One broken record used to end the whole pass, for good.

        _run handles AdapterError. Anything else - a URLRejected from a DNS
        hiccup, a KeyError from credentials a restored backup left behind -
        escaped tick(), and because the record never reached _schedule it
        stayed due forever and killed every later pass too.
        """
        first = self.add_generic(domain="a.example.com")
        second = self.add_generic(domain="b.example.com")

        original = self.scheduler._perform  # noqa: SLF001

        def explode(record, ipv4, ipv6):
            if record.id == first.id:
                raise RuntimeError("something nobody thought of")
            return original(record, ipv4, ipv6)

        self.scheduler._perform = explode  # noqa: SLF001
        self.move_address("198.51.100.9")

        results = self.scheduler.tick()

        self.assertEqual(len(results), 2, "the second record was never reached")
        broken = next(item for item in results if item.record_id == first.id)
        healthy = next(item for item in results if item.record_id == second.id)
        self.assertEqual(broken.state, UpdateState.FAIL)
        self.assertEqual(healthy.state, UpdateState.SUCCESS)
        # And it must not stay due for ever, or it poisons the next pass too.
        self.assertIn(first.id, self.scheduler._next_attempt)  # noqa: SLF001

    def test_the_change_goes_out_once_the_gap_has_passed(self):
        clock = [1000.0]
        self.scheduler._clock = lambda: clock[0]  # noqa: SLF001

        record = self.add_generic()
        self.scheduler.update(record.id)
        self.move_address("198.51.100.4")

        clock[0] += 301  # the default cooldown is five minutes
        self.scheduler.update(record.id, force=False)

        self.assertEqual(len(self.caller.calls), 2)

    def test_pressing_the_button_overrules_it(self):
        """The cooldown protects the provider from DNSmith, not from the user."""
        record = self.add_generic()
        self.scheduler.update(record.id)
        self.move_address("198.51.100.4")

        self.scheduler.update(record.id)

        self.assertEqual(len(self.caller.calls), 2)

    def test_a_failed_update_is_not_held_back_by_it(self):
        """A failure retries on the backoff schedule, not on the cooldown."""
        self.caller.body = "dnserr"
        record = self.add_generic()
        self.scheduler.update(record.id)

        self.caller.body = "good"
        self.move_address("198.51.100.4")
        self.scheduler.update(record.id, force=False)

        self.assertEqual(len(self.caller.calls), 2)


class TestDualStackOnOneAddressProviders(HubTestCase):
    """A provider with a single myip cannot hear about both families at once.

    The old engine kept two records per dual-stack entry. Here the manifest
    says which kind a provider is, and the scheduler makes the call twice.
    """

    def add_dual(self):
        return self.service.create_record({
            "provider_id": "dyndns2",
            "domain": "home.example.com",
            "owner": "@",
            "ip_version": "dual_stack",
            "values": {
                "server": "https://dyndns.example.org/nic/update",
                "username": "u",
                "password": "p",
            },
        })

    def test_both_families_are_sent(self):
        self.sources.value = type(self.sources.value)(
            ipv4="203.0.113.9", ipv6="2001:db8::1", ipv4_source="stub",
            fetched_at="2026-01-01T00:00:00Z")
        record = self.add_dual()

        status = self.scheduler.update(record.id)

        self.assertEqual(status.state.value, "success")
        self.assertEqual(status.current_ipv4, "203.0.113.9")
        self.assertEqual(status.current_ipv6, "2001:db8::1")


class StubSupervisor:
    """Stands in for Home Assistant."""

    def __init__(self, states=None, fail=None) -> None:
        self.states = states or {}
        self.fail = fail
        self.asked = []
        self.available = True

    def state(self, entity_id):
        from dnsmith_hub.publicip import SupervisorUnavailable

        self.asked.append(entity_id)
        if self.fail:
            raise SupervisorUnavailable(self.fail)
        if entity_id not in self.states:
            raise SupervisorUnavailable(f"Die Entität {entity_id} gibt es nicht.")
        return self.states[entity_id]


class StubHTTP:
    def __init__(self, ipv4="203.0.113.9", ipv6=None) -> None:
        from dnsmith_hub.adapters.base import PublicIP

        self.value = PublicIP(ipv4=ipv4, ipv6=ipv6, ipv4_source="ipv4.icanhazip.com")
        self.calls = 0

    def get(self, refresh=False):
        self.calls += 1
        return self.value


# Addresses that survive the public-address check. The documentation ranges
# (203.0.113.0/24, 198.51.100.0/24, 2001:db8::/32) do NOT: Python counts them
# as private, and DNSmith refuses a private address from any source, because
# one in public DNS is a misconfiguration whatever put it there. Tests about
# resolving therefore need addresses that look real.
GLOBAL_V4 = "93.184.216.34"
GLOBAL_V6 = "2606:2800:220:1:248:1893:25c8:1946"


class TestAddressSources(unittest.TestCase):
    """Where an address comes from.

    The interface promised for months that IPv6 could be read from a Home
    Assistant entity — in the very notice shown when no IPv6 was found. These
    tests are what makes that true rather than said.
    """

    def settings(self, **kwargs):
        from dnsmith_hub.models import GlobalSettings

        return GlobalSettings(**kwargs)

    def sources(self, supervisor=None, http=None):
        from dnsmith_hub.publicip import AddressSources

        return AddressSources(http=http or StubHTTP(), supervisor=supervisor or StubSupervisor())

    def test_auto_asks_the_internet(self):
        http = StubHTTP()
        address = self.sources(http=http).get(self.settings())

        self.assertEqual(address.ipv4, "203.0.113.9")
        self.assertEqual(http.calls, 1)

    def test_an_entity_is_read_for_the_family_that_asks_for_it(self):
        supervisor = StubSupervisor({"sensor.wan_v6": GLOBAL_V6})
        address = self.sources(supervisor=supervisor).get(self.settings(
            ip_source_v6={"mode": "ha_entity", "entity_id": "sensor.wan_v6"},
        ))

        self.assertEqual(address.ipv6, GLOBAL_V6)
        self.assertEqual(address.ipv6_source, "sensor.wan_v6")
        self.assertEqual(supervisor.asked, ["sensor.wan_v6"])

    def test_nothing_reaches_out_when_no_family_wants_it(self):
        """A setup reading both families from entities is offline by design."""
        http = StubHTTP()
        self.sources(
            http=http,
            supervisor=StubSupervisor({"sensor.wan_v4": GLOBAL_V4,
                                       "sensor.wan_v6": GLOBAL_V6}),
        ).get(self.settings(
            ip_source_v4={"mode": "ha_entity", "entity_id": "sensor.wan_v4"},
            ip_source_v6={"mode": "ha_entity", "entity_id": "sensor.wan_v6"},
        ))

        self.assertEqual(http.calls, 0)

    def test_an_unavailable_entity_yields_no_address_and_a_reason(self):
        """Leaving the record alone beats setting it to something wrong."""
        supervisor = StubSupervisor(fail="Die Entität sensor.wan_v6 hat gerade keinen Wert.")
        address = self.sources(supervisor=supervisor).get(self.settings(
            ip_source_v6={"mode": "ha_entity", "entity_id": "sensor.wan_v6"},
        ))

        self.assertIsNone(address.ipv6)
        self.assertIn("keinen Wert", address.ipv6_error)

    def test_an_entity_holding_something_else_is_reported_with_what_it_held(self):
        supervisor = StubSupervisor({"sensor.wan_v6": "verbunden"})
        address = self.sources(supervisor=supervisor).get(self.settings(
            ip_source_v6={"mode": "ha_entity", "entity_id": "sensor.wan_v6"},
        ))

        self.assertIsNone(address.ipv6)
        self.assertIn("verbunden", address.ipv6_error)

    def test_an_entity_with_the_wrong_family_is_refused(self):
        """An IPv4 address in the IPv6 slot would write a broken record."""
        supervisor = StubSupervisor({"sensor.wan": GLOBAL_V4})
        address = self.sources(supervisor=supervisor).get(self.settings(
            ip_source_v6={"mode": "ha_entity", "entity_id": "sensor.wan"},
        ))

        self.assertIsNone(address.ipv6)
        self.assertIn("IPv6", address.ipv6_error)

    def test_a_static_address_is_used_as_given(self):
        address = self.sources().get(self.settings(
            ip_source_v4={"mode": "static", "value": GLOBAL_V4},
        ))
        self.assertEqual(address.ipv4, GLOBAL_V4)

    def test_a_static_address_that_is_not_one_is_refused(self):
        address = self.sources().get(self.settings(
            ip_source_v4={"mode": "static", "value": "mein-anschluss"},
        ))
        self.assertIsNone(address.ipv4)
        self.assertIn("gültige", address.ipv4_error)

    def test_a_private_address_is_refused_wherever_it_came_from(self):
        """A LAN address in public DNS is broken, however it got there."""
        supervisor = StubSupervisor({"sensor.wan": "192.168.1.20"})
        address = self.sources(supervisor=supervisor).get(self.settings(
            ip_source_v4={"mode": "ha_entity", "entity_id": "sensor.wan"},
        ))
        self.assertIsNone(address.ipv4)
        self.assertIn("192.168.1.20", address.ipv4_error)

    def test_disabled_means_disabled(self):
        http = StubHTTP(ipv4="203.0.113.9")
        address = self.sources(http=http).get(self.settings(
            ip_source_v4={"mode": "disabled"},
        ))
        self.assertIsNone(address.ipv4)
        self.assertIsNone(address.ipv4_error)


class TestConfigMigration(unittest.TestCase):
    """Settings that were only ever written have to leave without breaking."""

    def test_dead_settings_are_dropped_on_load(self):
        from dnsmith_hub.store import migrate

        migrated = migrate({
            "config_version": 1,
            "settings": {
                "poll_interval": "5m",
                "resolver": None,
                "notifications": [],
                "ip_source_v6": {"mode": "prefix_suffix", "prefix_source": "x",
                                 "suffix": "::1", "http_providers": []},
            },
            "records": [],
        })

        settings = migrated["settings"]
        self.assertNotIn("resolver", settings)
        self.assertNotIn("notifications", settings)
        self.assertNotIn("prefix_source", settings["ip_source_v6"])
        # The mode did nothing, so the honest replacement is what the user
        # actually got.
        self.assertEqual(settings["ip_source_v6"]["mode"], "auto")
        self.assertEqual(migrated["config_version"], 3)

    def test_log_level_is_dropped_on_load(self):
        """log_level was settable via the API and persisted, but nothing ever

        read it back — configure_logging() only looks at the
        DNSMITH_LOG_LEVEL environment variable. Same situation as
        resolver/notifications above, same remedy.
        """
        from dnsmith_hub.store import migrate

        migrated = migrate({
            "config_version": 2,
            "settings": {"poll_interval": "5m", "log_level": "debug"},
            "records": [],
        })

        self.assertNotIn("log_level", migrated["settings"])
        self.assertEqual(migrated["config_version"], 3)

    def test_a_migrated_configuration_actually_loads(self):
        """extra="forbid" means a leftover key is not harmless."""
        from dnsmith_hub.models import DnsmithConfig
        from dnsmith_hub.store import migrate

        DnsmithConfig.model_validate(migrate({
            "config_version": 1,
            "settings": {"resolver": "1.1.1.1", "notifications": ["x"]},
            "records": [],
        }))


class TestErrorExplanations(unittest.TestCase):
    def test_every_engine_code_has_german_text(self):
        from dnsmith_hub.errors import MESSAGES

        engine_codes = {
            "auth", "account", "banned", "rate_limit", "not_found", "record_state",
            "config", "ip", "provider_response", "dns", "network", "timeout", "unknown",
        }
        self.assertTrue(engine_codes.issubset(set(MESSAGES)))

    def test_an_explanation_says_what_to_check(self):
        explained = explain({"code": "auth", "summary": "bad authentication"})
        self.assertTrue(explained["checks"], "an explanation with no next step is useless")
        self.assertEqual(explained["technical"], "bad authentication")

    def test_an_unknown_code_still_explains_something(self):
        explained = explain({"code": "something_new"})
        self.assertEqual(explained["code"], "something_new")
        self.assertTrue(explained["message"])

    def test_detail_is_redacted_when_a_redactor_is_given(self):
        """explain() feeds the API response, not a logger.

        The log filter is wired to loggers only; a provider whose response
        body happened to echo a stored credential in `detail` would reach the
        browser untouched unless this function redacts it itself.
        """
        redactor = redact.ValueRedactor()
        redactor.update({"super-secret-token"})

        explained = explain(
            {"code": "provider_response", "detail": "rejected token super-secret-token"},
            redactor=redactor,
        )

        self.assertNotIn("super-secret-token", explained["detail"])
        self.assertIn(redact.MASK, explained["detail"])

    def test_detail_is_unredacted_without_a_redactor(self):
        """No behaviour change for the existing unit-level callers."""
        explained = explain({"code": "provider_response", "detail": "plain text"})
        self.assertEqual(explained["detail"], "plain text")


# ---------------------------------------------------------------------------
# Native adapter
# ---------------------------------------------------------------------------


class TestDynDNS2Responses(unittest.TestCase):
    def test_the_protocol_vocabulary_is_interpreted(self):
        cases = {
            "good 203.0.113.9": (True, "success"),
            "nochg 203.0.113.9": (True, "up_to_date"),
            "badauth": (False, "auth"),
            "nohost": (False, "not_found"),
            "abuse": (False, "banned"),
            "911": (False, "provider_response"),
        }
        for body, (ok, code) in cases.items():
            with self.subTest(body=body):
                outcome = native.interpret_dyndns2(200, body)
                self.assertEqual(outcome.ok, ok)
                self.assertEqual(outcome.code, code)

    def test_nochg_counts_as_success(self):
        """"No change" is the normal answer, not a failure."""
        self.assertTrue(native.interpret_dyndns2(200, "nochg").ok)

    def test_http_401_is_treated_as_bad_credentials(self):
        """Several providers answer 401 rather than sending badauth."""
        outcome = native.interpret_dyndns2(401, "")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "auth")

    def test_an_unrecognised_body_is_not_silently_a_success(self):
        outcome = native.interpret_dyndns2(200, "<html>maintenance</html>")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "unknown")


class TestCustomHTTPResponses(unittest.TestCase):
    def test_status_mode_uses_the_status_code(self):
        self.assertTrue(native.interpret_custom(200, "anything", "status", "").ok)
        self.assertFalse(native.interpret_custom(500, "", "status", "").ok)

    def test_regex_mode_ignores_the_status_code(self):
        self.assertTrue(native.interpret_custom(200, "result: good", "regex", "good").ok)
        self.assertFalse(native.interpret_custom(200, "result: bad", "regex", "good").ok)

    def test_an_invalid_regex_is_reported_as_configuration(self):
        with self.assertRaises(AdapterError) as caught:
            native.interpret_custom(200, "x", "regex", "[unclosed")
        self.assertEqual(caught.exception.code, "config")


class TestNativeProbe(unittest.TestCase):
    def setUp(self):
        self.adapter = native.NativeAdapter()

    def test_a_private_url_is_refused(self):
        result = self.adapter.probe(
            {
                "protocol": "custom_http",
                "values": {"url": "https://192.168.1.1/update", "success_mode": "status"},
            },
            "validate",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "address_not_public")

    def test_missing_credentials_are_reported(self):
        result = self.adapter.probe(
            {
                "protocol": "dyndns2",
                "values": {"server": "https://dyndns.example.org/nic/update", "username": "u"},
            },
            "validate",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "config")
        self.assertIn("password", result.error["summary"])

    def test_validation_makes_no_network_request(self):
        """It runs while the user is typing; DNS must not be in the way.

        A hostname that cannot be resolved here would otherwise be reported
        as a settings error, which it is not.
        """
        result = self.adapter.probe(
            {
                "protocol": "dyndns2",
                "values": {
                    "server": "https://host.invalid/nic/update",
                    "username": "u",
                    "password": "p",
                },
            },
            "validate",
        )
        self.assertTrue(result.ok, result.error)

    def test_a_private_literal_is_still_caught_without_resolution(self):
        """No lookup is needed to see that 10.0.0.1 is inside the network."""
        result = self.adapter.probe(
            {
                "protocol": "dyndns2",
                "values": {
                    "server": "https://10.0.0.1/nic/update",
                    "username": "u",
                    "password": "p",
                },
            },
            "validate",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "address_not_public")

    def test_http_is_caught_in_validation(self):
        result = self.adapter.probe(
            {
                "protocol": "custom_http",
                "values": {"url": "http://example.com/update", "success_mode": "status"},
            },
            "validate",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "scheme_not_allowed")


class TestHostPinning(unittest.TestCase):
    def test_the_url_host_is_replaced_by_the_approved_address(self):
        guarded = ssrf.GuardedURL(
            url="https://example.com/nic/update?x=1",
            scheme="https",
            host="example.com",
            port=443,
            pinned_addresses=(ipaddress.ip_address("203.0.113.9"),),
        )
        pinned = native._url_with_address(guarded.url, guarded)
        self.assertEqual(pinned, "https://203.0.113.9:443/nic/update?x=1")

    def test_ipv6_literals_are_bracketed(self):
        guarded = ssrf.GuardedURL(
            url="https://example.com/update",
            scheme="https",
            host="example.com",
            port=443,
            pinned_addresses=(ipaddress.ip_address("2606:4700::1111"),),
        )
        self.assertIn("[2606:4700::1111]", native._url_with_address(guarded.url, guarded))

    def test_the_host_header_keeps_the_real_name(self):
        guarded = ssrf.GuardedURL(
            url="https://example.com/update", scheme="https", host="example.com", port=443
        )
        self.assertEqual(native._host_header(guarded), "example.com")

    def test_a_non_default_port_stays_in_the_host_header(self):
        guarded = ssrf.GuardedURL(
            url="https://example.com:8443/update",
            scheme="https",
            host="example.com",
            port=8443,
        )
        self.assertEqual(native._host_header(guarded), "example.com:8443")


if __name__ == "__main__":
    unittest.main(verbosity=2)
