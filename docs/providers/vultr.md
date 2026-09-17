<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Vultr

Cloud-Anbieter. Der API-Zugriff ist zusätzlich auf freigegebene IP-Adressen beschränkt.

Website: <https://www.vultr.com>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `apikey` | API-Key | Zugangsdaten | erforderlich | Aus dem Kundenportal unter Account → API, nicht das Konto-Passwort. Wichtig: Vultr filtert nach IP — trage dort die öffentliche Adresse deines Anschlusses ein, sonst werden alle Anfragen abgelehnt. |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen verwendet den Standardwert der Zone. Beispiel: `300`. |

## Ratenbegrenzung

Ab etwa 30 Anfragen je Sekunde antwortet Vultr mit HTTP 429.

---

Stand: 16.09.2026.
