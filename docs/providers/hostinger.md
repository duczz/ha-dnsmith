<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Hostinger

Hoster mit eigener API. Der Token wird im hPanel erzeugt.

Website: <https://www.hostinger.com>

Einordnung: DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | API-Token | Zugangsdaten | erforderlich | Nicht dein hPanel-Passwort. Im hPanel unter Profil → API erzeugen. |
| `ttl` | TTL | Zahl | optional | Sekunden, optional. Ohne Angabe verwendet Hostinger 14400. Beispiel: `300`. |

---

Stand: 16.09.2026.
