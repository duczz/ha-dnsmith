<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Google Cloud DNS

Google Cloud DNS. Die Anmeldung erfolgt über die JSON-Schlüsseldatei eines Dienstkontos.

Website: <https://cloud.google.com/dns>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `project` | Projekt-ID | Text | erforderlich | Die Projekt-ID, nicht der Anzeigename. Steht in der Cloud Console in der Projektauswahl. Beispiel: `mein-projekt-123456`. |
| `zone` | Cloud-DNS-Zone | Text | erforderlich | Der Name der verwalteten Zone, nicht der Domainname. Unter Network Services → Cloud DNS in der Spalte "Zone name". Beispiel: `meine-zone`. |
| `credentials` | Dienstkonto-JSON | Zugangsdaten (mehrzeilig) | erforderlich | Der komplette Inhalt der JSON-Schlüsseldatei eines Dienstkontos, nicht nur die Key-ID. Unter IAM & Admin → Service Accounts → Keys → Add key → Create new key (JSON). Das Konto braucht Schreibrechte auf die DNS-Einträge. |

---

Stand: 16.09.2026.
