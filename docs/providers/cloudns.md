<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# ClouDNS

DNS-Anbieter aus Bulgarien mit kostenlosem Tarif. Je Eintrag wird eine geheime Update-Adresse erzeugt; aktualisiert wird immer auf die Adresse, von der die Anfrage kommt.

Website: <https://www.cloudns.net>

Einordnung: DNS-Anbieter, kostenlos

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `key` | Schlüssel der Update-Adresse | Zugangsdaten | erforderlich | In der Zonenverwaltung beim A- oder AAAA-Eintrag auf das DynDNS-Symbol klicken. ClouDNS zeigt dann eine fertige Adresse an; gebraucht wird daraus nur der Teil hinter "q=". Du kannst auch die ganze Adresse einfügen, DNSmith kürzt sie selbst. |

## Ratenbegrenzung

Keine dokumentierte Grenze. ClouDNS empfiehlt für DDNS-Einträge eine TTL von einer Stunde.

Kürzestes sinnvolles Intervall: 60s.

## Hinweise

> Jeder Schlüssel gehört zu genau einem Eintrag. Für A und AAAA derselben Domain erzeugt ClouDNS zwei verschiedene Schlüssel — in DNSmith brauchst du dafür zwei Einträge.

> **ClouDNS ignoriert die von DNSmith ermittelte Adresse.** Der Dienst trägt immer die Adresse ein, von der die Anfrage kommt. Die Einstellung „Woher die IP-Adressen kommen" wirkt hier deshalb nicht: Eine feste Adresse oder eine Home-Assistant-Entität als Quelle ändert nichts daran, mit welcher Adresse der Eintrag beschrieben wird. Für Anschlüsse hinter DS-Lite ist ClouDNS damit ungeeignet.

---

Stand: 16.09.2026.
