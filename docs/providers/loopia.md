<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Loopia

Schwedischer Registrar und Hoster. Die Domain muss vorher für DynDNS vorbereitet werden.

Website: <https://www.loopia.com>

Einordnung: Registrar, DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Kundzon-Benutzername | Text | erforderlich | Dein Login für die Loopia Kundzon. Die Domain muss vorher für DynDNS vorbereitet sein: ein A-Eintrag unter @ und ein CNAME unter *. |
| `password` | Kundzon-Passwort | Zugangsdaten | erforderlich | Das Passwort der Loopia Kundzon. Meldest du dich sonst nur per BankID an, musst du unter Kontoinställningar erst ein Passwort setzen. |

---

Stand: 16.09.2026.
