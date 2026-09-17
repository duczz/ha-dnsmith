<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Amazon Route 53

DNS-Dienst von AWS. Braucht neben den Zugangsschlüsseln die ID der Hosted Zone.

Website: <https://aws.amazon.com/route53/>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | ja |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `access_key` | Access Key ID | Zugangsdaten | erforderlich | Die AWS_ACCESS_KEY_ID eines IAM-Benutzers. Der Benutzer braucht die Berechtigung route53:ChangeResourceRecordSets für deine Hosted Zone. |
| `secret_key` | Secret Access Key | Zugangsdaten | erforderlich | Der zugehörige AWS_SECRET_ACCESS_KEY, kein Konsolen-Passwort. Wird nur einmal beim Anlegen des Zugriffsschlüssels angezeigt. |
| `zone_id` | Hosted Zone ID | Text | erforderlich | Die ID der Hosted Zone, etwa A30888735ZF12K83Z6F00. In der Route-53-Konsole unter "Hosted zones" → Zone → Details. Beispiel: `A30888735ZF12K83Z6F00`. |
| `ttl` | TTL | Zahl | optional | Sekunden. Leer lassen verwendet 300. Beispiel: `300`. |

## Ratenbegrenzung

Route 53 drosselt je AWS-Konto auf etwa fünf Anfragen je Sekunde im Dauerbetrieb.

---

Stand: 16.09.2026.
