<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# DonDominio

Spanischer Registrar. Updates laufen über einen eigenen DonDNS-Key.

Website: <https://www.dondominio.com>

Einordnung: Registrar

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
| `username` | Benutzername | Text | erforderlich | Dein DonDominio- bzw. MrDomain-Benutzername aus dem Kundenbereich. |
| `key` | DonDNS-Key | Zugangsdaten | erforderlich | Ein eigens erzeugtes Zweitpasswort, nicht dein Konto-Passwort. Im Kundenbereich unter "Mein Konto" den Punkt "DonDNS Key" öffnen und bei Bedarf einen neuen erzeugen. |
| `password` | DonDNS-Key (altes Feld) | Zugangsdaten | optional | Veraltet. Der Quelltext kopiert diesen Wert nur nach "key", wenn dieses leer ist — bisher stand es im Formular genau andersherum. Für neue Einrichtungen leer lassen. |

---

Stand: 16.09.2026.
