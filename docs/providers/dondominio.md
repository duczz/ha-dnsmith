<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DonDominio

Spanischer Registrar. Updates laufen über einen eigenen DonDNS-Key.

Website: <https://www.dondominio.com>

Einordnung: Registrar

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `username` | Benutzername | Text | erforderlich | Dein DonDominio- bzw. MrDomain-Benutzername aus dem Kundenbereich. |
| `key` | DonDNS-Key | Zugangsdaten | erforderlich | Ein eigens erzeugtes Zweitpasswort, nicht dein Konto-Passwort. Im Kundenbereich unter "Mein Konto" den Punkt "DonDNS Key" öffnen und bei Bedarf einen neuen erzeugen. |
| `password` | DonDNS-Key (altes Feld) | Zugangsdaten | optional | Veraltet. Der Wert wird nur nach "key" kopiert, wenn dieses leer ist. Für neue Einrichtungen leer lassen. |

---

Stand: 03.10.2026.
