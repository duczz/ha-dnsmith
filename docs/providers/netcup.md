<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# netcup

Deutscher Hoster. Braucht API-Schlüssel und API-Passwort — zwei verschiedene Dinge.

Website: <https://www.netcup.com>

Einordnung: deutschsprachig, DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `customer_number` | Kundennummer | Text | erforderlich | Die netcup-Kundennummer, wie sie im Kundenkonto oben steht. Beispiel: `111111`. |
| `api_key` | API-Key | Zugangsdaten | erforderlich | Der Schlüssel, der deinen API-Zugang identifiziert. Im netcup Customer Control Panel im API-Bereich erzeugen; mehrere Keys sind möglich. |
| `password` | API-Passwort | Zugangsdaten | erforderlich | Ausdrücklich nicht dein Kontopasswort. netcup erlaubt genau ein API-Passwort pro Konto; es gilt für alle deine API-Keys und wird ebenfalls im CCP im API-Bereich gesetzt. |

---

Stand: 16.09.2026.
