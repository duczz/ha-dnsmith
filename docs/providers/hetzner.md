<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Hetzner

Deutscher Hoster. Läuft über die Hetzner Cloud API, nicht mehr über die alte DNS Console (die wurde am 27.05.2026 abgeschaltet).

Website: <https://www.hetzner.com>

Einordnung: deutschsprachig, DNS-Anbieter

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
| `token` | API-Token | Zugangsdaten | erforderlich | Token der Hetzner Cloud Console (console.hetzner.com), nicht dein Konto-Passwort. Unter Sicherheit → API-Tokens mit Schreibrecht erzeugen; er wird nur einmal angezeigt. Ein Token aus der alten, inzwischen abgeschalteten DNS Console (dns.hetzner.com) funktioniert hier nicht mehr. |
| `ttl` | TTL | Zahl | optional | Sekunden, optional. Leer lassen für den Zonen-Standardwert, sonst mindestens 60 Sekunden — kleinere Werte lehnt Hetzner ab. (min. 60) Beispiel: `600`. |

---

Stand: 16.09.2026.
