<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Hetzner Cloud

Dieselbe Firma wie Hetzner, aber die Cloud-API mit eigenen Token.

Website: <https://www.hetzner.com>

Einordnung: deutschsprachig, Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | API-Token | Zugangsdaten | erforderlich | Token der Hetzner CLOUD API, nicht der DNS Console auf dns.hetzner.com. In der Cloud Console unter Security → API tokens mit "Read & Write" erzeugen; wird nur einmal angezeigt. |
| `ttl` | TTL | Zahl | optional | Sekunden, ab 60. Nur relevant, wenn der Eintrag neu angelegt wird. (min. 60) Beispiel: `600`. |

## Hinweise

> Seit Hetzner die getrennte DNS-Konsole abgeschaltet hat (27.05.2026), ist das dieselbe Schnittstelle wie bei „Hetzner“. Beide Einträge führen zum selben Ergebnis; welchen du nimmst, ist Geschmackssache.

---

Stand: 16.09.2026.
