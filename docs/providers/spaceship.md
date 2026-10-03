<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Spaceship

Registrar mit API-Schlüssel und Secret aus dem eigenen API Manager.

Website: <https://www.spaceship.com>

Einordnung: Registrar

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `api_key` | API-Key | Zugangsdaten | erforderlich | Im Spaceship API Manager über "New API key" erzeugen. Nicht dein Konto-Passwort. |
| `api_secret` | API-Secret | Zugangsdaten | erforderlich | Entsteht im selben Schritt und wird nur einmal angezeigt. |
| `ttl` | TTL | Zahl | optional | Sekunden, erlaubt sind 60 bis 3600. (min. 60, max. 3600) Beispiel: `300`. |

---

Stand: 16.09.2026.
