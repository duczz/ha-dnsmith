"""What each ported provider actually sends.

The manifests describe the call; these tests perform it against a recording
stub and check what came out. Two kinds of assertion live here.

The endpoint table is a deliberate second copy of the host and path. That is
the point: a manifest edit that moves a provider to the wrong endpoint is
exactly the change that produces no error anywhere — the request goes out,
something answers, and the user's record quietly stops being updated. A
second copy in a different file is what makes that edit fail.

Everything else is a property that has to hold for every provider at once,
which is where the real value is: no placeholder may survive into a sent
request, no credential may be missing, and a dual-stack record must not
silently update only one family.

unittest rather than pytest, so they run with nothing installed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dnsmith/hub"))

from dnsmith_hub.adapters.base import AdapterError  # noqa: E402
from dnsmith_hub.adapters.native import PLACEHOLDER, NativeAdapter  # noqa: E402

MANIFESTS = ROOT / "dnsmith/providers"

# provider id -> the URL its update must reach, with the sample values below
# filled in. A provider whose path carries the domain or the record type shows
# them resolved here, which is the point: it is the finished URL that either
# reaches the provider or does not.
ENDPOINTS = {
    "allinkl": "https://dyndns.kasserver.com/",
    "cloudns": "https://ipv4.cloudns.net/api/dynamicURL/",
    "ddnss": "https://www.ddnss.de/upd.php",
    "desec": "https://update.dedyn.io/",
    "dnshome": "https://www.dnshome.de/dyndns.php",
    "dnsomatic": "https://updates.dnsomatic.com/nic/update",
    "domeneshop": "https://api.domeneshop.no/v0/dyndns/update",
    "dyn": "https://members.dyndns.org/v3/update",
    "dynu": "https://api.dynu.com/nic/update",
    "easydns": "https://api.cp.easydns.com/dyn/generic.php",
    "gigahostno": "https://api.gigahost.no/api/v0/dns/dyndns",
    "he": "https://dyn.dns.he.net/nic/update",
    "infomaniak": "https://infomaniak.com/nic/update",
    "inwx": "https://dyndns.inwx.com/nic/update",
    "loopia": "https://dyndns.loopia.se/",
    "noip": "https://dynupdate.no-ip.com/nic/update",
    "nowdns": "https://now-dns.com/update",
    "opendns": "https://updates.opendns.com/nic/update",
    "selfhost.de": "https://carol.selfhost.de/nic/update",
    "spdyn": "https://update.spdyn.de/nic/update",
    "strato": "https://dyndns.strato.com/nic/update",
    "variomedia": "https://dyndns4.variomedia.de/nic/update",
    "zoneedit": "https://api.cp.zoneedit.com/dyn/generic.php",
    # Tier 2 — one request each, but no shared protocol.
    "changeip": "https://nic.changeip.com/nic/update",
    "dd24": "https://dynamicdns.key-systems.net/update.php",
    "dondominio": "https://dondns.dondominio.com/json/",
    "duckdns": "https://www.duckdns.org/update",
    "freemyip": "https://freemyip.com/update",
    "dynv6": "https://ipv4.dynv6.com/api/update",
    "freedns": "https://sync.afraid.org/u/sample-token/",
    "gandi": "https://api.gandi.net/v5/livedns/domains/example.com/records/home/A",
    "godaddy": "https://api.godaddy.com/v1/domains/example.com/records/A/home",
    "goip": "https://www.goip.de/setip",
    "hostinger": "https://developers.hostinger.com/api/dns/v1/zones/example.com",
    "ipv64": "https://ipv64.net/nic/update",
    "joker": "https://svc.joker.com/nic/update",
    "myaddr": "https://myaddr.tools/update",
    "namecheap": "https://dynamicdns.park-your-domain.com/update",
    "njalla": "https://njal.la/update/",
    "scaleway": "https://api.scaleway.com/domain/v2beta1/dns-zones/example.com/records",
    "servercow": "https://api.servercow.de/dns/v1/domains/example.com",
    # Tier 3 — the URL below is the one that writes, after the lookups.
    "cloudflare": "https://api.cloudflare.com/client/v4/zones/sample-zone_identifier/"
                  "dns_records/c0ffee",
    "digitalocean": "https://api.digitalocean.com/v2/domains/example.com/records/4242",
    "linode": "https://api.linode.com/v4/domains/77/records/991",
    "luadns": "https://api.luadns.com/v1/zones/12/records/345",
    "vultr": "https://api.vultr.com/v2/domains/example.com/records/rec-88",
    "vercel": "https://api.vercel.com/v1/domains/records/rec-vc",
    "bunny": "https://api.bunny.net/dnszone/5/records/61",
    "name.com": "https://api.name.com/v4/domains/example.com/records/909",
    "ionos": "https://api.hosting.ionos.com/dns/v1/zones/zone-1/records/rec-io",
    "namesilo": "https://www.namesilo.com/api/dnsUpdateRecord",
    # Spaceship writes the whole record set for a name, so it needs no lookup.
    "spaceship": "https://spaceship.dev/api/v1/dns/records/example.com",
}

# A value for every field a provider collects. Distinct per field so that a
# value landing in the wrong parameter is visible.
SAMPLE = {
    "username": "sample-user",
    "user": "sample-user",
    "password": "sample-password",
    "token": "sample-token",
    "secret": "sample-secret",
    "client_key": "sample-client-key",
    "apikey": "sample-apikey",
    "email": "user@example.org",
    "group": "sample-group",
    "dual_stack": True,
    "key": "sample-key",
    "personal_access_token": "sample-pat",
    "secret_key": "sample-secret-key",
    "zone_identifier": "sample-zone_identifier",
    "api_key": "sample-api-key",
    "team_id": "",
    "api_secret": "sample-api-secret",
    "email": "user@example.org",
    "proxied": False,
    "ttl": 300,
}


# What each two-step provider's lookup calls answer, in order. These are
# shaped after the real APIs: the list lives under a different key for every
# one of them, IDs come back as numbers here and as strings there, and LuaDNS
# writes names with a trailing dot. That variety is the reason the select
# block exists, so the fixtures have to keep it rather than smooth it away.
LOOKUPS = {
    "cloudflare": ['{"success": true, "result": [{"id": "c0ffee", "content": "198.51.100.1"}]}'],
    "digitalocean": ['{"domain_records": [{"id": 4242, "name": "home"}]}'],
    "linode": [
        '{"data": [{"id": 77, "domain": "example.com", "status": "active"}]}',
        '{"data": [{"id": 991, "name": "home", "type": "A"}]}',
    ],
    "luadns": [
        '[{"id": 12, "name": "example.com"}]',
        '[{"id": 345, "name": "home.example.com.", "type": "A"}]',
    ],
    "vultr": ['{"records": [{"id": "rec-88", "name": "home", "type": "A"}]}'],
    "vercel": ['{"records": [{"id": "rec-vc", "name": "home", "type": "A"}]}'],
    "bunny": [
        '{"Items": [{"Id": 5, "Domain": "example.com"}]}',
        '{"Records": [{"Id": 61, "Name": "home", "Type": 0}]}',
    ],
    "name.com": ['{"records": [{"id": 909, "host": "home", "type": "A"}]}'],
    "ionos": [
        '[{"id": "zone-1", "name": "example.com"}]',
        '{"records": [{"id": "rec-io", "name": "home.example.com", "type": "A"}]}',
    ],
    "namesilo": ['{"reply": {"code": "300", "resource_record": '
                 '[{"record_id": "ns-7", "host": "home.example.com", "type": "A"}]}}'],
}


class Caller:
    """Answers the lookup calls from a script, then the update.

    A provider with no lookups simply gets the update answer on its first
    call, which is what every Tier 1 and Tier 2 provider does.
    """

    def __init__(self, status=200, body="good 203.0.113.7", lookups=(), lookup_status=200):
        self.status = status
        self.body = body
        self.lookups = list(lookups)
        # What the provider answers to a lookup when the script is empty.
        # 404 is its own case: it means "no such thing here", not "not yet".
        self.lookup_status = lookup_status
        self.calls = []

    def call(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.lookups:
            return 200, self.lookups.pop(0)
        if self.lookup_status != 200:
            return self.lookup_status, ""
        return self.status, self.body

    @property
    def last(self):
        return self.calls[-1]

    @property
    def update(self):
        """The call that actually writes — the last one."""
        return self.calls[-1]


def manifest(identifier: str) -> dict:
    return yaml.safe_load((MANIFESTS / f"{identifier}.yaml").read_text(encoding="utf-8"))


def ported() -> dict[str, dict]:
    """Every provider whose manifest carries a request block."""
    found = {}
    for path in sorted(MANIFESTS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data.get("request"):
            found[data["id"]] = data
    return found


def values_for(data: dict) -> dict:
    return {field["id"]: SAMPLE.get(field["id"], f"sample-{field['id']}")
            for field in data.get("fields", [])}


# Providers whose final answer is JSON rather than a DynDNS2 keyword.
JSON_ANSWER = {
    "namesilo": '{"reply": {"code": "300", "detail": "success"}}',
    "cloudflare": '{"success": true}',
    "dondominio": '{"success": true}',
    "njalla": '{"message": "record updated"}',
}


def send(data: dict, caller: Caller, **override):
    if caller.body == "good 203.0.113.7" and data["id"] in JSON_ANSWER:
        caller.body = JSON_ANSWER[data["id"]]
    if not caller.lookups:
        caller.lookups = [body for body in LOOKUPS.get(data["id"], ())]
    native = NativeAdapter(caller=caller)
    arguments = {
        "ipv4": "203.0.113.7",
        "ipv6": None,
        "hostname": "home.example.com",
        "domain": "example.com",
        "owner": "home",
    }
    arguments.update(override)
    return native.update_declarative(
        data["request"], values_for(data),
        lookup=data.get("lookup"), create=data.get("create"),
        bindings=data.get("bindings"), **arguments)


class TestEndpoints(unittest.TestCase):
    def test_every_ported_provider_reaches_its_endpoint(self):
        for identifier, data in ported().items():
            if identifier not in ENDPOINTS:
                continue
            with self.subTest(provider=identifier):
                caller = Caller()
                send(data, caller)
                self.assertEqual(caller.update["url"], ENDPOINTS[identifier])

    def test_the_table_covers_every_ported_provider(self):
        """A provider ported without an entry here would go unchecked."""
        # The two generic providers take their URL from the form and have no
        # request block, so they are not in ported() to begin with.
        self.assertEqual(sorted(set(ported()) - set(ENDPOINTS)), [])


class TestEveryProvider(unittest.TestCase):
    """Properties that have to hold across the whole catalogue."""

    def test_no_placeholder_survives_into_a_sent_request(self):
        """An unresolved {name} means a credential went out empty."""
        for identifier, data in ported().items():
            with self.subTest(provider=identifier):
                caller = Caller()
                send(data, caller)
                sent = repr(caller.update)
                self.assertEqual(PLACEHOLDER.findall(sent), [], sent)

    def test_every_provider_is_authenticated_somehow(self):
        """The credential has to appear in the request, wherever it goes.

        Asking "is there an Authorization header" would have to keep learning
        new spellings — Gigahost uses a bearer token, GoDaddy its own
        sso-key format, Servercow two headers of its own, bunny.net a header
        called AccessKey, FreeDNS a path segment. Looking for the value
        instead needs to know none of that.
        """
        secrets = {str(SAMPLE.get(field, "")) for field in
                   ("password", "token", "secret", "apikey", "api_key", "client_key",
                    "key", "secret_key", "personal_access_token")}
        secrets.discard("")

        for identifier, data in ported().items():
            with self.subTest(provider=identifier):
                caller = Caller()
                send(data, caller)
                sent = repr(caller.update)
                self.assertTrue(any(value in sent for value in secrets),
                                f"{identifier} sends no credential")

    # Two endpoints have no address parameter at all: they read the address off
    # the connection they were reached over, which is also why each needs a
    # separate host name per family.
    INFERS_THE_ADDRESS = {"freedns", "cloudns"}

    def test_the_address_is_actually_in_the_request(self):
        """Wherever it goes — query, JSON body or form — it has to be there."""
        for identifier, data in ported().items():
            if identifier in self.INFERS_THE_ADDRESS:
                continue
            with self.subTest(provider=identifier):
                caller = Caller()
                send(data, caller)
                call = caller.update
                anywhere = repr([call.get("params"), call.get("json_body"),
                                 call.get("form_body"), call["url"]])
                self.assertIn("203.0.113.7", anywhere)

    def test_a_missing_credential_is_reported_not_sent_blank(self):
        for identifier, data in ported().items():
            with self.subTest(provider=identifier):
                caller = Caller()
                native = NativeAdapter(caller=caller)
                caller.lookups = list(LOOKUPS.get(identifier, ()))
                empty = {field["id"]: "" for field in data.get("fields", [])}
                try:
                    native.update_declarative(
                        data["request"], empty,
                        lookup=data.get("lookup"), create=data.get("create"),
                        ipv4="203.0.113.7", hostname="home.example.com",
                        domain="example.com", owner="home",
                    )
                except AdapterError:
                    continue
                # Providers that carry the credential in a query parameter
                # cannot fail early; what matters is that nothing was sent
                # with an empty credential in a header or in basic auth.
                self.assertIsNone(caller.update.get("auth"))


class TestProviderQuirks(unittest.TestCase):
    """The handful of providers that are not plain DynDNS2."""

    def test_desec_preserves_the_family_it_is_not_updating(self):
        """Without this deSEC deletes the other record.

        Sending only myipv4 makes deSEC infer the AAAA record from the
        connection — which, over IPv4, means removing it.
        """
        caller = Caller()
        send(manifest("desec"), caller)
        self.assertEqual(caller.last["params"]["myipv6"], "preserve")
        self.assertEqual(caller.last["params"]["myipv4"], "203.0.113.7")

    def test_spdyn_token_mode_puts_the_hostname_where_the_user_goes(self):
        data = manifest("spdyn")
        caller = Caller()
        native = NativeAdapter(caller=caller)
        native.update_declarative(
            data["request"],
            {"token": "sample-token", "user": "", "password": ""},
            ipv4="203.0.113.7", hostname="home.example.com",
            domain="example.com", owner="home",
        )
        self.assertEqual(caller.last["params"]["user"], "home.example.com")
        self.assertEqual(caller.last["params"]["pass"], "sample-token")

    def test_gigahost_prefers_the_account_over_the_api_key(self):
        """Basic first, not the key - the DynDNS endpoint documents only Basic.

        This used to assert the opposite. Gigahost documents an API key for its
        API in general, but the DynDNS endpoint's own section shows nothing but
        `--user email:password`. Leading with the key meant the recommended
        path was the one the endpoint does not advertise.
        """
        data = manifest("gigahostno")
        caller = Caller()
        send(data, caller)
        self.assertEqual(caller.last["auth"], ("user@example.org", "sample-password"))
        self.assertNotIn("Authorization", caller.last["headers"])

    def test_gigahost_falls_back_to_the_api_key(self):
        data = manifest("gigahostno")
        caller = Caller()
        native = NativeAdapter(caller=caller)
        native.update_declarative(
            data["request"],
            {"apikey": "flux_live_sample", "email": "", "password": ""},
            ipv4="203.0.113.7", hostname="home.example.com",
            domain="example.com", owner="home",
        )
        self.assertEqual(caller.last["headers"]["Authorization"], "Bearer flux_live_sample")
        self.assertIsNone(caller.last.get("auth"))

    def test_variomedia_switches_host_by_family(self):
        caller = Caller()
        send(manifest("variomedia"), caller, ipv4=None, ipv6="2001:db8::1")
        self.assertEqual(caller.last["url"], "https://dyndns6.variomedia.de/nic/update")

    def test_strato_authenticates_as_the_domain(self):
        caller = Caller()
        send(manifest("strato"), caller)
        self.assertEqual(caller.last["auth"], ("example.com", "sample-password"))

    def test_he_authenticates_as_the_record(self):
        caller = Caller()
        send(manifest("he"), caller)
        self.assertEqual(caller.last["auth"], ("home.example.com", "sample-password"))

    def test_dnsomatic_leaves_mx_and_wildcard_alone(self):
        """Omitting them is not neutral: DNS-O-Matic resets them."""
        caller = Caller()
        send(manifest("dnsomatic"), caller)
        for name in ("mx", "backmx", "wildcard"):
            self.assertEqual(caller.last["params"][name], "NOCHG")

    def test_ddnss_does_not_answer_in_the_dyndns2_vocabulary(self):
        data = manifest("ddnss")
        native = NativeAdapter(caller=Caller(200, "Updated 1 hostname."))
        outcome = native.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home",
        )
        self.assertTrue(outcome.ok)

        native = NativeAdapter(caller=Caller(200, "badauth"))
        outcome = native.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home",
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "auth")

    def test_zoneedit_rate_limit_is_recognised(self):
        data = manifest("zoneedit")
        native = NativeAdapter(
            caller=Caller(200, "minimum 600 seconds between requests"))
        outcome = native.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home",
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "rate_limit")


class TestRestProviderQuirks(unittest.TestCase):
    """The providers that speak JSON rather than the DynDNS2 query protocol."""

    def test_gandi_prefers_the_token_over_the_deprecated_api_key(self):
        caller = Caller()
        send(manifest("gandi"), caller)
        self.assertEqual(caller.last["headers"]["Authorization"], "Bearer sample-pat")
        self.assertNotIn("X-Api-Key", caller.last["headers"])

    def test_gandi_falls_back_to_the_api_key(self):
        data = manifest("gandi")
        caller = Caller()
        NativeAdapter(caller=caller).update_declarative(
            data["request"],
            {"personal_access_token": "", "key": "sample-key", "ttl": 300},
            ipv4="203.0.113.7", hostname="home.example.com",
            domain="example.com", owner="home",
        )
        self.assertEqual(caller.last["headers"]["X-Api-Key"], "sample-key")
        self.assertNotIn("Authorization", caller.last["headers"])

    def test_godaddy_uses_its_own_authorization_format(self):
        """sso-key key:secret — not Bearer, not basic."""
        caller = Caller()
        send(manifest("godaddy"), caller)
        self.assertEqual(
            caller.last["headers"]["Authorization"], "sso-key sample-key:sample-secret")
        self.assertEqual(caller.last["json_body"], [{"data": "203.0.113.7"}])

    def test_servercow_sends_the_apex_as_an_empty_name(self):
        """"@" would create a record literally called "@"."""
        data = manifest("servercow")
        caller = Caller()
        NativeAdapter(caller=caller).update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="example.com", domain="example.com", owner="@",
        )
        self.assertEqual(caller.last["json_body"]["name"], "")
        self.assertEqual(caller.last["json_body"]["type"], "A")

    def test_the_record_type_follows_the_family(self):
        for identifier in ("godaddy", "gandi", "scaleway", "servercow", "hostinger"):
            with self.subTest(provider=identifier):
                data = manifest(identifier)
                caller = Caller()
                send(data, caller, ipv4=None, ipv6="2001:db8::1")
                self.assertIn("AAAA", repr([caller.last["url"], caller.last["json_body"]]))

    def test_freedns_uses_a_separate_host_for_ipv6(self):
        caller = Caller()
        send(manifest("freedns"), caller, ipv4=None, ipv6="2001:db8::1")
        self.assertEqual(caller.last["url"], "https://v6.sync.afraid.org/u/sample-token/")

    def test_dynv6_uses_a_separate_host_for_ipv6(self):
        caller = Caller()
        send(manifest("dynv6"), caller, ipv4=None, ipv6="2001:db8::1")
        self.assertEqual(caller.last["url"], "https://ipv6.dynv6.com/api/update")
        self.assertNotIn("ipv4", caller.last["params"])

    def test_namecheap_reads_the_error_out_of_the_xml(self):
        """It answers HTTP 200 either way; the count is in the body."""
        data = manifest("namecheap")
        failing = NativeAdapter(caller=Caller(200, "<response><ErrCount>1</ErrCount>"
                                                   "<errors><Err1>Passwords do not match</Err1>"
                                                   "</errors></response>"))
        outcome = failing.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home")
        self.assertFalse(outcome.ok)

        passing = NativeAdapter(caller=Caller(200, "<response><ErrCount>0</ErrCount></response>"))
        self.assertTrue(passing.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home").ok)

    def test_duckdns_rejects_a_bad_token_despite_http_200(self):
        data = manifest("duckdns")
        native = NativeAdapter(caller=Caller(200, "KO"))
        outcome = native.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.duckdns.org", domain="duckdns.org", owner="home")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "auth")

    def test_dondominio_reads_the_success_flag(self):
        data = manifest("dondominio")
        native = NativeAdapter(caller=Caller(200, '{"success": false, "messages": ["nope"]}'))
        outcome = native.update_declarative(
            data["request"], values_for(data), ipv4="203.0.113.7",
            hostname="home.example.com", domain="example.com", owner="home")
        self.assertFalse(outcome.ok)

    def test_myaddr_sends_a_form_body_not_a_query(self):
        caller = Caller()
        send(manifest("myaddr"), caller)
        self.assertEqual(caller.last["form_body"], {"key": "sample-key", "ip": "203.0.113.7"})
        self.assertFalse(caller.last.get("params"))


class TestLookups(unittest.TestCase):
    """Two-step providers: find the record, then write it.

    The lookup block is what kept eighteen near-identical Python modules out
    of this project, so it is worth testing as a mechanism and not only
    through the providers that happen to use it.
    """

    def test_cloudflare_finds_the_record_then_writes_it(self):
        caller = Caller()
        send(manifest("cloudflare"), caller)

        self.assertEqual(len(caller.calls), 2)
        query, write = caller.calls
        self.assertEqual(
            query["url"],
            "https://api.cloudflare.com/client/v4/zones/sample-zone_identifier/dns_records")
        self.assertEqual(query["params"]["name"], "home.example.com")
        self.assertEqual(query["params"]["type"], "A")
        self.assertEqual(write["method"], "PUT")
        self.assertTrue(write["url"].endswith("/dns_records/c0ffee"))

    def test_a_lookup_authenticates_like_the_update(self):
        """Credentials are not repeated per step, so they must be inherited."""
        caller = Caller()
        send(manifest("cloudflare"), caller)
        for call in caller.calls:
            self.assertEqual(call["headers"]["Authorization"], "Bearer sample-token")

    def test_a_missing_record_is_created_instead_of_updated(self):
        caller = Caller(body='{"success": true}', lookups=['{"success": true, "result": []}'])
        outcome = send(manifest("cloudflare"), caller)

        self.assertTrue(outcome.ok)
        write = caller.update
        self.assertEqual(write["method"], "POST")
        self.assertTrue(write["url"].endswith("/dns_records"))
        self.assertEqual(write["json_body"]["content"], "203.0.113.7")

    def test_a_missing_record_without_a_create_block_says_so(self):
        caller = Caller(lookups=["[]"])
        with self.assertRaises(AdapterError) as caught:
            send(manifest("luadns"), caller)
        self.assertEqual(caught.exception.code, "not_found")
        # The message has to name WHICH step came up empty. luadns looks for
        # the zone first, and "create the record at your provider" would send
        # the user off to fix the wrong thing when the domain is simply not in
        # the account.
        self.assertIn("zone_id", caught.exception.message)
        self.assertIn("Konto", caught.exception.message)


    def test_linode_filters_through_a_header(self):
        caller = Caller()
        send(manifest("linode"), caller)

        self.assertEqual(len(caller.calls), 3)
        self.assertEqual(caller.calls[0]["headers"]["X-Filter"], '{"domain": "example.com"}')
        self.assertIn("/v4/domains/77/records", caller.calls[1]["url"])

    def test_a_later_step_uses_what_an_earlier_one_found(self):
        caller = Caller()
        send(manifest("luadns"), caller)
        self.assertEqual(caller.calls[1]["url"],
                         "https://api.luadns.com/v1/zones/12/records")

    def test_a_trailing_dot_in_a_name_still_matches(self):
        """LuaDNS answers "home.example.com." for "home.example.com"."""
        caller = Caller()
        send(manifest("luadns"), caller)
        self.assertTrue(caller.update["url"].endswith("/records/345"))

    def test_an_id_that_comes_back_as_a_number_is_usable_in_a_path(self):
        caller = Caller()
        send(manifest("digitalocean"), caller)
        self.assertTrue(caller.update["url"].endswith("/records/4242"))

    def test_a_rejected_credential_during_a_lookup_is_an_auth_error(self):
        """Not "the record does not exist", which is what 404 would mean."""
        data = manifest("cloudflare")

        class Refusing(Caller):
            def call(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return 403, '{"success": false}'

        with self.assertRaises(AdapterError) as caught:
            send(data, Refusing())
        self.assertEqual(caught.exception.code, "auth")

    def test_a_non_json_answer_to_a_lookup_is_reported_as_such(self):
        caller = Caller(lookups=["<html>maintenance</html>"])
        with self.assertRaises(AdapterError) as caught:
            send(manifest("cloudflare"), caller)
        self.assertEqual(caught.exception.code, "provider_response")

    def test_bunny_record_types_are_translated_to_its_own_numbering(self):
        """bunny.net calls A and AAAA 0 and 1.

        The executor must not learn that; a binding in the manifest says it,
        which is the difference between a provider being data and a provider
        being a special case in the code.
        """
        caller = Caller()
        send(manifest("bunny"), caller)
        self.assertEqual(caller.calls[1]["url"], "https://api.bunny.net/dnszone/5")
        self.assertEqual(caller.update["json_body"]["Type"], 0)

        caller = Caller(lookups=[
            '{"Items": [{"Id": 5, "Domain": "example.com"}]}',
            '{"Records": [{"Id": 62, "Name": "home", "Type": 1}]}',
        ])
        send(manifest("bunny"), caller, ipv4=None, ipv6="2001:db8::1")
        self.assertEqual(caller.update["json_body"]["Type"], 1)

    def test_numbers_and_booleans_keep_their_type_in_a_json_body(self):
        """"300" is not 300, and "false" is not false.

        A string "false" is truthy in several languages, so a TTL or a proxy
        flag that went out quoted would be wrong in a way no status code
        reports.
        """
        caller = Caller()
        send(manifest("cloudflare"), caller)
        body = caller.update["json_body"]
        self.assertEqual(body["ttl"], 300)
        self.assertIs(body["proxied"], False)

    def test_an_embedded_placeholder_is_still_text(self):
        native = NativeAdapter(caller=Caller())
        from dnsmith_hub.adapters.native import _render_deep

        self.assertEqual(_render_deep("v{n}-x", {"n": 4}), "v4-x")
        self.assertEqual(_render_deep("{n}", {"n": 4}), 4)

    def test_omit_if_empty_drops_a_named_key_but_nothing_else(self):
        """A field named in omit_if_empty disappears from the body when it

        would otherwise be sent as "" — for a provider whose JSON body names
        the address field once per record type (ipv4Address vs.
        ipv6Address, rather than one generic key plus {rrtype}), so the
        update for one family does not carry an empty placeholder for the
        other's key. An unnamed field keeps _render_deep's existing "" —
        Servercow relies on exactly that for its apex record.
        """
        from dnsmith_hub.adapters.native import _drop_empty_keys, _render_deep

        rendered = _render_deep(
            {"ipv4Address": "{ipv4}", "ipv6Address": "{ipv6}", "name": "{subdomain}"},
            {"ipv4": "203.0.113.7", "subdomain": ""},
        )
        self.assertEqual(rendered, {"ipv4Address": "203.0.113.7", "ipv6Address": "", "name": ""})
        self.assertEqual(
            _drop_empty_keys(rendered, ["ipv4Address", "ipv6Address"]),
            {"ipv4Address": "203.0.113.7", "name": ""},
        )
        # A value that is genuinely "" but not named is left alone.
        self.assertEqual(_drop_empty_keys(rendered, []), rendered)
        # A key whose value is legitimately non-empty is never touched, named
        # or not.
        self.assertEqual(
            _drop_empty_keys(rendered, ["ipv4Address", "ipv6Address", "name"])["ipv4Address"],
            "203.0.113.7",
        )

    def test_an_empty_optional_parameter_is_left_out(self):
        """Vercel's team ID is optional; sending teamId= would select no team."""
        caller = Caller()
        send(manifest("vercel"), caller)
        for call in caller.calls:
            self.assertNotIn("teamId", call.get("params") or {})

    def test_cloudflare_legacy_credentials_need_both_halves(self):
        data = manifest("cloudflare")
        caller = Caller(lookups=LOOKUPS["cloudflare"])
        NativeAdapter(caller=caller).update_declarative(
            data["request"],
            {"zone_identifier": "z", "token": "",
             "email": "user@example.org", "key": "sample-key", "proxied": False, "ttl": 1},
            lookup=data["lookup"], create=data["create"],
            ipv4="203.0.113.7", hostname="home.example.com",
            domain="example.com", owner="home",
        )
        headers = caller.update["headers"]
        self.assertEqual(headers["X-Auth-Email"], "user@example.org")
        self.assertEqual(headers["X-Auth-Key"], "sample-key")
        self.assertNotIn("Authorization", headers)


class TestDynuLegacyGroup(unittest.TestCase):
    """The classic IP-update path sends a Dynu group under Dynu's current name.

    Dynu renamed the `location` parameter to `group` in 2020 (Dynu staff in
    the community forum: "Location has been renamed to Group"); the current
    protocol documentation lists only `group`. Whether `location` still works
    as an alias is unmeasured, so the documented name is the one to send.
    """

    def _params(self, **fields):
        data = manifest("dynu")
        caller = Caller(body="good 203.0.113.7")
        NativeAdapter(caller=caller).update_declarative(
            data["request"], {"username": "user", "password": "secret", **fields},
            ipv4="203.0.113.7", hostname="home.example.com",
            domain="example.com", owner="home",
        )
        return caller.update["params"]

    def test_a_group_is_sent_under_the_name_dynu_documents(self):
        params = self._params(group="work")
        self.assertEqual(params.get("group"), "work")
        self.assertNotIn("location", params)

    def test_no_group_means_no_group_parameter_at_all(self):
        params = self._params()
        self.assertNotIn("group", params)
        self.assertNotIn("location", params)


if __name__ == "__main__":
    unittest.main()


class TestLiveProbe(unittest.TestCase):
    """"Verbindung testen" has to mean something.

    Before this, the button checked the form and reported "der Anbieter ist
    erreichbar" — after making no request at all. A test button that says
    more than it did is worse than none: it gets believed.

    A lookup only reads, so for the providers that have one it can be run for
    real. For the rest it cannot: their update IS the write, and a live test
    would set the record the user has not saved yet.
    """

    def spec(self, identifier, **values):
        data = manifest(identifier)
        return {
            "adapter": data["engine"]["adapter"],
            "protocol": data["engine"].get("protocol"),
            "request": data.get("request"),
            "lookup": data.get("lookup"),
            "bindings": data.get("bindings"),
            "values": {**values_for(data), **values},
            "context": {"domain": "example.com", "zone": "example.com", "owner": "home",
                        "subdomain": "home", "hostname": "home.example.com"},
        }

    def test_a_lookup_answered_with_404_is_not_reported_as_a_record_to_create(self):
        """404 and an empty list mean different things to the test button.

        An empty list is the normal state before the first update. A 404 says
        the provider does not know what was asked for at all - usually a zone
        that is not in this account. Telling the user "credentials and zone are
        fine" in that case is the one answer the button must never give.
        """
        adapter = NativeAdapter(caller=Caller(lookup_status=404))
        result = adapter.probe(self.spec("cloudflare"), "live")

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "not_found")
        self.assertIn("404", result.error["summary"])

    def test_a_lookup_provider_is_really_asked(self):
        caller = Caller(lookups=LOOKUPS["cloudflare"])
        result = NativeAdapter(caller=caller).probe(self.spec("cloudflare"), "live")

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.checked, "credentials")
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(caller.calls[0]["params"]["name"], "home.example.com")

    def test_a_probe_finds_the_record_at_the_apex(self):
        """An apex record (owner "@", subdomain "") must not be reported as

        missing just because the probe's context carries it as an empty
        string. `_probe_lookup` merges `context` overrides with `if value`,
        which drops falsy-but-real overrides like `subdomain: ""` — the
        lookup then filters on the placeholder default ("host") instead of
        the real, empty subdomain, finds nothing, and wrongly claims the
        record does not exist yet.
        """
        spec = self.spec("linode")
        spec["context"] = {
            "domain": "example.com", "zone": "example.com", "owner": "@",
            "subdomain": "", "hostname": "example.com",
        }
        caller = Caller(lookups=[
            '{"data": [{"id": 77, "domain": "example.com", "status": "active"}]}',
            '{"data": [{"id": 991, "name": "", "type": "A"}]}',
        ])

        result = NativeAdapter(caller=caller).probe(spec, "live")

        self.assertTrue(result.ok, result.error)
        self.assertIn("gefunden", result.message)
        self.assertNotIn("noch nicht", result.message)

    def test_a_probe_never_writes(self):
        """Only the read steps run — the update itself must not."""
        caller = Caller(lookups=LOOKUPS["linode"])
        NativeAdapter(caller=caller).probe(self.spec("linode"), "live")

        self.assertEqual(len(caller.calls), 2)
        for call in caller.calls:
            self.assertIn(call.get("method", "GET"), ("GET", "POST"))
            self.assertIsNone(call.get("json_body"))

    def test_a_record_that_does_not_exist_yet_is_not_a_failure(self):
        caller = Caller(lookups=['{"success": true, "result": []}'])
        result = NativeAdapter(caller=caller).probe(self.spec("cloudflare"), "live")

        self.assertTrue(result.ok)
        self.assertIn("noch nicht", result.message)

    def test_a_missing_record_where_none_can_be_created_is_reported(self):
        caller = Caller(lookups=["[]"])
        result = NativeAdapter(caller=caller).probe(self.spec("luadns"), "live")

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "not_found")

    def test_rejected_credentials_are_reported_as_such(self):
        class Refusing(Caller):
            def call(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return 403, "{}"

        result = NativeAdapter(caller=Refusing()).probe(self.spec("cloudflare"), "live")

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "auth")

    def test_a_one_shot_provider_says_it_only_checked_the_form(self):
        """Dynu's update is the write; there is nothing safe to try."""
        caller = Caller()
        result = NativeAdapter(caller=caller).probe(self.spec("dynu"), "live")

        self.assertTrue(result.ok)
        self.assertEqual(result.checked, "settings")
        self.assertEqual(caller.calls, [])
        self.assertIn("beim ersten Update", result.message)
