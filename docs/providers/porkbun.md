<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Porkbun

US-Registrar. Der API-Zugriff muss zusätzlich je Domain freigeschaltet werden.

Website: <https://porkbun.com>

Einordnung: Registrar

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `api_key` | API-Key | Zugangsdaten | erforderlich | Der öffentliche Teil des Schlüsselpaars, beginnt meist mit pk1_. Unter porkbun.com/account/api erzeugen. Zusätzlich musst du bei der Domain selbst den Schalter "API ACCESS" einschalten, sonst wird jede Anfrage abgelehnt. |
| `secret_api_key` | Secret-API-Key | Zugangsdaten | erforderlich | Der geheime Teil desselben Paars, beginnt meist mit sk1_. Nicht dein Porkbun-Passwort; wird nur einmal angezeigt. |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen behält den Standardwert von Porkbun. Beispiel: `600`. |

---

Stand: 16.09.2026.
