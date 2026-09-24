<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Servercow

Deutscher Hoster mit eigener DNS-API, deren Zugänge getrennt angelegt werden.

Website: <https://www.servercow.de>

Einordnung: deutschsprachig, DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | DNS-API-Benutzername | Text | erforderlich | Nicht dein Kundenkonto-Login, sondern der Name eines DNS-API-Zugangs. Im Servercow-Panel oben rechts über deinen Kundennamen → "Servercow DNS-API" → "Neuen API-Zugang erstellen". Beispiel: `servercow_username`. |
| `password` | DNS-API-Passwort | Zugangsdaten | erforderlich | Wird beim Erstellen des Zugangs nur einmal angezeigt und ist später nicht mehr auslesbar — dann hilft nur ein neuer API-Zugang. |
| `ttl` | TTL | Zahl | optional | Beispiel: `600`. |

---

Stand: 16.09.2026.
