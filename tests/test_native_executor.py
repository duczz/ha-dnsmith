"""Tests for the declarative request executor.

The executor is what makes a provider a piece of YAML, so these tests are
really tests of the manifest contract: what a request block may say, and what
DNSmith does with the answer.

The HTTP layer is replaced by a recording stub. That is not a shortcut around
httpx — it is the boundary worth testing. What matters is which URL, which
parameters, which credentials and which body DNSmith would have sent, and
httpx is not the part that could get those wrong.

unittest rather than pytest, so they run with nothing installed.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "dnsmith/hub"))

from dnsmith_hub.adapters.base import AdapterError  # noqa: E402
from dnsmith_hub.adapters.native import (  # noqa: E402
    NativeAdapter,
    RequestSpec,
    evaluate,
    render,
)


class RecordingCaller:
    """Stands in for HTTPCaller and remembers what it was asked to send."""

    def __init__(self, status: int = 200, body: str = "good") -> None:
        self.status = status
        self.body = body
        self.calls: list[dict] = []

    def call(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.status, self.body

    @property
    def last(self) -> dict:
        return self.calls[-1]


def adapter(status: int = 200, body: str = "good") -> tuple[NativeAdapter, RecordingCaller]:
    caller = RecordingCaller(status, body)
    return NativeAdapter(caller=caller), caller


class RenderTest(unittest.TestCase):
    def test_fills_placeholders(self):
        self.assertEqual(render("{a}-{b}", {"a": "x", "b": "y"}), "x-y")

    def test_unknown_placeholder_becomes_empty(self):
        self.assertEqual(render("a{missing}b", {}), "ab")

    def test_quotes_for_path_segments(self):
        # A domain with a slash in it must not be able to reach a different
        # endpoint of the provider's API.
        self.assertEqual(
            render("https://api/{zone}/records", {"zone": "a/../b"}, quote=True),
            "https://api/a%2F..%2Fb/records",
        )

    def test_false_renders_empty_not_the_word_false(self):
        self.assertEqual(render("{flag}", {"flag": False}), "")


class ExecutorTest(unittest.TestCase):
    def test_builds_a_dyndns2_style_call(self):
        native, caller = adapter()
        request = {
            "url": "https://api.example.com/nic/update",
            "auth": {"mode": "basic", "username": "{username}", "password": "{password}"},
            "params": {"hostname": "{hostname}", "myip": "{ipv4}", "myipv6": "{ipv6}"},
            "success": {"vocabulary": "dyndns2"},
        }
        outcome = native.update_declarative(
            request,
            {"username": "u", "password": "p"},
            ipv4="203.0.113.7",
            hostname="home.example.com",
        )

        self.assertTrue(outcome.ok)
        self.assertEqual(caller.last["url"], "https://api.example.com/nic/update")
        self.assertEqual(caller.last["auth"], ("u", "p"))
        self.assertEqual(
            caller.last["params"],
            {"hostname": "home.example.com", "myip": "203.0.113.7"},
        )

    def test_empty_parameters_are_dropped_not_sent_blank(self):
        # Several providers read "myipv6=" as "delete the AAAA record".
        native, caller = adapter()
        native.update_declarative(
            {"url": "https://api/u", "params": {"myip": "{ipv4}", "myipv6": "{ipv6}"},
             "success": {"vocabulary": "dyndns2"}},
            {},
            ipv4="203.0.113.7",
        )
        self.assertNotIn("myipv6", caller.last["params"])

    def test_token_header(self):
        native, caller = adapter(200, '{"status":"ok"}')
        native.update_declarative(
            {"url": "https://api/{zone}/rrset", "method": "PUT",
             "auth": {"mode": "header", "header": "Authorization", "format": "Token {token}"},
             "body_type": "json", "body": {"records": ["{ipv4}"], "ttl": "{ttl}"},
             "success": {"status": [200]}},
            {"token": "secret-token", "ttl": 300},
            ipv4="203.0.113.7",
            domain="example.com",
        )
        self.assertEqual(caller.last["headers"]["Authorization"], "Token secret-token")
        self.assertEqual(caller.last["method"], "PUT")
        # The TTL stays a number: a placeholder that is the whole field keeps
        # the value's type rather than stringifying it.
        self.assertEqual(caller.last["json_body"], {"records": ["203.0.113.7"], "ttl": 300})
        self.assertEqual(caller.last["url"], "https://api/example.com/rrset")

    def test_query_credential_never_becomes_a_header(self):
        native, caller = adapter()
        native.update_declarative(
            {"url": "https://api/u", "auth": {"mode": "query", "param": "apikey", "value": "{key}"},
             "success": {"status": [200]}},
            {"key": "abc"},
            ipv4="203.0.113.7",
        )
        self.assertEqual(caller.last["params"]["apikey"], "abc")
        self.assertNotIn("Authorization", caller.last["headers"])

    def test_header_injection_is_refused(self):
        native, _ = adapter()
        with self.assertRaises(AdapterError) as caught:
            native.update_declarative(
                {"url": "https://api/u", "headers": {"X-Zone": "{zone}"},
                 "success": {"status": [200]}},
                {},
                ipv4="203.0.113.7",
                domain="evil\r\nX-Other: 1",
            )
        self.assertEqual(caught.exception.code, "config")

    def test_no_address_is_refused_before_any_request(self):
        native, caller = adapter()
        with self.assertRaises(AdapterError) as caught:
            native.update_declarative({"url": "https://api/u"}, {})
        self.assertEqual(caught.exception.code, "ip")
        self.assertEqual(caller.calls, [])

    def test_runtime_values_win_over_a_field_of_the_same_name(self):
        native, caller = adapter()
        native.update_declarative(
            {"url": "https://api/u", "params": {"a": "{ipv4}"}, "success": {"status": [200]}},
            {"ipv4": "10.0.0.1"},
            ipv4="203.0.113.7",
        )
        self.assertEqual(caller.last["params"]["a"], "203.0.113.7")


class EvaluateTest(unittest.TestCase):
    def spec(self, **block) -> RequestSpec:
        return RequestSpec.from_manifest({"url": "https://api/u", **block})

    def test_dyndns2_badauth_on_a_200_is_a_failure(self):
        # The trap the whole "success" block exists for.
        outcome = evaluate(self.spec(success={"vocabulary": "dyndns2"}), 200, "badauth")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "auth")

    def test_mapped_failure_beats_a_2xx(self):
        spec = self.spec(success={"status": [200]}, failures={"quota exceeded": "account"})
        outcome = evaluate(spec, 200, "Quota exceeded for this plan")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "account")

    def test_status_only(self):
        self.assertTrue(evaluate(self.spec(success={"status": [201]}), 201, "").ok)
        self.assertFalse(evaluate(self.spec(success={"status": [201]}), 200, "").ok)

    def test_json_path(self):
        spec = self.spec(success={"json_path_equals": {"result.status": "SUCCESS"}})
        self.assertTrue(evaluate(spec, 200, '{"result":{"status":"SUCCESS"}}').ok)
        self.assertFalse(evaluate(spec, 200, '{"result":{"status":"ERROR"}}').ok)

    def test_json_path_on_a_non_json_answer(self):
        spec = self.spec(success={"json_path_equals": {"status": "ok"}})
        outcome = evaluate(spec, 200, "<html>maintenance</html>")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "provider_response")

    def test_body_regex(self):
        spec = self.spec(success={"body_regex": r"^good|^nochg"})
        self.assertTrue(evaluate(spec, 200, "good 203.0.113.7").ok)
        self.assertFalse(evaluate(spec, 200, "dnserr").ok)

    def test_without_rules_the_status_decides(self):
        self.assertTrue(evaluate(self.spec(), 204, "").ok)
        outcome = evaluate(self.spec(), 401, "nope")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.code, "auth")

    def test_answers_are_truncated_so_a_page_cannot_reach_the_log(self):
        outcome = evaluate(self.spec(), 500, "x" * 5000)
        self.assertLessEqual(len(outcome.raw), 200)


if __name__ == "__main__":
    unittest.main()
