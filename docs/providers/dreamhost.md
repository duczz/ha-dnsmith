<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DreamHost

US-Hoster. DNS-Einträge werden über die Panel-API geändert.

Website: <https://www.dreamhost.com>

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
| `key` | API-Key | Zugangsdaten | erforderlich | Nicht dein Panel-Passwort. Im DreamHost-Panel auf der API-Seite mit "Generate a new API Key" erzeugen. Der Key braucht die DNS-Funktionen dns-list_records, dns-add_record und dns-remove_record. |

## Ratenbegrenzung

DreamHost drosselt einzelne API-Befehle je Nutzer, nennt aber keine konkreten Zahlen.

---

Stand: 16.09.2026.
