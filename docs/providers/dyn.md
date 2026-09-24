<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Dyn

Kommerzieller DDNS-Dienst von Oracle, früher DynDNS. Kostenpflichtig, auch für Neukunden buchbar.

Website: <https://account.dyn.com>

Einordnung: kommerziell, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Anmeldeverfahren

Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — du füllst genau einen aus.

**Client-Key** _(empfohlen)_

Felder: `client_key`

Der aktuelle Weg. Der Client-Key steht im Dyn-Account unter den Update-Clients. Upstream dokumentiert ausschließlich diesen.

**Account-Passwort** _(veraltet)_

Felder: `password`

Der alte Weg, im Quelltext als veraltet markiert und nur noch aus Kompatibilität vorhanden. Bestehende Konfigurationen funktionieren weiter; für neue besser den Client-Key nehmen.

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Der Benutzername des Dyn-Accounts. |
| `client_key` | Client-Key | Zugangsdaten | je nach Verfahren | — |
| `password` | Account-Passwort | Zugangsdaten | je nach Verfahren | — |

---

Stand: 16.09.2026.
