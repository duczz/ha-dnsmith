<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# No-IP

Bekannter DDNS-Dienst mit kostenlosem Tarif. Kostenlose Hostnamen müssen regelmäßig von Hand bestätigt werden.

Website: <https://www.noip.com>

Einordnung: kostenlos, kommerziell, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | DDNS-Key-Benutzername | Text | erforderlich | Besser nicht dein No-IP-Login: unter DNS Records → Hostname bearbeiten → "Enable Dynamic DNS" einen DDNS Key erzeugen. No-IP legt dabei einen eigenen Benutzernamen an. Der Kontoname funktioniert auch, ist aber unsicherer. |
| `password` | DDNS-Key-Passwort | Zugangsdaten | erforderlich | Wird beim Erzeugen des Keys nur ein einziges Mal angezeigt — sofort kopieren, sonst brauchst du einen neuen Key. Das Kontopasswort geht ebenfalls, macht bei Sonderzeichen aber oft Ärger. |

## Ratenbegrenzung

No-IP sperrt Clients, die häufiger als alle fünf Minuten aktualisieren; der Dienst antwortet dann mit "abuse".

Kürzestes sinnvolles Intervall: 5m.

---

Stand: 16.09.2026.
