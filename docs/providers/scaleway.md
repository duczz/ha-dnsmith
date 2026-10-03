<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Scaleway

Französischer Cloud-Anbieter mit API-Schlüsseln aus dem IAM-Bereich.

Website: <https://www.scaleway.com>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `secret_key` | Secret Key | Zugangsdaten | erforderlich | Der geheime Teil eines Scaleway-API-Keys, nicht dein Konto-Passwort. In der Console unter IAM → API keys erzeugen und sofort notieren. |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen überlässt Scaleway den Standard. Beispiel: `300`. |

---

Stand: 16.09.2026.
