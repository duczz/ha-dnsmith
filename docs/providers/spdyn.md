<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# spDYN

Kostenloser deutscher DDNS-Dienst. Der Update-Token ist der sicherere Weg gegenüber Benutzername und Passwort.

Website: <https://www.spdyn.de>

Einordnung: deutschsprachig, kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Anmeldeverfahren

Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — du füllst genau einen aus.

**Update-Token** _(empfohlen)_

Felder: `token`

Der sichere Weg: ein je Hostname erzeugter Token. Damit liegt kein Kontopasswort im Gerät, und der Benutzername wird nicht gebraucht.

**Benutzername und Passwort**

Felder: `user`, `password`

Die Zugangsdaten eines spdyn-Kontos, das diesen Host aktualisieren darf. Nur nötig, wenn du keinen Token verwendest.

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | Update-Token | Zugangsdaten | je nach Verfahren | — |
| `user` | Benutzername | Text | je nach Verfahren | — |
| `password` | Passwort | Zugangsdaten | je nach Verfahren | — |

---

Stand: 16.09.2026.
