<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DuckDNS

Kostenloser DDNS-Dienst mit Subdomains unter duckdns.org. Ein Token pro Account, kein Login nötig.

Website: <https://www.duckdns.org>

Einordnung: kostenlos, IPv6-orientiert

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |
| mehrere Einträge je Domain | ja |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | Token | Zugangsdaten | erforderlich | Steht nach dem Login auf duckdns.org ganz oben als "token". Es gilt für den gesamten Account, nicht nur für diese Domain. Beispiel: `00000000-0000-0000-0000-000000000000`. |

## Ratenbegrenzung

Keine dokumentierte Grenze. Fünf Minuten sind reichlich.

Kürzestes sinnvolles Intervall: 60s.

## Hinweise

> Der Hostname muss auf duckdns.org enden. Für die Subdomain "zuhause" lautet er zuhause.duckdns.org.

> Mehrere Hostnamen derselben Domain lassen sich mit Komma trennen. Zwei verschiedene DuckDNS-Domains brauchen dagegen zwei Einträge.

---

Stand: 16.09.2026.
