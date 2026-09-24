<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DDNSS.de

Kostenloser deutscher DDNS-Dienst mit eigenen Domains.

Website: <https://ddnss.de>

Einordnung: deutschsprachig, kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Der Benutzername deines ddnss.de-Kontos. |
| `password` | Passwort | Zugangsdaten | erforderlich | Das Passwort deines ddnss.de-Kontos. ddnss bietet je Host zwar auch einen Update-Key an, diese Engine nutzt hier aber die Kontodaten. |
| `dual_stack` | Dual Stack | Ja/Nein | optional | Beispiel: `false`. |

## Ratenbegrenzung

DDNSS verlangt in seinen Regeln mindestens fünf Minuten Abstand zwischen zwei Updates.

Kürzestes sinnvolles Intervall: 5m.

---

Stand: 16.09.2026.
