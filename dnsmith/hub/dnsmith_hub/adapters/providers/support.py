"""What a provider module gets to work with.

Ten providers out of sixty cannot be expressed as a request block, and the
reasons are specific rather than accidental: an API that answers with an
action to wait for, one that wants a session opened first, one that deletes
and recreates instead of updating. Each of those is a shape, not a quirk, and
a module is the honest place for it.

What a module must NOT be is a second executor. Everything that is already
solved above this line stays solved there: the SSRF guard, address pinning,
the redirect refusal, the error vocabulary, the scheduling. A module gets an
`Api` that has those built in and a `Context` with the values the manifest
would have templated, and it returns the same UpdateOutcome the declarative
path returns.

A module is therefore expected to be short. If one starts growing branches
for credentials, record types or address families, that is a sign the
manifest should have carried it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..base import AdapterError
from ..native import FAILURE_MESSAGES, HTTPCaller, UpdateOutcome


@dataclass(frozen=True)
class Context:
    """The values a provider needs, already worked out.

    Exactly the runtime values the declarative path templates, so a module
    that later turns out to be expressible as a manifest translates without
    anything being renamed.
    """

    ip: str
    ipv4: str | None
    ipv6: str | None
    rrtype: str
    hostname: str
    domain: str
    owner: str
    subdomain: str

    @property
    def is_ipv6(self) -> bool:
        return bool(self.ipv6)


class Api:
    """A JSON client that keeps the guarantees the rest of DNSmith gives.

    Every call goes through HTTPCaller, so the SSRF guard, the pinned address
    and the refusal to follow redirects apply here exactly as they do to a
    manifest-driven provider. A module cannot opt out of them by accident,
    because it has no other way to reach the network.
    """

    def __init__(self, caller: HTTPCaller, *, headers: dict[str, str] | None = None,
                 auth: tuple[str, str] | None = None) -> None:
        self._caller = caller
        self._headers = dict(headers or {})
        self._auth = auth

    def with_headers(self, **headers: str) -> "Api":
        return Api(self._caller, headers={**self._headers, **headers}, auth=self._auth)

    def call(self, url: str, *, method: str = "GET", params: dict[str, str] | None = None,
             headers: dict[str, str] | None = None, json_body: Any = None,
             form_body: dict[str, str] | None = None,
             content: bytes | None = None) -> tuple[int, str]:
        return self._caller.call(
            url,
            method=method,
            params={k: v for k, v in (params or {}).items() if v not in (None, "")} or None,
            headers={**self._headers, **(headers or {})},
            auth=self._auth,
            json_body=json_body,
            form_body=form_body,
            content=content,
        )

    def json(self, url: str, *, expect: tuple[int, ...] = (200, 201, 204), **kwargs) -> Any:
        """Call and decode, turning the usual statuses into usual errors.

        Returns None for a 204 and for an empty body: several APIs answer a
        successful write with nothing at all, and a module should not have to
        guard against that every time.
        """
        status, body = self.call(url, **kwargs)

        if status in (401, 403):
            raise AdapterError("auth", FAILURE_MESSAGES["auth"], detail=body[:200])
        if status == 404:
            raise AdapterError("not_found", FAILURE_MESSAGES["not_found"], detail=body[:200])
        if status == 429:
            raise AdapterError("rate_limit", FAILURE_MESSAGES["rate_limit"], detail=body[:200])
        if status not in expect:
            raise AdapterError(
                "provider_response",
                f"Der Anbieter hat mit HTTP {status} geantwortet.",
                detail=body[:200],
            )

        if not body.strip():
            return None
        try:
            return json.loads(body)
        except ValueError as error:
            raise AdapterError(
                "provider_response",
                "Der Anbieter hat keine gültige JSON-Antwort geschickt.",
                detail=body[:200],
            ) from error


def succeeded(message: str = "Der Eintrag wurde aktualisiert.") -> UpdateOutcome:
    return UpdateOutcome(True, "success", message)


def find(entries: Any, **match: str) -> dict | None:
    """First entry whose fields match, compared as text.

    The same reasoning as in the declarative select: one provider's ID is a
    number and the next one's is a string, and names come with and without a
    trailing dot.
    """
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if all(entry.get(key) is not None
               and str(entry[key]).rstrip(".").lower() == str(wanted).rstrip(".").lower()
               for key, wanted in match.items()):
            return entry
    return None
