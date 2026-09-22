"""Turning error codes into something a person can act on.

The engine classifies; the hub explains. This split exists so the engine can
stay language-neutral and the wording can change without touching Go code.

The rule for every message here: say what went wrong, then what to check. A
message that only restates the failure ("Authentifizierung fehlgeschlagen")
leaves the user exactly where they were.
"""

from __future__ import annotations

from typing import Any

from .redact import ValueRedactor

# code -> (headline, what to check)
MESSAGES: dict[str, tuple[str, list[str]]] = {
    "auth": (
        "Der Anbieter hat die Zugangsdaten abgelehnt.",
        [
            "Wurde der Schlüssel vollständig kopiert, ohne Leerzeichen am Anfang oder Ende?",
            "Ist er noch gültig, oder wurde er beim Anbieter zurückgezogen?",
            "Darf er DNS-Einträge dieser Zone ändern?",
        ],
    ),
    "account": (
        "Das Konto darf dieses Update nicht ausführen.",
        [
            "Ist das Konto beim Anbieter aktiv?",
            "Ist DDNS im gebuchten Tarif enthalten?",
        ],
    ),
    "banned": (
        "Der Anbieter hat diesen Zugang gesperrt.",
        [
            "Updates für diesen Eintrag aussetzen, bis die Sperre aufgehoben ist.",
            "Häufigste Ursache sind wiederholte Updates mit unveränderter IP-Adresse.",
        ],
    ),
    "rate_limit": (
        "Das Anfragelimit des Anbieters ist erreicht.",
        ["Das Aktualisierungsintervall für diesen Eintrag verlängern."],
    ),
    "not_found": (
        "Der Anbieter kennt diesen Eintrag nicht.",
        [
            "Stimmt die Schreibweise des Hostnamens?",
            "Die meisten Anbieter legen den Eintrag nicht selbst an — einmal dort anlegen.",
        ],
    ),
    "record_state": (
        "Der Eintrag existiert, lässt sich so aber nicht ändern.",
        ["Ist er beim Anbieter deaktiviert, gesperrt oder anderweitig verwaltet?"],
    ),
    "config": (
        "Die Einstellungen des Eintrags sind unvollständig oder ungültig.",
        ["Das fehlende Feld ergänzen und erneut speichern."],
    ),
    "ip": (
        "Die verwendete IP-Adresse war nicht brauchbar.",
        ["Die Einstellungen zur IP-Ermittlung prüfen."],
    ),
    "provider_response": (
        "Der Anbieter hat unerwartet geantwortet.",
        [
            "Meist vorübergehend.",
            "Wenn es anhält, hat sich möglicherweise die Schnittstelle des Anbieters geändert.",
        ],
    ),
    "dns": (
        "Eine DNS-Abfrage ist fehlgeschlagen.",
        ["Funktioniert die Namensauflösung im Container?"],
    ),
    "network": (
        "Der Anbieter war nicht erreichbar.",
        ["Besteht eine Internetverbindung?", "Ist der Dienst des Anbieters gerade gestört?"],
    ),
    "timeout": (
        "Der Versuch hat zu lange gedauert.",
        ["Bei häufigem Auftreten das Zeitlimit erhöhen."],
    ),
    "engine_unreachable": (
        "Die DDNS-Engine antwortet nicht.",
        [
            "Sie startet nach einer Konfigurationsänderung kurz neu — in einigen Sekunden erneut versuchen.",
            "Hält es an, steht der Grund im Add-on-Protokoll.",
        ],
    ),
    "engine_unauthorized": (
        "Der Hub darf nicht mit der Engine sprechen.",
        ["Das ist ein Fehler der App selbst, nicht deiner Zugangsdaten."],
    ),
    "redirect_refused": (
        "Der Anbieter hat auf eine andere Adresse weitergeleitet.",
        ["Die endgültige Update-URL direkt eintragen."],
    ),
    "unknown": (
        "Das Update ist aus einem unbekannten Grund fehlgeschlagen.",
        ["Die technischen Details unten enthalten die Originalmeldung."],
    ),
}


def explain(
    error: dict[str, Any] | None, *, redactor: ValueRedactor | None = None
) -> dict[str, Any] | None:
    """Enrich an engine or adapter error with German text.

    The engine's own summary is kept as `technical`: when a provider returns
    something specific and useful, hiding it behind a generic sentence would
    be a loss. That is also exactly why this is the one place a credential
    could reach a response: `detail` and `technical` come from a provider's
    own response body, not from a fixed sentence, and this function is the
    single point every one of them passes through on the way to the browser.
    The log filter never sees this path — it is wired to loggers, not to API
    responses — so redaction here has to happen explicitly, not assume the
    filter already did it.
    """
    if not error:
        return None

    code = str(error.get("code", "unknown"))
    headline, checks = MESSAGES.get(code, MESSAGES["unknown"])

    explained = {
        "code": code,
        "message": headline,
        "checks": checks,
        "retryable": bool(error.get("retryable", False)),
    }

    technical = error.get("summary") or error.get("message")
    if technical and technical != headline:
        explained["technical"] = technical

    if error.get("detail"):
        explained["detail"] = error["detail"]

    if error.get("hints"):
        explained["provider_hints"] = error["hints"]

    return redactor.redact_structure(explained) if redactor else explained
