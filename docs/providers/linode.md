<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Linode

Cloud-Anbieter. Verwaltet die DNS-Zonen der dort eingetragenen Domains.

Website: <https://www.linode.com>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `token` | Personal Access Token | Zugangsdaten | erforderlich | Kein Konto-Passwort. Im Cloud Manager oben auf den Benutzernamen → API Tokens → "Create a Personal Access Token" und dem Token Schreibrechte für Domains geben. |

## Ratenbegrenzung

1600 Anfragen je Minute; für paginierte Abfragen, also Listen, 200 je Minute.

---

Stand: 16.09.2026.
