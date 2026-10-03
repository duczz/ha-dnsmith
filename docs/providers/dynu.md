<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Dynu

Kommerzieller DDNS-Anbieter mit kostenlosem Tarif, eigenen Domains und DynDNS2-kompatibler Schnittstelle.

Website: <https://www.dynu.com>

Einordnung: kommerziell, kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Der Benutzername des Dynu-Accounts. |
| `password` | Passwort oder IP-Update-Passwort | Zugangsdaten | erforderlich | Dynu empfiehlt ein eigenes IP-Update-Passwort statt des Account-Passworts. Es steht im Control Panel unter "IP Update Password". |
| `group` | Gruppe | Text | optional | Nur nötig, wenn mehrere Hostnamen in einer Dynu-Gruppe gemeinsam aktualisiert werden sollen. Sonst leer lassen. |

## Hinweise

> Wichtig bei Dynu: Die Hauptdomain (z. B. beispiel.ddnsgeek.com) wird über den DDNS-Dienst aktualisiert. Falls auf dynu.com unter "Control Panel" → "DDNS Services" → [Domain anklicken] im unteren Abschnitt "DNS Records" manuelle A- oder AAAA-Einträge für die Domain existieren (erkennbar am Button "Remove DNS Record"), überschreiben diese die dynamische IP. Diese manuellen Records müssen dort einmalig per "Remove DNS Record" gelöscht werden, damit Dynu die dynamische IP für die Domain übernimmt.

---

Stand: 28.09.2026.
