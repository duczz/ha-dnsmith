<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# LuaDNS

DNS-Anbieter, dessen Zonen aus einem Git-Repository gespeist werden.

Website: <https://www.luadns.com>

Einordnung: DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `email` | Konto-E-Mail | E-Mail | erforderlich | Die E-Mail-Adresse deines LuaDNS-Kontos. Sie wird gegen ein E-Mail-Muster geprüft, eine reine Kennung wird abgelehnt. Beispiel: `du@example.com`. |
| `token` | API-Token | Zugangsdaten | erforderlich | Nicht dein Konto-Passwort. In den LuaDNS-Einstellungen den API-Zugriff aktivieren und den angezeigten Token kopieren. |

---

Stand: 16.09.2026.
