<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# NameSilo

US-Registrar. Der API-Schlüssel darf nicht auf Nur-Lesen stehen.

Website: <https://www.namesilo.com>

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
| `key` | API-Key | Zugangsdaten | erforderlich | Im NameSilo API Manager erzeugen, kein Konto-Passwort. Das Häkchen für Nur-Lese-Zugriff darf dabei nicht gesetzt sein, sonst schlagen alle Änderungen fehl. |
| `ttl` | TTL | Zahl | optional | Sekunden, mindestens 3600. Andere Werte lehnt die Engine ab. Leer lassen überlässt NameSilo den Standard. (min. 3600, max. 2592001) Beispiel: `7207`. |

---

Stand: 16.09.2026.
