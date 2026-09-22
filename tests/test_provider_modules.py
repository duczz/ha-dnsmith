"""The providers that could not stay data, and why.

Ten of sixty need a module. Each of these tests names the reason in its own
docstring, because "this one has a module" is only defensible as long as the
reason is written down and still true — a module whose reason has evaporated
should go back to being a manifest.

The HTTP layer is a scripted stub: the module gets the answers a real API
would give, in order, and the test checks what it decided to send back.

unittest rather than pytest, so they run with nothing installed.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import urllib.parse
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dnsmith/hub"))

from dnsmith_hub.adapters.base import AdapterError  # noqa: E402
from dnsmith_hub.adapters.providers import support  # noqa: E402

MANIFESTS = ROOT / "dnsmith/providers"


class Scripted:
    """Answers each call from a script, and remembers every request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def call(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if not self.answers:
            return 200, "{}"
        answer = self.answers.pop(0)
        return answer if isinstance(answer, tuple) else (200, answer)

    @property
    def last(self):
        return self.calls[-1]

    # What support.Api expects of a caller.
    def __call__(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("the module must go through Api, not call directly")


def context(owner="home", ipv6=False):
    return support.Context(
        ip="2001:db8::1" if ipv6 else "203.0.113.7",
        ipv4=None if ipv6 else "203.0.113.7",
        ipv6="2001:db8::1" if ipv6 else None,
        rrtype="AAAA" if ipv6 else "A",
        hostname="example.com" if owner == "@" else f"{owner}.example.com",
        domain="example.com",
        owner=owner,
        subdomain="" if owner == "@" else owner,
    )


def run(module_name, values, caller, ctx=None):
    import importlib

    module = importlib.import_module(f"dnsmith_hub.adapters.providers.{module_name}")
    return module.update(support.Api(caller), values, ctx or context())


def bodies(caller):
    return [call.get("json_body") or call.get("form_body") or call.get("params")
            for call in caller.calls]


class TestEveryModuleIsDeclared(unittest.TestCase):
    def test_each_module_is_named_by_a_manifest(self):
        """A module nothing points at is dead code that still looks alive."""
        declared = set()
        for path in MANIFESTS.glob("*.yaml"):
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
            if manifest["engine"]["adapter"] == "python":
                declared.add(manifest["engine"]["module"])

        directory = ROOT / "dnsmith/hub/dnsmith_hub/adapters/providers"
        present = {p.stem for p in directory.glob("*.py")} - {"__init__", "support"}

        self.assertEqual(present, declared)


class TestPorkbun(unittest.TestCase):
    """Porkbun: a new domain arrives with a parked placeholder in the way.

    Creating an A record next to the ALIAS that points at pixie.porkbun.com
    fails, so the first update on a fresh domain is delete-then-create — two
    writes, which the declarative path does not do.
    """

    VALUES = {"api_key": "pk-key", "secret_api_key": "pk-secret", "ttl": 600}

    def test_an_existing_record_is_edited(self):
        caller = Scripted('{"status": "SUCCESS", "records": [{"id": "77"}]}',
                          '{"status": "SUCCESS"}')
        outcome = run("porkbun", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(len(caller.calls), 2)
        self.assertTrue(caller.calls[1]["url"].endswith("/dns/edit/example.com/77"))
        self.assertEqual(caller.calls[1]["json_body"]["content"], "203.0.113.7")

    def test_the_credentials_travel_in_the_body_on_every_call(self):
        caller = Scripted('{"status": "SUCCESS", "records": [{"id": "77"}]}',
                          '{"status": "SUCCESS"}')
        run("porkbun", self.VALUES, caller)
        for body in bodies(caller):
            self.assertEqual(body["apikey"], "pk-key")
            self.assertEqual(body["secretapikey"], "pk-secret")

    def test_the_parked_placeholder_is_removed_before_creating_at_the_apex(self):
        caller = Scripted(
            '{"status": "SUCCESS", "records": []}',                       # no A record
            '{"status": "SUCCESS", "records": [{"id": "1", "content": "pixie.porkbun.com"}]}',
            '{"status": "SUCCESS"}',                                      # the delete
            '{"status": "SUCCESS"}',                                      # the create
        )
        run("porkbun", self.VALUES, caller, context(owner="@"))

        urls = [call["url"] for call in caller.calls]
        self.assertIn("/dns/deleteByNameType/example.com/ALIAS/", urls[2])
        self.assertIn("/dns/create/example.com", urls[3])

    def test_a_record_that_is_not_the_placeholder_is_left_alone(self):
        """Somebody's own ALIAS is not ours to delete to make room."""
        caller = Scripted(
            '{"status": "SUCCESS", "records": []}',
            '{"status": "SUCCESS", "records": [{"id": "1", "content": "their-own.example.net"}]}',
            '{"status": "SUCCESS"}',
        )
        run("porkbun", self.VALUES, caller, context(owner="@"))

        urls = [call["url"] for call in caller.calls]
        self.assertFalse(any("deleteByNameType" in url for url in urls))
        self.assertIn("/dns/create/example.com", urls[-1])

    def test_a_refusal_is_reported(self):
        caller = Scripted('{"status": "SUCCESS", "records": [{"id": "77"}]}',
                          '{"status": "ERROR", "message": "Invalid API key."}')
        with self.assertRaises(AdapterError) as caught:
            run("porkbun", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "provider_response")


class TestDreamhost(unittest.TestCase):
    """DreamHost has no update: a record is removed and a new one added."""

    VALUES = {"key": "dh-key"}

    def test_remove_comes_before_add(self):
        """Adding first would simply be refused as a duplicate."""
        caller = Scripted(
            '{"result": "success", "data": [{"record": "home.example.com", "type": "A",'
            ' "value": "198.51.100.1", "editable": "1"}]}',
            '{"result": "success"}',
            '{"result": "success"}',
        )
        outcome = run("dreamhost", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        commands = [call["params"]["cmd"] for call in caller.calls]
        self.assertEqual(commands, ["dns-list_records", "dns-remove_record", "dns-add_record"])

    def test_an_unchanged_record_is_not_rewritten(self):
        caller = Scripted(
            '{"result": "success", "data": [{"record": "home.example.com", "type": "A",'
            ' "value": "203.0.113.7", "editable": "1"}]}')
        outcome = run("dreamhost", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(len(caller.calls), 1)

    def test_a_record_dreamhost_manages_itself_is_refused_with_a_reason(self):
        caller = Scripted(
            '{"result": "success", "data": [{"record": "home.example.com", "type": "A",'
            ' "value": "198.51.100.1", "editable": "0"}]}')
        with self.assertRaises(AdapterError) as caught:
            run("dreamhost", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "config")
        self.assertIn("nicht änderbar", caught.exception.message)

    def test_every_call_carries_a_fresh_unique_id(self):
        """It is DreamHost's replay guard, so reusing one would be wrong."""
        caller = Scripted(
            '{"result": "success", "data": []}',
            '{"result": "success"}',
        )
        run("dreamhost", self.VALUES, caller)
        ids = [call["params"]["unique_id"] for call in caller.calls]
        self.assertEqual(len(set(ids)), len(ids))


class TestDnspod(unittest.TestCase):
    """DNSPod's write needs the record's line, which only the listing knows."""

    VALUES = {"token": "dp-token"}

    def test_the_line_is_carried_over_from_the_listing(self):
        caller = Scripted(
            '{"status": {"code": "1"}, "records": [{"id": "5", "name": "home",'
            ' "type": "A", "value": "198.51.100.1", "line": "电信"}]}',
            '{"status": {"code": "1"}}',
        )
        outcome = run("dnspod", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(caller.calls[1]["form_body"]["record_line"], "电信")
        self.assertEqual(caller.calls[1]["form_body"]["value"], "203.0.113.7")

    def test_a_rejected_token_is_an_auth_error_despite_http_200(self):
        caller = Scripted('{"status": {"code": "-1", "message": "login error"}}')
        with self.assertRaises(AdapterError) as caught:
            run("dnspod", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "auth")

    def test_a_missing_record_says_what_to_do(self):
        caller = Scripted('{"status": {"code": "1"}, "records": []}')
        with self.assertRaises(AdapterError) as caught:
            run("dnspod", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "not_found")
        self.assertIn("einmal an", caught.exception.message)


class TestHetzner(unittest.TestCase):
    """Hetzner answers a write with an action, not with a result.

    Reporting success when the POST returned would report that Hetzner
    accepted the job, not that the record changed.
    """

    VALUES = {"token": "hz-token", "ttl": 300}

    def test_an_accepted_action_is_waited_for(self):
        slept = []
        caller = Scripted(
            '{"rrset": {"records": [{"value": "198.51.100.1"}]}}',   # exists
            '{"action": {"id": 9, "status": "running"}}',            # the write
            '{"action": {"id": 9, "status": "running"}}',            # still running
            '{"action": {"id": 9, "status": "success"}}',            # done
        )
        import importlib
        module = importlib.import_module("dnsmith_hub.adapters.providers.hetzner")
        outcome = module.update(support.Api(caller), self.VALUES, context(),
                                sleep=slept.append)

        self.assertTrue(outcome.ok)
        self.assertTrue(caller.calls[-1]["url"].endswith("/v1/actions/9"))
        self.assertEqual(len(slept), 2)

    def test_a_failed_action_is_reported_even_though_the_post_succeeded(self):
        caller = Scripted(
            '{"rrset": {"records": []}}',
            '{"action": {"id": 3, "status": "error",'
            ' "error": {"code": "conflict", "message": "record exists"}}}',
        )
        with self.assertRaises(AdapterError) as caught:
            run("hetzner", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "provider_response")
        self.assertIn("conflict", caught.exception.detail)

    def test_a_missing_rrset_is_created(self):
        caller = Scripted((404, '{"error": {"code": "not_found"}}'),
                          '{"action": {"id": 1, "status": "success"}}')
        outcome = run("hetzner", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        self.assertTrue(caller.calls[1]["url"].endswith("/v1/zones/example.com/rrsets"))
        self.assertEqual(caller.calls[1]["json_body"]["records"], [{"value": "203.0.113.7"}])

    def test_the_apex_is_addressed_as_at_not_as_nothing(self):
        caller = Scripted('{"rrset": {"records": []}}',
                          '{"action": {"id": 1, "status": "success"}}')
        run("hetzner", self.VALUES, caller, context(owner="@"))
        self.assertIn("/rrsets/%40/A", caller.calls[0]["url"])


class TestNetcup(unittest.TestCase):
    """netcup is JSON-RPC with a session: log in, read, write, log out."""

    VALUES = {"customer_number": "12345", "api_key": "nc-key", "password": "nc-password"}

    def test_the_session_from_the_login_is_used_by_every_later_call(self):
        caller = Scripted(
            '{"status": "success", "responsedata": {"apisessionid": "sess-1"}}',
            '{"status": "success", "responsedata": {"dnsrecords": [{"id": "1",'
            ' "hostname": "home", "type": "A", "destination": "198.51.100.1",'
            ' "priority": "0"}]}}',
            '{"status": "success", "responsedata": {}}',
            '{"status": "success", "responsedata": {}}',
        )
        outcome = run("netcup", self.VALUES, caller)

        self.assertTrue(outcome.ok)
        actions = [call["json_body"]["action"] for call in caller.calls]
        self.assertEqual(actions, ["login", "infoDnsRecords", "updateDnsRecords", "logout"])
        for call in caller.calls[1:]:
            self.assertEqual(call["json_body"]["param"]["apisessionid"], "sess-1")

    def test_the_record_is_sent_back_whole(self):
        """Only the destination changes; netcup keeps the rest of the entry."""
        caller = Scripted(
            '{"status": "success", "responsedata": {"apisessionid": "s"}}',
            '{"status": "success", "responsedata": {"dnsrecords": [{"id": "1",'
            ' "hostname": "home", "type": "A", "destination": "198.51.100.1",'
            ' "priority": "7", "state": "yes"}]}}',
            '{"status": "success", "responsedata": {}}',
            '{"status": "success", "responsedata": {}}',
        )
        run("netcup", self.VALUES, caller)

        written = caller.calls[2]["json_body"]["param"]["dnsrecordset"]["dnsrecords"][0]
        self.assertEqual(written["destination"], "203.0.113.7")
        self.assertEqual(written["priority"], "7")
        self.assertEqual(written["id"], "1")

    def test_the_session_is_closed_even_when_the_update_fails(self):
        caller = Scripted(
            '{"status": "success", "responsedata": {"apisessionid": "s"}}',
            '{"status": "success", "responsedata": {"dnsrecords": []}}',
            '{"status": "success", "responsedata": {}}',
        )
        with self.assertRaises(AdapterError):
            run("netcup", self.VALUES, caller)
        self.assertEqual(caller.calls[-1]["json_body"]["action"], "logout")

    def test_a_rejected_login_is_an_auth_error(self):
        caller = Scripted('{"status": "error", "statuscode": 4013,'
                          ' "longmessage": "Authorization failed."}')
        with self.assertRaises(AdapterError) as caught:
            run("netcup", self.VALUES, caller)
        self.assertEqual(caught.exception.code, "auth")


class TestOvh(unittest.TestCase):
    """OVH has two ways in, and the API side signs every call."""

    DYNHOST = {"mode": "dynamic", "username": "ovh-user", "password": "ovh-password"}
    API = {"mode": "api", "app_key": "ak", "app_secret": "as",
           "consumer_key": "ck", "api_endpoint": "ovh-eu"}

    def test_dynhost_mode_speaks_plain_dyndns2(self):
        caller = Scripted("good 203.0.113.7")
        outcome = run("ovh", self.DYNHOST, caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(caller.calls[0]["url"], "https://www.ovh.com/nic/update")
        self.assertEqual(caller.calls[0]["params"]["system"], "dyndns")

    def test_dynhost_badauth_is_an_auth_error_despite_http_200(self):
        with self.assertRaises(AdapterError) as caught:
            run("ovh", self.DYNHOST, Scripted("badauth"))
        self.assertEqual(caught.exception.code, "auth")

    def test_the_api_asks_ovh_what_time_it_is(self):
        """A drifted clock would otherwise look like wrong credentials."""
        caller = Scripted("1789456000", "[42]", "{}", "{}")
        run("ovh", self.API, caller)

        self.assertTrue(caller.calls[0]["url"].endswith("/auth/time"))
        self.assertEqual(caller.calls[1]["headers"]["X-Ovh-Timestamp"], "1789456000")

    def test_every_api_call_is_signed(self):
        import hashlib

        caller = Scripted("1789456000", "[42]", "{}", "{}")
        run("ovh", self.API, caller)

        listing = caller.calls[1]
        expected = "$1$" + hashlib.sha1(
            "+".join(["as", "ck", "GET", listing["url"], "", "1789456000"]).encode()
        ).hexdigest()
        self.assertEqual(listing["headers"]["X-Ovh-Signature"], expected)

    def test_the_signed_body_is_the_body_that_goes_out(self):
        """Re-encoding would change the spacing and break the signature."""
        import hashlib

        caller = Scripted("1789456000", "[]", "{}", "{}")
        run("ovh", self.API, caller)

        create = caller.calls[2]
        payload = create["content"].decode()
        expected = "$1$" + hashlib.sha1(
            "+".join(["as", "ck", "POST", create["url"], payload, "1789456000"]).encode()
        ).hexdigest()
        self.assertEqual(create["headers"]["X-Ovh-Signature"], expected)
        self.assertIsNone(create.get("json_body"))

    def test_the_zone_is_refreshed_afterwards(self):
        """Without it the change sits in the zone file unpublished."""
        caller = Scripted("1789456000", "[42]", "{}", "{}")
        run("ovh", self.API, caller)
        self.assertTrue(caller.calls[-1]["url"].endswith("/domain/zone/example.com/refresh"))

    def test_an_unknown_endpoint_name_is_refused_with_the_options(self):
        with self.assertRaises(AdapterError) as caught:
            run("ovh", {**self.API, "api_endpoint": "ovh-moon"}, Scripted())
        self.assertEqual(caught.exception.code, "config")
        self.assertIn("ovh-eu", caught.exception.message)


class TestRoute53(unittest.TestCase):
    """Every call is signed over method, path, headers and a hash of the body.

    The signature here is recomputed independently, from the published rules
    rather than from the implementation — a test that calls the same function
    it is checking proves only that the function is deterministic.
    """

    VALUES = {"access_key": "AKIAEXAMPLE", "secret_key": "sekrit", "zone_id": "Z123", "ttl": 300}
    MOMENT = datetime.datetime(2026, 9, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def send(self, caller):
        import importlib

        module = importlib.import_module("dnsmith_hub.adapters.providers.route53")
        return module.update(support.Api(caller), self.VALUES, context(), now=self.MOMENT)

    def test_it_upserts_without_looking_anything_up(self):
        """Route 53 has no separate create, so there is nothing to look up."""
        caller = Scripted((200, "<ChangeResourceRecordSetsResponse/>"))
        outcome = self.send(caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(
            caller.last["url"],
            "https://route53.amazonaws.com/2013-04-01/hostedzone/Z123/rrset")
        self.assertIn(b"<Action>UPSERT</Action>", caller.last["content"])
        self.assertIn(b"<Value>203.0.113.7</Value>", caller.last["content"])

    def test_the_signature_matches_an_independent_calculation(self):
        import hashlib
        import hmac

        caller = Scripted((200, "<ok/>"))
        self.send(caller)

        body = caller.last["content"]
        path = "/2013-04-01/hostedzone/Z123/rrset"
        canonical = "\n".join([
            "POST", path, "",
            "content-type:application/xml\nhost:route53.amazonaws.com\n",
            "content-type;host",
            hashlib.sha256(body).hexdigest(),
        ])
        scope = "20260915/us-east-1/route53/aws4_request"
        to_sign = "\n".join([
            "AWS4-HMAC-SHA256", "20260915T120000Z", scope,
            hashlib.sha256(canonical.encode()).hexdigest(),
        ])
        key = b"AWS4sekrit"
        for part in ("20260915", "us-east-1", "route53", "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        expected = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()

        self.assertEqual(
            caller.last["headers"]["Authorization"],
            f"AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/{scope},"
            f"SignedHeaders=content-type;host,Signature={expected}",
        )

    def test_the_signed_bytes_are_the_bytes_that_go_out(self):
        """A serialiser that reorders anything would break the signature."""
        caller = Scripted((200, "<ok/>"))
        self.send(caller)
        self.assertIsNone(caller.last.get("json_body"))
        self.assertIsInstance(caller.last["content"], bytes)

    def test_a_rejected_key_is_an_auth_error(self):
        caller = Scripted((403, '<ErrorResponse><Error><Code>SignatureDoesNotMatch</Code>'
                                '<Message>nope</Message></Error></ErrorResponse>'))
        with self.assertRaises(AdapterError) as caught:
            self.send(caller)
        self.assertEqual(caught.exception.code, "auth")

    def test_an_unknown_zone_says_where_to_find_the_right_one(self):
        caller = Scripted((404, '<ErrorResponse><Error><Code>NoSuchHostedZone</Code>'
                                '<Message>gone</Message></Error></ErrorResponse>'))
        with self.assertRaises(AdapterError) as caught:
            self.send(caller)
        self.assertEqual(caught.exception.code, "not_found")
        self.assertIn("Route-53-Konsole", caught.exception.message)


class TestAliyun(unittest.TestCase):
    """Signed over the whole parameter set, and addressed by a record ID."""

    VALUES = {"access_key_id": "LTAIexample", "access_secret": "sekrit"}
    MOMENT = datetime.datetime(2026, 9, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def send(self, caller, ctx=None):
        import importlib

        module = importlib.import_module("dnsmith_hub.adapters.providers.aliyun")
        return module.update(support.Api(caller), self.VALUES, ctx or context(),
                             nonce="fixed-nonce", now=self.MOMENT)

    def listing(self, *records):
        import json

        return json.dumps({"DomainRecords": {"Record": list(records)}})

    def test_reading_and_writing_use_different_hosts(self):
        """Aliyun's doing, not a typo."""
        caller = Scripted(
            self.listing({"RecordId": "77", "RR": "home", "Type": "A", "Value": "198.51.100.1"}),
            "{}",
        )
        outcome = self.send(caller)

        self.assertTrue(outcome.ok)
        self.assertIn("dns.aliyuncs.com", caller.calls[0]["url"])
        self.assertIn("alidns.aliyuncs.com", caller.calls[1]["url"])
        self.assertEqual(caller.calls[1]["params"]["RecordId"], "77")

    def test_a_keyword_hit_that_is_not_the_record_is_ignored(self):
        """RRKeyWord is a search: asking for "home" also returns "home-office"."""
        caller = Scripted(
            self.listing({"RecordId": "9", "RR": "home-office", "Type": "A", "Value": "1.2.3.4"}),
            "{}",
        )
        self.send(caller)

        self.assertEqual(caller.calls[1]["params"]["Action"], "AddDomainRecord")

    def test_an_unchanged_record_is_not_rewritten(self):
        caller = Scripted(
            self.listing({"RecordId": "77", "RR": "home", "Type": "A", "Value": "203.0.113.7"}))
        outcome = self.send(caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(len(caller.calls), 1)

    def test_the_signature_matches_an_independent_calculation(self):
        import base64
        import hashlib
        import hmac
        import urllib.parse

        caller = Scripted(self.listing(), "{}")
        self.send(caller)

        params = dict(caller.calls[0]["params"])
        signature = params.pop("Signature")

        def quote(value):
            return (urllib.parse.quote_plus(str(value), safe="")
                    .replace("+", "%20").replace("*", "%2A").replace("%7E", "~"))

        canonical = "&".join(f"{quote(k)}={quote(v)}" for k, v in sorted(params.items()))
        to_sign = f"GET&{quote('/')}&{quote(canonical)}"
        expected = base64.b64encode(
            hmac.new(b"sekrit&", to_sign.encode(), hashlib.sha1).digest()).decode()

        self.assertEqual(signature, expected)

    def test_every_call_carries_a_fresh_nonce_in_real_use(self):
        """The nonce is fixed in these tests; it must not be fixed in the code."""
        import importlib

        module = importlib.import_module("dnsmith_hub.adapters.providers.aliyun")
        seen = set()
        for _ in range(3):
            caller = Scripted(self.listing(), "{}")
            module.update(support.Api(caller), self.VALUES, context(), now=self.MOMENT)
            seen.add(caller.calls[0]["params"]["SignatureNonce"])

        self.assertEqual(len(seen), 3)

    def test_a_rejected_key_is_an_auth_error(self):
        caller = Scripted((403, '{"Code": "InvalidAccessKeyId.NotFound", "Message": "nope"}'))
        with self.assertRaises(AdapterError) as caught:
            self.send(caller)
        self.assertEqual(caught.exception.code, "auth")


def rsa_available() -> bool:
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(rsa_available(), "cryptography fehlt; siehe tests/README.md")
class TestGcp(unittest.TestCase):
    """Google needs a signed JWT before it will talk at all.

    The service-account key signs a short-lived assertion, Google exchanges
    it for an access token, and that token authorises the record call. Three
    steps where every other provider has one, and the reason this is the only
    module with a dependency behind it.
    """

    NOW = 1_789_000_000

    def setUp(self):
        import importlib

        self.module = importlib.import_module("dnsmith_hub.adapters.providers.gcp")
        # The token cache is global on purpose; a test must not inherit one.
        self.module._tokens.clear()  # noqa: SLF001
        self.values = {"project": "my-project", "zone": "my-zone",
                       "credentials": json.dumps(self.credentials())}

    def credentials(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        if not hasattr(type(self), "_key"):
            type(self)._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = type(self)._key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        return {"client_email": "dnsmith@my-project.iam.gserviceaccount.com",
                "private_key": pem, "type": "service_account"}

    def send(self, caller, values=None):
        return self.module.update(support.Api(caller), values or self.values,
                                  context(), now=self.NOW)

    def token_answer(self):
        return '{"access_token": "ya29.token", "expires_in": 3600}'

    def test_the_assertion_verifies_against_the_service_account_key(self):
        """Signed correctly, or Google would simply refuse."""
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        caller = Scripted(self.token_answer(),
                          '{"rrdatas": ["198.51.100.1"], "ttl": 300}',
                          "{}")
        self.send(caller)

        assertion = caller.calls[0]["form_body"]["assertion"]
        signing_input, signature = assertion.rsplit(".", 1)

        def unpad(segment):
            return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

        type(self)._key.public_key().verify(
            unpad(signature), signing_input.encode(),
            padding.PKCS1v15(), hashes.SHA256(),
        )

        header, claims = (json.loads(unpad(part)) for part in signing_input.split("."))
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(claims["iss"], "dnsmith@my-project.iam.gserviceaccount.com")
        self.assertEqual(claims["exp"], self.NOW + 3600)

    def test_the_narrowest_scope_that_still_works_is_asked_for(self):
        """cloud-platform would also work and would grant far more."""
        caller = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"]}', "{}")
        self.send(caller)

        claims = json.loads(
            __import__("base64").urlsafe_b64decode(
                caller.calls[0]["form_body"]["assertion"].split(".")[1] + "=="))
        self.assertEqual(claims["scope"],
                         "https://www.googleapis.com/auth/ndev.clouddns.readwrite")

    def test_the_token_is_reused_across_records(self):
        """Six Google records in one pass must not mean six tokens."""
        first = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"]}', "{}")
        self.send(first)

        second = Scripted('{"rrdatas": ["198.51.100.1"]}', "{}")
        self.send(second)

        self.assertNotIn(self.module.TOKEN_URL, [call["url"] for call in second.calls])

    def test_an_expired_token_is_fetched_again(self):
        caller = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"]}', "{}")
        self.send(caller)

        later = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"]}', "{}")
        self.module.update(support.Api(later), self.values, context(),
                           now=self.NOW + 3600)
        self.assertEqual(later.calls[0]["url"], self.module.TOKEN_URL)

    def test_the_record_is_named_absolutely(self):
        """Google wants the trailing dot."""
        caller = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"]}', "{}")
        self.send(caller)

        self.assertIn("home.example.com.", urllib.parse.unquote(caller.calls[1]["url"]))
        self.assertEqual(caller.calls[2]["json_body"]["name"], "home.example.com.")
        self.assertEqual(caller.calls[2]["method"], "PATCH")

    def test_a_missing_record_set_is_created(self):
        caller = Scripted(self.token_answer(), (404, '{"error": {"message": "nope"}}'), "{}")
        outcome = self.send(caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(caller.last["method"], "POST")
        self.assertTrue(caller.last["url"].endswith("/rrsets"))

    def test_an_unchanged_record_is_not_written(self):
        caller = Scripted(self.token_answer(), '{"rrdatas": ["203.0.113.7"], "ttl": 60}')
        outcome = self.send(caller)

        self.assertTrue(outcome.ok)
        self.assertEqual(len(caller.calls), 2)

    def test_the_existing_ttl_is_kept(self):
        """Changing the address must not silently reset the TTL."""
        caller = Scripted(self.token_answer(), '{"rrdatas": ["198.51.100.1"], "ttl": 60}', "{}")
        self.send(caller)
        self.assertEqual(caller.last["json_body"]["ttl"], 60)

    def test_credentials_that_are_not_json_say_so(self):
        with self.assertRaises(AdapterError) as caught:
            self.send(Scripted(), {**self.values, "credentials": "mein schluessel"})
        self.assertEqual(caught.exception.code, "config")
        self.assertIn("Dienstkontos", caught.exception.message)

    def test_a_missing_permission_names_the_role(self):
        caller = Scripted(self.token_answer(),
                          (403, '{"error": {"message": "forbidden"}}'))
        with self.assertRaises(AdapterError) as caught:
            self.send(caller)
        self.assertEqual(caught.exception.code, "auth")
        self.assertIn("DNS-Administrator", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
