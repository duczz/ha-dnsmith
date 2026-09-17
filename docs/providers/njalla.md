<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Njalla

Datenschutzorientierter Registrar. Der Schlüssel gilt je Eintrag, nicht je Konto.

Website: <https://njal.la>

Einordnung: Registrar, DNS-Anbieter

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
| `key` | Eintrags-Schlüssel | Zugangsdaten | erforderlich | Gilt für einen einzelnen Dynamic-Eintrag, nicht für das ganze Konto. Bei Njalla die Domain öffnen → Add record → Typ "Dynamic" → Subdomain eintragen; der Schlüssel steht danach im angelegten Eintrag. |

---

Stand: 16.09.2026.
