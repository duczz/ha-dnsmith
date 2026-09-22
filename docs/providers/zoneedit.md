<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# ZoneEdit

Älterer DNS-Anbieter. Updates sind ausschließlich mit einem eigenen Token möglich.

Website: <https://www.zoneedit.com>

Einordnung: DNS-Anbieter

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
| `username` | Benutzername | Text | erforderlich | Dein Login für das ZoneEdit Control Panel. |
| `token` | Dyn-Authentication-Token | Zugangsdaten | erforderlich | Nicht dein ZoneEdit-Passwort: Control Panel → DNS → Werkzeug-Symbol bei Dyn Records → Host und TTL angeben → Enable. ZoneEdit lässt nur diesen Token zu. Zwischen zwei Updates müssen mindestens zehn Minuten liegen. |

---

Stand: 16.09.2026.
