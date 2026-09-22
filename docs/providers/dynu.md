<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Dynu

Kommerzieller DDNS-Anbieter mit kostenlosem Tarif, eigenen Domains und DynDNS2-kompatibler Schnittstelle.

Website: <https://www.dynu.com>

Einordnung: kommerziell, kostenlos, DynDNS2

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
| `username` | Benutzername | Text | erforderlich | Der Benutzername des Dynu-Accounts. |
| `password` | Passwort oder IP-Update-Passwort | Zugangsdaten | erforderlich | Dynu empfiehlt ein eigenes IP-Update-Passwort statt des Account-Passworts. Es steht im Control Panel unter "IP Update Password". |
| `group` | Gruppe | Text | optional | Nur nötig, wenn mehrere Hostnamen in einer Dynu-Gruppe gemeinsam aktualisiert werden sollen. Sonst leer lassen. |

---

Stand: 16.09.2026.
