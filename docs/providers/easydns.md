<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# easyDNS

Kanadischer DNS-Anbieter und Registrar. Für Updates ist ausschließlich ein eigener Token zugelassen.

Website: <https://www.easydns.com>

Einordnung: DNS-Anbieter, Registrar

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
| `username` | Benutzername | Text | erforderlich | Dein Login für das easyDNS Control Panel. |
| `token` | Dynamic Token | Zugangsdaten | erforderlich | Der "Dynamic Authenticated Token", ausdrücklich nicht dein Passwort: Domain → DNS Settings → Modular Editor → bei Dynamic Records auf Edit → Enable. easyDNS lässt für Updates nur diesen Token zu. |

## Ratenbegrenzung

easyDNS verlangt mindestens zehn Minuten Abstand zwischen zwei Updates desselben Eintrags; zu frühe Aufrufe werden mit TOOSOON abgelehnt.

Kürzestes sinnvolles Intervall: 600s.

---

Stand: 16.09.2026.
