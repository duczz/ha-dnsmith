<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DigitalOcean

Cloud-Anbieter. Verwaltet die DNS-Zonen der dort eingetragenen Domains.

Website: <https://www.digitalocean.com>

Einordnung: Cloud-DNS

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
| `token` | API-Token | Zugangsdaten | erforderlich | Ein Personal Access Token mit Schreibrechten, nicht dein Passwort. Unter Account → API → Tokens → "Generate New Token". Wird nur einmal angezeigt. |

## Ratenbegrenzung

5000 Anfragen je Stunde und 250 je Minute, gezählt je Token.

---

Stand: 16.09.2026.
