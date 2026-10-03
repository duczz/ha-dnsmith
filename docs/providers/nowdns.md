<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Now-DNS

Kostenloser DDNS-Dienst. Seit Oktober 2024 gibt es API-Tokens, die das Konto-Passwort im Update ersetzen — bis zu zehn je Konto.

Website: <https://now-dns.com>

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
| `username` | E-Mail-Adresse | Text | erforderlich | Die E-Mail-Adresse deines Now-DNS-Kontos. |
| `password` | API-Token oder Konto-Passwort | Zugangsdaten | erforderlich | Am besten ein API-Token: im Konto unter „Generate Token" erzeugen, bis zu zehn Stück möglich. Er ersetzt hier das Konto-Passwort, lässt sich einzeln zurückziehen und gibt niemandem Zugriff auf dein Konto. Das Konto-Passwort funktioniert weiterhin, ist aber der schlechtere Weg. |

---

Stand: 16.09.2026.
