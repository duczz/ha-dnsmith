<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Namecheap

Großer US-Registrar. Dynamic DNS wird je Domain eingeschaltet; über diese Schnittstelle gibt es kein IPv6.

Website: <https://www.namecheap.com>

Einordnung: Registrar

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 |
| Hinweis | Dieser Anbieter kann **kein IPv6**. |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `password` | Dynamic-DNS-Passwort | Zugangsdaten | erforderlich | Nicht dein Namecheap-Kontopasswort. Namecheap erzeugt es, sobald du die Funktion einschaltest: Domain List → Manage → Advanced DNS → Schalter "Dynamic DNS". Das Passwort steht danach direkt darunter. |

## Ratenbegrenzung

50 Anfragen je Minute, 700 je Stunde, 8000 am Tag — gezählt über den gesamten API-Schlüssel.

---

Stand: 16.09.2026.
