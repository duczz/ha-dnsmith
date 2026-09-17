<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# IPv64

Deutscher DDNS-Dienst mit starkem IPv6-Fokus, eigenen Subdomains und Healthchecks.

Website: <https://ipv64.net>

Einordnung: kostenlos, deutschsprachig, IPv6-orientiert

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
| `key` | Update-Token der Domain | Zugangsdaten | erforderlich | Der Schlüssel aus deinem IPv64-Konto. Du kannst auch die komplette Update-URL einfügen, die IPv64 anzeigt (https://ipv64.net/nic/update?key=…) — DNSmith nimmt sich den Schlüssel selbst heraus. |

## Ratenbegrenzung

IPv64 rechnet Updates gegen ein Tageskontingent an. Kurze Intervalle verbrauchen es schnell.

Kürzestes sinnvolles Intervall: 60s.

## Hinweise

> IPv64 kennt zusätzlich einen Account-Update-Token und einen Economy-Modus. Die eingesetzte Engine unterstützt beides derzeit nicht — DNSmith aktualisiert ohnehin nur bei tatsächlicher IP-Änderung, was den Economy-Modus praktisch ersetzt.

---

Stand: 16.09.2026.
