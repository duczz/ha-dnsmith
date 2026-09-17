<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Infomaniak

Schweizer Hoster. Für Dynamic DNS wird ein eigenes Kennung-Passwort-Paar angelegt.

Website: <https://www.infomaniak.com>

Einordnung: DNS-Anbieter, Registrar

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
| `username` | DynDNS-Kennung | Text | erforderlich | Ausdrücklich nicht dein Infomaniak-Login. Im Manager die Domain öffnen, links "Dynamic DNS" wählen und dort ein eigenes Kennung-Passwort-Paar anlegen. Erlaubt sind nur Buchstaben und Ziffern. |
| `password` | DynDNS-Passwort | Zugangsdaten | erforderlich | Das Passwort, das du beim Anlegen des Dynamic-DNS-Eintrags selbst vergibst — nicht dein Infomaniak-Konto-Passwort. |

---

Stand: 16.09.2026.
