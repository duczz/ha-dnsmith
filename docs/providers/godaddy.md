<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# GoDaddy

Großer US-Registrar. Der API-Schlüssel muss ein Production-Key sein, kein Test-Key.

Website: <https://www.godaddy.com>

Einordnung: Registrar

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `key` | API-Key | Zugangsdaten | erforderlich | Der öffentliche Teil des Schlüsselpaars von developer.godaddy.com — unbedingt ein Production-Key, kein Test-Key. Form xxxxxxxx_yyyyyyyy; das Format wird streng geprüft. |
| `secret` | API-Secret | Zugangsdaten | erforderlich | Das zugehörige Secret von derselben Seite, nicht dein GoDaddy-Passwort. |

## Ratenbegrenzung

20.000 API-Aufrufe im Monat im kostenlosen Kontingent. Eine Minutengrenze nennt GoDaddy nicht mehr.

## Hinweise

> API-Zugriff setzt ein GoDaddy-Konto mit mindestens einer aktiven Domain voraus. Scheitert die Verbindung mit "Access denied", liegt es meist daran und nicht an den Zugangsdaten.

---

Stand: 16.09.2026.
