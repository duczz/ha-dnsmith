<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# freemyip.com

Kostenloser DDNS-Dienst mit Subdomains unter freemyip.com. Ein Token je Subdomain, keine Registrierung nötig.

Website: <https://freemyip.com>

Einordnung: kostenlos, IPv6-orientiert

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | Token | Zugangsdaten | erforderlich | Wird beim Anlegen der Subdomain auf freemyip.com angezeigt und gilt nur für diese eine Subdomain. Er steht auch in der dort gezeigten Update-URL hinter "token=". |

## Ratenbegrenzung

Keine dokumentierte Grenze.

Kürzestes sinnvolles Intervall: 60s.

## Hinweise

> Der Hostname muss auf freemyip.com enden. Für die Subdomain "zuhause" lautet er zuhause.freemyip.com.

> Der Dienst beantwortet jede Anfrage nur mit "OK" oder "ERROR" und nennt keinen Grund. Bleibt ein Update erfolglos, ist fast immer der Token falsch oder er gehört zu einer anderen Subdomain.

---

Stand: 16.09.2026.
