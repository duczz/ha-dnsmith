<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Gigahost

Norwegischer Hoster. Der DynDNS-Endpunkt ist auf E-Mail und Passwort ausgelegt.

Website: <https://gigahost.no>

Einordnung: DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Anmeldeverfahren

Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — du füllst genau einen aus.

**E-Mail und Passwort** _(empfohlen)_

Felder: `email`, `password`

Die Zugangsdaten des Gigahost-Kontos. Gigahost dokumentiert für den DynDNS-Endpunkt ausdrücklich nur dieses Verfahren.

**API-Schlüssel**

Felder: `apikey`

Beginnt mit flux_live_ und wird nur einmal vollständig angezeigt. Für die übrigen Endpunkte von Gigahost vorgesehen; ob der DynDNS-Endpunkt ihn annimmt, ist nicht dokumentiert. Wenn Updates damit an der Anmeldung scheitern, auf E-Mail und Passwort umstellen.

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `apikey` | API-Schlüssel | Zugangsdaten | je nach Verfahren | — |
| `email` | Konto-E-Mail | E-Mail | je nach Verfahren | Beispiel: `du@example.com`. |
| `password` | Konto-Passwort | Zugangsdaten | je nach Verfahren | — |

---

Stand: 16.09.2026.
