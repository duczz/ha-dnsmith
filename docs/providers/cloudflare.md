<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Cloudflare

DNS-Records direkt über die Cloudflare-API aktualisieren, mit Proxy- und TTL-Steuerung.

Website: <https://www.cloudflare.com>

Einordnung: Cloud-DNS, DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| Wildcard-Einträge | ja |
| TTL einstellbar | ja |
| Proxy-Schalter | ja |

## Anmeldeverfahren

Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — du füllst genau einen aus.

**API-Token** _(empfohlen)_

Felder: `token`

Die sichere Variante. Lege unter "My Profile → API Tokens" ein Token mit der Berechtigung Zone → DNS → Edit an und beschränke es auf genau diese Zone. Damit kann DNSmith nichts anderes in deinem Account tun.

**E-Mail und Global API Key** _(veraltet)_

Felder: `email`, `key`

Nicht empfohlen. Der Global API Key hat Vollzugriff auf den gesamten Cloudflare-Account, inklusive Abrechnung und Domain-Transfers.

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `zone_identifier` | Zone-ID | Text | erforderlich | Auf der Übersichtsseite der Domain rechts unten als "Zone ID". Eine 32-stellige Hex-Zeichenkette. Beispiel: `023e105f4ecef8ad9ca31a8372d0c353`. |
| `token` | API-Token | Zugangsdaten | je nach Verfahren | — |
| `email` | Account-E-Mail | E-Mail | je nach Verfahren | Beispiel: `du@example.com`. |
| `key` | Global API Key | Zugangsdaten | je nach Verfahren | — |
| `proxied` | Cloudflare-Proxy aktiv | Ja/Nein | optional | Leitet den Verkehr über Cloudflare. Verbirgt die eigene IP-Adresse, macht den Record aber für alles außer HTTP und HTTPS unbrauchbar — also nicht für VPN, SSH oder Mailserver geeignet. Vorgabe: `nein`. |
| `ttl` | TTL | Zahl | optional | Sekunden. Der Wert 1 bedeutet bei Cloudflare "automatisch". (min. 1, max. 86400) Vorgabe: `1`. Beispiel: `600`. |

## Ratenbegrenzung

1200 Anfragen pro fünf Minuten und Account.

Kürzestes sinnvolles Intervall: 60s.

---

Stand: 16.09.2026.
