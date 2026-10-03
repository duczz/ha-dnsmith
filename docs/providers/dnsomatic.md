<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DNS-O-Matic

Kostenloser Verteiler: ein Update an DNS-O-Matic wird an mehrere DDNS-Dienste weitergereicht. Die Zugangsdaten sind die eines OpenDNS-Kontos. Wird abgeschaltet: Cisco/OpenDNS kündigte den Dienst per E-Mail vom 05.09.2026 mit 30 Tagen Frist — das Ende liegt also um den 05.10.2026, zusammen mit der Löschung aller DNS-O-Matic-Kontodaten. Die OpenDNS-Logins selbst bleiben bestehen. Auf dnsomatic.com steht dazu nichts (Stand 14.09.2026), die Mail wurde aber von mehreren Nutzern unabhängig voneinander im Wortlaut veröffentlicht. Für neue Einrichtungen besser einen anderen Anbieter wählen.

Website: <https://www.dnsomatic.com>

Einordnung: kostenlos, DynDNS2

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Dein DNS-O-Matic-Login (ein OpenDNS-Konto) — nicht der Benutzername des Dienstes, an den DNS-O-Matic weiterleitet. |
| `password` | Konto-Passwort | Zugangsdaten | erforderlich | Das Passwort deines DNS-O-Matic-Kontos. Nicht die Passwörter der verknüpften Dienste eintragen. |

## Ratenbegrenzung

DNS-O-Matic kennt die Antwort "abuse" und sperrt vorübergehend, wenn zu häufig aktualisiert wird.

---

Stand: 16.09.2026.
