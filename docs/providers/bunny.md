<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# bunny.net

CDN- und DNS-Anbieter mit schlanker API und engen TTL-Grenzen.

Website: <https://bunny.net>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `api_key` | API-Key | Zugangsdaten | erforderlich | Der Account-API-Key, kein Storage-Zone-Key und kein Passwort. Im Dashboard unter Account Settings → API Key. |
| `ttl` | TTL | Zahl | optional | Sekunden, erlaubt sind 60 bis 3600. Andere Werte lehnt die Engine beim Start ab. (min. 60, max. 3600) Beispiel: `300`. |

---

Stand: 16.09.2026.
