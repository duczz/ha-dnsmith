<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Name.com

US-Registrar mit API-Token je Konto.

Website: <https://www.name.com>

Einordnung: Registrar

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
| `username` | Benutzername | Text | erforderlich | Dein name.com-Account-Login. |
| `token` | API-Token | Zugangsdaten | erforderlich | Nicht dein Passwort. Unter Account → Settings → API erzeugen; der Token wird nur direkt nach dem Anlegen angezeigt. |
| `ttl` | TTL | Zahl | optional | Sekunden, mindestens 300. Kleinere Werte lehnt die Engine ab. (min. 300) Beispiel: `300`. |

---

Stand: 16.09.2026.
