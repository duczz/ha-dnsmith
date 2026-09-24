<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Gandi

Französischer Registrar und DNS-Anbieter. Neue Zugänge nutzen einen Personal Access Token.

Website: <https://www.gandi.net>

Einordnung: Registrar, DNS-Anbieter

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Anmeldeverfahren

Dieser Anbieter kennt mehrere Wege, und sie schließen einander aus — du füllst genau einen aus.

**Personal Access Token** _(empfohlen)_

Felder: `personal_access_token`

Bei Gandi unter Organisationen → Organisation wählen → Reiter Sharing → "Create a token" anlegen und ihm Rechte zur DNS-Verwaltung geben.

**API-Key (veraltet)** _(veraltet)_

Felder: `key`

Der alte Gandi-API-Key, im Quelltext als veraltet markiert und nur Rückfall, wenn kein Token gesetzt ist.

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `personal_access_token` | Personal Access Token | Zugangsdaten | je nach Verfahren | — |
| `key` | API-Key (veraltet) | Zugangsdaten | je nach Verfahren | — |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen übernimmt den Standardwert der Zone. Beispiel: `3600`. |

## Ratenbegrenzung

Bis zu 1000 Anfragen je Minute von derselben IP-Adresse.

---

Stand: 16.09.2026.
