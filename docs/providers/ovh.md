<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# OVHcloud

Französischer Hoster mit zwei Wegen: dem einfachen DynHost und der vollen API.

Website: <https://www.ovhcloud.com>

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
| `mode` | Verfahren | Auswahl | optional | DynHost ist der übliche Weg und braucht nur Benutzername und Passwort. Die API brauchst du, wenn die Zone kein DynHost unterstützt; dafür legst du eine OVH-Anwendung an. Vorgabe: `dynamic`. |
| `username` | DynHost-Benutzername | Text | erforderlich (nur bei mode = dynamic) | Nicht dein OVH-Kundenkennzeichen. Im OVH-Kundencenter unter Web Cloud → Domains → DNS-Zone → Reiter DynHost → Zugriff verwalten → Benutzernamen erstellen. Du vergibst dabei ein Suffix. |
| `password` | DynHost-Passwort | Zugangsdaten | erforderlich (nur bei mode = dynamic) | Nicht dein OVH-Konto-Passwort. Du legst es im selben Dialog fest, in dem du den DynHost-Benutzer anlegst. Es gilt nur für DynHost-Updates. |
| `app_key` | Application Key | Zugangsdaten | erforderlich (nur bei mode = api) | Aus einer OVH-Anwendung, die du unter eu.api.ovh.com/createApp/ anlegst. Dort bekommst du Application Key und Application Secret zusammen. |
| `app_secret` | Application Secret | Zugangsdaten | erforderlich (nur bei mode = api) | Das Gegenstück zum Application Key aus derselben Anwendung. |
| `consumer_key` | Consumer Key | Zugangsdaten | erforderlich (nur bei mode = api) | Verknüpft die Anwendung mit deinem OVH-Konto. Über ovh.com/auth/api/createToken mit Schreibrechten auf die DNS-Zone erzeugen. |
| `api_endpoint` | API-Endpunkt | Auswahl | optional (nur bei mode = api) | Vorgabe: `ovh-eu`. |

---

Stand: 16.09.2026.
