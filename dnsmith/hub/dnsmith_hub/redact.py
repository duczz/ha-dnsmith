"""Keeping credentials out of logs and error messages.

Two layers, because neither alone is enough.

The engine redacts by *shape*: it knows nothing about the user's values, so it
strips anything that looks like a credential — secret query parameters, URL
userinfo, bearer tokens. That catches messages from values the hub has never
seen.

This module redacts by *value*: the hub knows every stored secret, so it can
find one anywhere in a string, however it got there. That catches the case the
shape rules miss — a provider that echoes the token back in a plain sentence,
or an exception that formatted a whole request object.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

MASK = "<redacted>"

# Below this length a "secret" is too likely to occur as ordinary text — a
# one-character password would otherwise blank out every letter in the log.
MIN_REDACTABLE_LENGTH = 6


class ValueRedactor:
    """Replaces known secret values wherever they appear in a string."""

    def __init__(self) -> None:
        self._pattern: re.Pattern[str] | None = None
        self._count = 0

    def update(self, values: set[str]) -> None:
        """Rebuild from the current set of stored secrets.

        Called whenever the secret store changes. Values are matched longest
        first so that a secret which contains another is masked whole.

        A secret that carries a URL-reserved character never appears in a
        request line the way it was typed: query-auth providers go through
        httpx's own percent-encoding (`!` becomes `%21`), and the literal
        value is not a substring of that any more. Every value therefore also
        registers its percent-encoded form, so a URL that does end up
        rendered into a log line or an error string still gets caught.
        """
        candidates: set[str] = set()
        for value in values:
            if not value or len(value) < MIN_REDACTABLE_LENGTH:
                continue
            candidates.add(value)
            encoded = urllib.parse.quote(value, safe="")
            if encoded != value:
                candidates.add(encoded)

        usable = sorted(candidates, key=len, reverse=True)
        self._count = len({value for value in values if value and len(value) >= MIN_REDACTABLE_LENGTH})
        self._pattern = (
            re.compile("|".join(re.escape(value) for value in usable)) if usable else None
        )

    @property
    def value_count(self) -> int:
        return self._count

    def __call__(self, text: str) -> str:
        return self.redact(text)

    def redact(self, text: str) -> str:
        if not text or self._pattern is None:
            return text
        return self._pattern.sub(MASK, text)

    def redact_structure(self, value):
        """Walk a nested structure, redacting every string in it.

        Used on anything headed for a log, a diagnostics dump or an event.
        """
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {key: self.redact_structure(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self.redact_structure(item) for item in value)
        return value


def _exception_chain(exception: BaseException) -> list[BaseException]:
    """The exception and everything it was raised from, outermost first.

    Mirrors what the standard traceback formatter walks: `__cause__` (an
    explicit `raise ... from err`) takes priority over `__context__` (an
    exception that was simply in flight when another replaced it), and a
    `raise ... from None` sets `__suppress_context__` to say the implicit
    link should be ignored.
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exception
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return chain


class RedactingFilter(logging.Filter):
    """Log filter that masks secrets in the message and its arguments.

    This is the last line of defence. It exists because the failure it
    prevents — a token in the add-on log, which users paste into forum posts
    and bug reports — is both easy to cause and impossible to undo.
    """

    def __init__(self, redactor: ValueRedactor) -> None:
        super().__init__()
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        # Render first, then redact the finished line. Replacing msg and args
        # separately only works for values that are already strings; a library
        # that logs an object - httpx passes an httpx.URL, and the URL is where
        # a token sits - would slip through, because the formatting that turns
        # it into text happens later, in the handler, after this filter has run.
        if record.args:
            try:
                record.msg = record.getMessage()
            except Exception:  # noqa: BLE001 - a broken format string is not ours to fix
                record.msg = f"{record.msg!r} % {record.args!r}"
            record.args = ()

        if isinstance(record.msg, str):
            record.msg = self._redactor.redact(record.msg)
        else:
            # A logged object whose __str__ raises must not take the logging
            # call down with it - logging is the thing that reports trouble,
            # so it has to survive trouble.
            try:
                rendered = str(record.msg)
            except Exception:  # noqa: BLE001
                rendered = f"<unprintable {type(record.msg).__name__}>"
            record.msg = self._redactor.redact(rendered)

        # Exception text is formatted later from exc_info, so it bypasses the
        # substitutions above. Flattening it here is what stops a traceback
        # from carrying the value the rest of this class just removed.
        #
        # A raised AdapterError is deliberately generic ("Der Anbieter hat
        # nicht rechtzeitig geantwortet.") and never repeats what caused it -
        # that lives in `__cause__`, the original httpx exception. Checking
        # only the top exception's text would miss a secret sitting one level
        # down the chain, so every linked exception is rendered and checked.
        if record.exc_info and record.exc_info[1] is not None:
            exception = record.exc_info[1]
            chain = _exception_chain(exception)
            original = " | caused by ".join(
                f"{type(item).__name__}: {item}" for item in chain
            )
            cleaned = self._redactor.redact(original)
            if cleaned != original:
                record.exc_info = None
                record.exc_text = None
                record.msg = f"{record.msg} | {cleaned}"

        return True


def install(logger: logging.Logger, redactor: ValueRedactor) -> None:
    """Attach the filter to a logger and every handler it owns.

    Both are needed, and neither alone is enough:

    A filter on a logger runs only for records created on THAT logger. It is
    not consulted for records that arrive from a child logger, because
    ``Logger.handle`` applies ``self.filter`` before handing the record to
    ``callHandlers``, and ``callHandlers`` walks up the tree asking only the
    HANDLERS. So ``install(getLogger("dnsmith"))`` alone covers nothing that
    ``dnsmith.hub`` logs - which is everything this add-on writes.

    A filter on a handler, by contrast, sees every record that reaches it,
    whichever logger created it. That is why install_everywhere() below puts
    one on the root handlers: it is the only placement that catches the whole
    tree, third-party libraries included.
    """
    logger.addFilter(RedactingFilter(redactor))
    for handler in logger.handlers:
        handler.addFilter(RedactingFilter(redactor))


def install_everywhere(redactor: ValueRedactor) -> None:
    """Put the filter where every log line has to pass, whoever wrote it.

    Call this AFTER logging is configured, so the handlers exist.

    Third-party libraries are the reason this is not optional. httpx logs the
    full request URL, and for providers that carry their token in the query
    string or the path - duckdns, freedns, namesilo and every entry using the
    custom HTTP provider with query auth - that line contains the credential
    verbatim.
    """
    root = logging.getLogger()
    if not root.handlers:
        # Nothing to attach to yet. Saying so is better than returning quietly
        # and leaving the caller believing the log is covered.
        logging.getLogger(__name__).warning(
            "redaction not installed: the root logger has no handlers yet")
    for handler in root.handlers:
        handler.addFilter(RedactingFilter(redactor))

    # uvicorn configures its own loggers with propagate=False, so their records
    # never reach the root handlers the loop above just covered. They need the
    # filter on themselves. uvicorn also installs these handlers when it
    # starts, which is after this function runs - hence the logger-level
    # filter, which does apply to records created directly on that logger.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        install(logging.getLogger(name), redactor)

    # Belt and braces: even masked, a line per request is noise, and one
    # library change away from carrying something new. INFO on httpx buys
    # nothing here - failures surface through our own error handling.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
