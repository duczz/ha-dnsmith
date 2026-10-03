<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# OpenDNS

DNS-Dienst von Cisco. Aktualisiert die dynamische Adresse eines im Dashboard angelegten Netzwerks.

Website: <https://www.opendns.com>

Einordnung: kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Dein Login für das OpenDNS- bzw. Umbrella-Dashboard, meist die E-Mail-Adresse. |
| `password` | Konto-Passwort | Zugangsdaten | erforderlich | Das Passwort dieses Kontos; ein eigenes Update-Passwort gibt es nicht. Das Netzwerk im Dashboard muss auf dynamische IP gestellt sein. |

## Hinweise

> Was hier als Domain eingetragen wird, ist der Name des Netzwerks aus dem OpenDNS-Dashboard — kein DNS-Eintrag. Er lässt sich nirgends auflösen. DNSmith prüft bei diesem Anbieter deshalb nicht über DNS, ob die Adresse schon stimmt, sondern vergleicht mit der zuletzt gesendeten.

---

Stand: 16.09.2026.
