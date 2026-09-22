<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# dnsHome.de

Kostenloser deutscher DDNS-Dienst mit Subdomains unter mehreren eigenen Domains. IPv4, IPv6 und der IPv6-Präfix lassen sich getrennt übergeben.

Website: <https://www.dnshome.de>

Einordnung: deutschsprachig, kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | nein |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `password` | Passwort der Subdomain | Zugangsdaten | erforderlich | Nicht das Passwort deines dnsHome-Kontos. Im Mitgliederbereich wird je Subdomain ein eigenes Update-Passwort gesetzt — dieses ist gemeint. |

## Ratenbegrenzung

Keine dokumentierte Grenze.

Kürzestes sinnvolles Intervall: 5m.

## Hinweise

> Als Benutzername verlangt dnsHome die vollständige Subdomain. DNSmith setzt dafür den Hostnamen des Eintrags ein, du musst ihn nicht zweimal angeben.

> dnsHome dokumentiert keine Antworttexte für Erfolg und Misserfolg. DNSmith wertet deshalb den HTTP-Status aus: Ein falsches Passwort führt zu einer abgelehnten Anmeldung und wird dadurch zuverlässig erkannt. Ein inhaltlicher Fehler bei gültiger Anmeldung kann jedoch unbemerkt als Erfolg durchgehen — im Zweifel im Mitgliederbereich nachsehen, welche Adresse dort steht.

---

Stand: 16.09.2026.
