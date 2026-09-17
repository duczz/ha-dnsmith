<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Vercel

Hosting-Plattform. Verwaltet die DNS-Einträge der dort eingetragenen Domains.

Website: <https://vercel.com>

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
| `token` | API-Token | Zugangsdaten | erforderlich | Kein Konto-Passwort. Im Dashboard auf das persönliche Konto wechseln, Settings → Tokens → Create. Danach wird es nicht wieder angezeigt. |
| `team_id` | Team-ID | Text | optional | Nur nötig, wenn die Domain einem Team gehört und nicht deinem persönlichen Konto. Steht in den allgemeinen Team-Einstellungen. |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen sendet das Feld gar nicht mit, Vercel behält dann seinen Wert. Beispiel: `60`. |

## Ratenbegrenzung

50 Anfragen je Minute für das Anlegen und Ändern von DNS-Einträgen.

---

Stand: 16.09.2026.
