"""End-to-end tests for the hub's HTTP API.

The whole API is exercised against a real Starlette app over temporary files,
with the HTTP layer and the address lookup stubbed — no network, no fixtures
to keep in sync. The point is to catch the mistakes that unit tests cannot: a route
wired to the wrong handler, a status code that says success for a failure,
and above all a response that carries a credential.

Run with:  python3 -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dnsmith/hub"))
sys.path.insert(0, str(ROOT / "tests"))

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

from starlette.testclient import TestClient  # noqa: E402

from dnsmith_hub.adapters import native  # noqa: E402
from dnsmith_hub.adapters.base import AdapterError, RecordStatus, UpdateState  # noqa: E402
from dnsmith_hub.scheduler import Scheduler  # noqa: E402
from dnsmith_hub.api import create_app  # noqa: E402
from dnsmith_hub.registry import Registry  # noqa: E402
from dnsmith_hub.secrets import SecretStore  # noqa: E402
from dnsmith_hub.service import Service  # noqa: E402
from dnsmith_hub.store import ConfigStore  # noqa: E402

from test_hub import StubCaller, StubSources  # noqa: E402

TOKEN = "a-very-secret-duckdns-token"


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        base = Path(self.directory.name)

        registry = Registry(ROOT / "dnsmith/providers")
        registry.load()

        secrets = SecretStore(base / "secrets.json")
        store = ConfigStore(base / "config.json", secrets, registry)
        self.caller = StubCaller()
        self.sources = StubSources()
        self.scheduler = Scheduler(
            registry=registry,
            store=store,
            secrets=secrets,
            native=native.NativeAdapter(caller=self.caller),
            sources=self.sources,
        )

        self.registry = registry
        self.service = Service(
            registry=registry, store=store, secrets=secrets, scheduler=self.scheduler
        )
        self.client = TestClient(create_app(self.service))

    def tearDown(self):
        self.directory.cleanup()


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

    def settle(self, expected: int = 1):
        """Wait for the update that creating a record kicks off.

        It runs as a background task, so a test that looks immediately would
        see whatever the event loop happened to have finished.
        """
        for _ in range(100):
            if len(self.caller.calls) >= expected:
                return
            time.sleep(0.01)

    def create_generic(self):
        """A record on a provider that is actually ported."""
        return self.client.post(
            "/api/v1/records",
            json={
                "provider_id": "dyndns2",
                "domain": "home.example.com",
                "owner": "@",
                "ip_version": "ipv4",
                "values": {
                    "server": "https://dyndns.example.org/nic/update",
                    "username": "u",
                    "password": "update-password",
                },
            },
        )

    def create_duckdns(self, owner="@", token=TOKEN):
        return self.client.post(
            "/api/v1/records",
            json={
                "provider_id": "duckdns",
                "domain": "home.duckdns.org",
                "owner": owner,
                "ip_version": "ipv4",
                "label": "Zuhause",
                "values": {"token": token},
            },
        )


class TestProviderEndpoints(APITestCase):
    def test_the_catalogue_lists_every_provider(self):
        response = self.client.get("/api/v1/providers")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertGreaterEqual(body["total"], 60)
        self.assertIn("german", body["categories"])

    def test_search_narrows_the_list(self):
        body = self.client.get("/api/v1/providers?q=duck").json()
        self.assertTrue(any(p["id"] == "duckdns" for p in body["providers"]))
        self.assertFalse(any(p["id"] == "cloudflare" for p in body["providers"]))

    def test_category_filter_narrows_the_list(self):
        body = self.client.get("/api/v1/providers?category=german").json()
        identifiers = {provider["id"] for provider in body["providers"]}
        self.assertIn("ipv64", identifiers)
        self.assertNotIn("cloudflare", identifiers)

    def test_a_form_is_returned_for_a_provider(self):
        body = self.client.get("/api/v1/providers/cloudflare").json()
        self.assertEqual(body["provider_id"], "cloudflare")
        self.assertEqual(body["auth"]["default"], "api_token")
        self.assertTrue(any(field["id"] == "zone_identifier" for field in body["fields"]))

    def test_an_unknown_provider_is_404(self):
        response = self.client.get("/api/v1/providers/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "provider_not_found")


class TestRecordEndpoints(APITestCase):
    def test_create_read_and_delete(self):
        created = self.create_duckdns()
        self.assertEqual(created.status_code, 201)

        record_id = created.json()["id"]
        self.assertEqual(created.json()["display_name"], "Zuhause")

        listed = self.client.get("/api/v1/records").json()
        self.assertEqual(listed["total"], 1)

        fetched = self.client.get(f"/api/v1/records/{record_id}")
        self.assertEqual(fetched.status_code, 200)

        deleted = self.client.delete(f"/api/v1/records/{record_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/records").json()["total"], 0)

    def test_a_missing_required_field_is_422_with_field_names(self):
        response = self.client.post(
            "/api/v1/records",
            json={
                "provider_id": "duckdns",
                "domain": "home.duckdns.org",
                "owner": "@",
                "ip_version": "ipv4",
                "values": {},
            },
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "validation_failed")
        # The UI needs to know WHICH field to mark, not just that something failed.
        self.assertIn("token", body["error"]["fields"])

    def test_an_invalid_ip_version_is_422_not_500(self):
        """ip_version used to go straight into the pydantic model unchecked,

        so a bad value surfaced as an unhandled ValidationError (bare 500)
        instead of the same validation_failed shape every other bad field
        gets.
        """
        response = self.client.post(
            "/api/v1/records",
            json={
                "provider_id": "duckdns",
                "domain": "home.duckdns.org",
                "owner": "@",
                "ip_version": "ipv5",
                "values": {"token": TOKEN},
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_failed")
        self.assertIn("ip_version", response.json()["error"]["fields"])

    def test_an_invalid_domain_is_422(self):
        response = self.client.post(
            "/api/v1/records",
            json={
                "provider_id": "duckdns",
                "domain": "not a hostname",
                "owner": "@",
                "ip_version": "ipv4",
                "values": {"token": TOKEN},
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("domain", response.json()["error"]["fields"])

    def test_a_duplicate_record_is_409(self):
        self.create_duckdns()
        response = self.create_duckdns()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "duplicate_record")

    def test_an_unknown_record_is_404(self):
        self.assertEqual(self.client.get("/api/v1/records/" + "0" * 16).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/records/" + "0" * 16).status_code, 404)

    def test_patching_a_label_leaves_the_secret_alone(self):
        record_id = self.create_duckdns().json()["id"]

        patched = self.client.patch(
            f"/api/v1/records/{record_id}", json={"label": "Neuer Name"}
        )

        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["label"], "Neuer Name")
        self.assertTrue(patched.json()["secrets"]["token"]["set"])

    def test_a_disabled_record_is_never_updated(self):
        record_id = self.create_generic().json()["id"]
        self.settle()
        self.caller.calls.clear()

        self.client.patch(f"/api/v1/records/{record_id}", json={"enabled": False})
        self.scheduler.tick()

        self.assertEqual(self.caller.calls, [])

        listed = self.client.get("/api/v1/records").json()
        self.assertEqual(listed["records"][0]["status"]["state"], "disabled")

    def test_creating_a_record_updates_it_straight_away(self):
        """Nobody should have to press a button to find out if it worked."""
        self.create_generic()

        # The update runs as a background task, so let the loop get to it.
        for _ in range(50):
            if self.caller.calls:
                break
            time.sleep(0.01)

        self.assertTrue(self.caller.calls, "no update was attempted after creating")
        self.assertEqual(self.caller.calls[0]["url"], "https://dyndns.example.org/nic/update")

    def test_the_form_says_whether_a_real_check_is_possible(self):
        """So the button can be honest before it is pressed, not after."""
        with_lookup = self.client.get("/api/v1/providers/cloudflare").json()
        without = self.client.get("/api/v1/providers/dynu").json()

        self.assertTrue(with_lookup["live_test"])
        self.assertFalse(without["live_test"])

    def test_an_unreadable_configuration_is_visible_in_the_status(self):
        """The interface leads with it, because an empty list looks normal."""
        broken = Path(self.directory.name) / "config.json"
        broken.write_text('{"config_version": 2, "records": "not a list"}', encoding="utf-8")
        self.service.store.load()

        body = self.client.get("/api/v1/status").json()
        self.assertIn("nicht gelesen werden", body["config_error"] or "")

        ready = self.client.get("/readyz").json()
        self.assertEqual(ready["status"], "degraded")
        self.assertEqual(ready["error"]["code"], "config_unreadable")

    def test_malformed_json_is_400(self):
        response = self.client.post(
            "/api/v1/records",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)


class TestNoSecretEverLeaves(APITestCase):
    """Every response is checked for the token. This is the important one."""

    def test_no_endpoint_returns_the_token(self):
        record_id = self.create_duckdns().json()["id"]
        self.scheduler._remember(  # noqa: SLF001 - as a real pass would have
            RecordStatus(
                record_id=record_id,
                state=UpdateState.FAIL,
                error={"code": "auth", "summary": "bad authentication"},
            )
        )

        responses = {
            "create": self.create_duckdns(owner="zweit").text,
            "list": self.client.get("/api/v1/records").text,
            "get": self.client.get(f"/api/v1/records/{record_id}").text,
            "status": self.client.get("/api/v1/status").text,
            "export": self.client.get("/api/v1/config/export").text,
            "patch": self.client.patch(
                f"/api/v1/records/{record_id}", json={"label": "x"}
            ).text,
            "test": self.client.post(
                "/api/v1/test",
                json={
                    "provider_id": "duckdns",
                    "domain": "home.duckdns.org",
                    "record_id": record_id,
                    "values": {},
                    "mode": "validate",
                },
            ).text,
        }

        for name, text in responses.items():
            with self.subTest(endpoint=name):
                self.assertNotIn(TOKEN, text)

    def test_the_export_with_secrets_is_opt_in(self):
        self.create_duckdns()

        without = self.client.get("/api/v1/config/export").text
        with_secrets = self.client.get("/api/v1/config/export?include_secrets=true").text

        self.assertNotIn(TOKEN, without)
        self.assertIn(TOKEN, with_secrets)
        self.assertFalse(json.loads(without)["includes_secrets"])

    def test_a_provider_that_echoes_the_token_back_is_still_redacted(self):
        """The log filter never sees an API response - this path has to redact itself.

        Simulates a provider that mirrors the credential in its own error
        text, the way a real one might on a bad-auth response. The status was
        put there directly, the way a real scheduler pass would have, so this
        exercises exactly what record_payload()/records_payload() serve - not
        just the live failure paths the other cases in this class cover.
        """
        record_id = self.create_duckdns().json()["id"]
        self.scheduler._remember(  # noqa: SLF001 - as a real pass would have
            RecordStatus(
                record_id=record_id,
                state=UpdateState.FAIL,
                error={
                    "code": "provider_response",
                    "summary": "DuckDNS lehnte ab",
                    "detail": f"invalid token: {TOKEN}",
                },
            )
        )

        for name, text in {
            "get": self.client.get(f"/api/v1/records/{record_id}").text,
            "list": self.client.get("/api/v1/records").text,
            "status": self.client.get("/api/v1/status").text,
        }.items():
            with self.subTest(endpoint=name):
                self.assertNotIn(TOKEN, text)

    def test_a_submitted_secret_is_not_echoed_by_the_test_endpoint(self):
        response = self.client.post(
            "/api/v1/test",
            json={
                "provider_id": "duckdns",
                "domain": "home.duckdns.org",
                "owner": "@",
                "ip_version": "ipv4",
                "values": {"token": "submitted-but-never-saved"},
                "mode": "validate",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("submitted-but-never-saved", response.text)


class TestStatusAndActions(APITestCase):
    def _status(self, record_id, **fields):
        """Put a status into the scheduler the way a real pass would have."""
        self.scheduler._remember(RecordStatus(record_id=record_id, **fields))  # noqa: SLF001

    def test_status_reports_counts_and_the_public_address(self):
        record_id = self.create_duckdns().json()["id"]
        self._status(record_id, state=UpdateState.UP_TO_DATE, current_ipv4="198.51.100.7")

        body = self.client.get("/api/v1/status").json()

        self.assertEqual(body["records_total"], 1)
        self.assertEqual(body["records_failed"], 0)
        self.assertEqual(body["public_ip"]["ipv4"], "203.0.113.9")

    def test_a_failing_record_is_counted_and_explained(self):
        record_id = self.create_duckdns().json()["id"]
        self._status(
            record_id,
            state=UpdateState.FAIL,
            error={"code": "auth", "summary": "bad authentication"},
        )

        body = self.client.get("/api/v1/status").json()

        self.assertEqual(body["records_failed"], 1)
        error = body["records"][0]["status"]["error"]
        self.assertEqual(error["code"], "auth")
        # German headline, upstream text kept separately, next steps present.
        self.assertIn("abgelehnt", error["message"])
        self.assertEqual(error["technical"], "bad authentication")
        self.assertTrue(error["checks"])

    def test_forcing_an_update_sends_the_request(self):
        record_id = self.create_generic().json()["id"]
        # Creating already triggered one; this test is about the button.
        self.settle()
        self.caller.calls.clear()

        response = self.client.post(f"/api/v1/records/{record_id}/update")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"], response.json())
        self.assertEqual(len(self.caller.calls), 1)

    def test_an_unported_provider_reports_instead_of_failing_silently(self):
        """The transitional state has to be visible, not a broken update.

        DuckDNS has no updater yet. Pressing the button must say so in the
        record's status rather than reporting a success nothing performed.
        """
        record_id = self.create_duckdns().json()["id"]
        self.settle()
        self.mark_unported()
        self.caller.calls.clear()

        response = self.client.post(f"/api/v1/records/{record_id}/update")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(self.caller.calls, [])

        status = self.client.get("/api/v1/status").json()["records"][0]["status"]
        self.assertEqual(status["state"], "fail")
        self.assertEqual(status["error"]["code"], "not_implemented")

    def test_the_ip_endpoint_flags_cgnat(self):
        self.scheduler.sources = StubSources(ipv4="100.64.12.7")

        body = self.client.get("/api/v1/ip").json()

        codes = {notice["code"] for notice in body["notices"]}
        self.assertIn("cgnat", codes)

    def test_the_ip_endpoint_flags_a_missing_ipv6(self):
        body = self.client.get("/api/v1/ip").json()
        codes = {notice["code"] for notice in body["notices"]}
        self.assertIn("no_ipv6", codes)
        message = next(n["message"] for n in body["notices"] if n["code"] == "no_ipv6")
        # The message must carry the actual fix, not just the diagnosis.
        self.assertIn("--enable-ipv6", message)

    def test_ds_lite_is_recognised(self):
        self.scheduler.sources = StubSources(ipv4=None, ipv6="2001:db8::1")
        body = self.client.get("/api/v1/ip").json()
        self.assertIn("ipv6_only", {notice["code"] for notice in body["notices"]})


class TestHealthEndpoints(APITestCase):
    def test_healthz_is_always_cheap(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readyz_is_degraded_without_a_public_address(self):
        """The one condition that stops DNSmith doing its job at all."""
        self.scheduler.sources = StubSources(ipv4=None, ipv6=None)
        body = self.client.get("/readyz").json()
        self.assertEqual(body["status"], "degraded")

    def test_responses_are_not_cacheable(self):
        response = self.client.get("/api/v1/records")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main(verbosity=2)
